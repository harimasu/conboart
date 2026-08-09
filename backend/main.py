"""CONBOART backend — FastAPI.

Per-session, nothing stored: each generation lives in a temp directory keyed by
a job id with a TTL, and is cleaned up on download or expiry.

Run from the project root:
    uvicorn backend.main:app --reload
Then open http://127.0.0.1:8000/
"""
from __future__ import annotations

import base64
import logging
import shutil
import time
import uuid
from collections import deque
from pathlib import Path
from tempfile import mkdtemp

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import convert, fal_client, mesh_utils, mock_client
from .config import (
    ALLOWED_ORIGINS,
    GENERATOR,
    MAX_UPLOAD_BYTES,
    RATE_LIMIT_GENERATES,
    RATE_LIMIT_WINDOW_S,
    SESSION_TTL_MIN,
)

log = logging.getLogger(__name__)

_GENERATOR = {"mock": mock_client, "fal": fal_client}[GENERATOR]
_GENERATOR_ERRORS = (mock_client.MockError, fal_client.FalError)

app = FastAPI(title="CONBOART", version="0.1.0")

# CORS — only for a separately hosted frontend
if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

# --- In-memory session store (swap for Redis if you scale out) --------------
# job_id -> {"dir": Path, "created": ts}
SESSIONS: dict[str, dict] = {}

# client ip -> timestamps of recent /api/generate calls
_GENERATE_HITS: dict[str, deque[float]] = {}


def _sweep_expired() -> None:
    now = time.time()
    cutoff = now - SESSION_TTL_MIN * 60
    for jid in list(SESSIONS):
        if SESSIONS[jid]["created"] < cutoff:
            _drop(jid)
    # Drop expired rate-limit buckets
    rl_cutoff = now - RATE_LIMIT_WINDOW_S
    for ip in list(_GENERATE_HITS):
        hits = _GENERATE_HITS[ip]
        if not hits or hits[-1] < rl_cutoff:
            del _GENERATE_HITS[ip]


def _drop(job_id: str) -> None:
    sess = SESSIONS.pop(job_id, None)
    if sess:
        shutil.rmtree(sess["dir"], ignore_errors=True)


def _get_session(job_id: str) -> dict:
    """Look up a live session, expiring stale ones first."""
    _sweep_expired()
    sess = SESSIONS.get(job_id)
    if not sess:
        raise HTTPException(404, "no such session")
    return sess


def _load_model(sess: dict):
    """Load the session's canonical, unscaled model."""
    try:
        return mesh_utils.load((sess["dir"] / "model.glb").read_bytes(), "glb")
    except mesh_utils.NotAMeshError as e:
        raise HTTPException(422, str(e))


def _check_rate_limit(request: Request) -> None:
    if RATE_LIMIT_GENERATES <= 0:
        return
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    hits = _GENERATE_HITS.setdefault(ip, deque())
    while hits and hits[0] < now - RATE_LIMIT_WINDOW_S:
        hits.popleft()
    if len(hits) >= RATE_LIMIT_GENERATES:
        retry_in = int(hits[0] + RATE_LIMIT_WINDOW_S - now) + 1
        raise HTTPException(
            429,
            f"too many generations — try again in about {retry_in}s",
            headers={"Retry-After": str(retry_in)},
        )
    hits.append(now)


# --- API --------------------------------------------------------------------
@app.post("/api/generate")
async def generate(request: Request, payload: dict = Body(...)):
    """Body: { "images": [{"image_base64": "<...>", "mime": "image/png", "slot": "front"}, ...] }

    1 to 4 images. slot is one of front/back/left/right (front required for
    multi-image; ignored for single-image).
    """
    _sweep_expired()
    _check_rate_limit(request)

    raw_images = payload.get("images", [])
    if not raw_images:
        raise HTTPException(400, "images is required (1 to 4 entries)")
    if len(raw_images) > 4:
        raise HTTPException(400, "at most 4 images are supported")

    images: list[tuple[bytes, str, str]] = []
    for entry in raw_images:
        b64 = entry.get("image_base64", "")
        if not b64:
            raise HTTPException(400, "each image needs image_base64")
        try:
            image_bytes = base64.b64decode(b64.split(",")[-1])
        except Exception:
            raise HTTPException(400, "image_base64 is not valid base64")
        if len(image_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "an image exceeds the size cap")
        images.append((image_bytes, entry.get("mime", "image/png"), entry.get("slot", "front")))

    # Generate at native size
    try:
        task_id = await _GENERATOR.submit_image(images)
        task = await _GENERATOR.poll_until_done(task_id)
        glb = await _GENERATOR.download_model(task)
    except _GENERATOR_ERRORS as e:
        raise HTTPException(502, f"generation failed: {e}")

    try:
        mesh = mesh_utils.load(glb, "glb")
    except mesh_utils.NotAMeshError as e:
        raise HTTPException(502, f"generation failed: {e}")
    report = mesh_utils.printability(mesh)
    info = mesh_utils.model_info(mesh)
    mesh_utils.ensure_visible_material(mesh)

    job_id = uuid.uuid4().hex
    workdir = Path(mkdtemp(prefix="conboart_"))
    (workdir / "model.glb").write_bytes(mesh.export(file_type="glb", include_normals=True))
    SESSIONS[job_id] = {"dir": workdir, "created": time.time()}

    return {"job_id": job_id, "status": "done", "report": report, "info": info}


@app.get("/api/status/{job_id}")
def status(job_id: str):
    # Generation is synchronous, so a live job is always "done"
    _sweep_expired()
    return {"status": "done" if job_id in SESSIONS else "unknown"}


@app.get("/api/report/{job_id}")
def report(job_id: str):
    mesh = _load_model(_get_session(job_id))
    return {"report": mesh_utils.printability(mesh), "info": mesh_utils.model_info(mesh)}


@app.post("/api/cleanup/{job_id}")
def cleanup(job_id: str):
    sess = _get_session(job_id)
    mesh = _load_model(sess)
    mesh = mesh_utils.cleanup(mesh, weld=True, guarantee=True)
    (sess["dir"] / "model.glb").write_bytes(mesh.export(file_type="glb", include_normals=True))
    report = mesh_utils.printability(mesh)
    return {
        "report": report,
        "info": mesh_utils.model_info(mesh),
        "unprintable": report["verdict"] != "ok",
    }


@app.get("/api/convert/{job_id}")
def convert_endpoint(job_id: str, format: str = "stl", scale: str = "M"):
    sess = _get_session(job_id)
    mesh = _load_model(sess)
    mesh_utils.bake_scale(mesh, scale)
    try:
        data = convert.to_bytes(mesh, format)
    except NotImplementedError as e:
        raise HTTPException(501, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))

    ext = convert.suggested_extension(format)
    # Unique filename per export, never "model.glb"
    out = sess["dir"] / f"export-{uuid.uuid4().hex[:8]}.{ext}"
    mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
    with open(out, mode) as f:
        f.write(data)
    return FileResponse(out, filename=f"conboart-model.{ext}")


# --- Serve the frontend (mount last so /api/* wins) -------------------------
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
