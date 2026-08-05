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

from . import convert, mesh_utils, meshy_client
from .config import (
    ALLOWED_ORIGINS,
    MAX_UPLOAD_BYTES,
    RATE_LIMIT_GENERATES,
    RATE_LIMIT_WINDOW_S,
    SESSION_TTL_MIN,
)

log = logging.getLogger(__name__)

app = FastAPI(title="CONBOART", version="0.1.0")

# The backend serves its own frontend, so the browser calls /api/* same-origin
# and needs no CORS headers. Only opt in when ALLOWED_ORIGINS names real hosts —
# a wildcard here would let any page on the internet spend Meshy credits from a
# visitor's browser.
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
    # Drop rate-limit buckets whose window has fully passed, so the table
    # doesn't grow one entry per IP that ever hit the endpoint.
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
    """Look up a live session, expiring stale ones first.

    Sweeping here as well as in /api/generate matters: an idle instance that
    never generates again would otherwise keep every temp directory forever.
    """
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
    """Body: { "image_base64": "<...>", "mime": "image/png" }"""
    _sweep_expired()
    _check_rate_limit(request)

    b64 = payload.get("image_base64", "")
    if not b64:
        raise HTTPException(400, "image_base64 is required")
    try:
        image_bytes = base64.b64decode(b64.split(",")[-1])
    except Exception:
        raise HTTPException(400, "image_base64 is not valid base64")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "image exceeds the size cap")

    # Generate (native size) -> cleanup -> printability
    try:
        task_id = await meshy_client.submit_image(image_bytes, payload.get("mime", "image/png"))
        task = await meshy_client.poll_until_done(task_id)
        glb = await meshy_client.download_model(task)
    except meshy_client.MeshyError as e:
        raise HTTPException(502, f"generation failed: {e}")

    try:
        mesh = mesh_utils.load(glb, "glb")
    except mesh_utils.NotAMeshError as e:
        raise HTTPException(502, f"generation failed: {e}")
    mesh_utils.cleanup(mesh)
    report = mesh_utils.printability(mesh)
    info = mesh_utils.model_info(mesh)

    job_id = uuid.uuid4().hex
    workdir = Path(mkdtemp(prefix="conboart_"))
    (workdir / "model.glb").write_bytes(mesh.export(file_type="glb"))
    SESSIONS[job_id] = {"dir": workdir, "created": time.time()}

    return {"job_id": job_id, "status": "done", "report": report, "info": info}


@app.get("/api/status/{job_id}")
def status(job_id: str):
    # In this simple version generation is synchronous, so a live job is "done".
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
    mesh_utils.cleanup(mesh)
    (sess["dir"] / "model.glb").write_bytes(mesh.export(file_type="glb"))
    # re-run printability after cleanup
    return {"report": mesh_utils.printability(mesh), "info": mesh_utils.model_info(mesh)}


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
    # A unique name per request, never "model.glb": writing the scale-baked
    # result back over the canonical source would corrupt it (the viewer
    # fetches format=glb on every load), and FileResponse streams this file
    # after the handler returns, so a fixed name could also be rewritten by a
    # concurrent request mid-download.
    out = sess["dir"] / f"export-{uuid.uuid4().hex[:8]}.{ext}"
    mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
    with open(out, mode) as f:
        f.write(data)
    return FileResponse(out, filename=f"conboart-model.{ext}")


# --- Serve the frontend (mount last so /api/* wins) -------------------------
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
