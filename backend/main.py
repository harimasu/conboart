"""CONBOART backend — FastAPI.

Per-session, nothing stored: each generation lives in a temp directory keyed by
a job id with a TTL, and is cleaned up on download or expiry.

Run from the project root:
    uvicorn backend.main:app --reload
Then open http://127.0.0.1:8000/
"""
from __future__ import annotations

import base64
import time
import uuid
from pathlib import Path
from tempfile import mkdtemp

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import convert, mesh_utils, meshy_client
from .config import MAX_UPLOAD_BYTES, SESSION_TTL_MIN

app = FastAPI(title="CONBOART", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# --- In-memory session store (swap for Redis if you scale out) --------------
# job_id -> {"dir": Path, "glb": bytes, "created": ts, "active": bool}
SESSIONS: dict[str, dict] = {}


def _sweep_expired() -> None:
    cutoff = time.time() - SESSION_TTL_MIN * 60
    for jid in list(SESSIONS):
        if SESSIONS[jid]["created"] < cutoff:
            _drop(jid)


def _drop(job_id: str) -> None:
    sess = SESSIONS.pop(job_id, None)
    if sess:
        import shutil

        shutil.rmtree(sess["dir"], ignore_errors=True)


# --- API --------------------------------------------------------------------
@app.post("/api/generate")
async def generate(payload: dict = Body(...)):
    """Body: { "image_base64": "<...>", "mime": "image/png" }"""
    _sweep_expired()

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

    mesh = mesh_utils.load(glb, "glb")
    mesh_utils.cleanup(mesh)
    report = mesh_utils.printability(mesh)
    info = mesh_utils.model_info(mesh)

    job_id = uuid.uuid4().hex[:12]
    workdir = Path(mkdtemp(prefix="conboart_"))
    (workdir / "model.glb").write_bytes(mesh.export(file_type="glb"))
    SESSIONS[job_id] = {"dir": workdir, "created": time.time(), "active": True}

    return {"job_id": job_id, "status": "done", "report": report, "info": info}


@app.get("/api/status/{job_id}")
def status(job_id: str):
    # In this simple version generation is synchronous, so a live job is "done".
    return {"status": "done" if job_id in SESSIONS else "unknown"}


@app.get("/api/report/{job_id}")
def report(job_id: str):
    sess = SESSIONS.get(job_id)
    if not sess:
        raise HTTPException(404, "no such session")
    mesh = mesh_utils.load((sess["dir"] / "model.glb").read_bytes(), "glb")
    return {"report": mesh_utils.printability(mesh), "info": mesh_utils.model_info(mesh)}


@app.post("/api/cleanup/{job_id}")
def cleanup(job_id: str):
    sess = SESSIONS.get(job_id)
    if not sess:
        raise HTTPException(404, "no such session")
    mesh = mesh_utils.load((sess["dir"] / "model.glb").read_bytes(), "glb")
    mesh_utils.cleanup(mesh)
    (sess["dir"] / "model.glb").write_bytes(mesh.export(file_type="glb"))
    # re-run printability after cleanup
    return {"report": mesh_utils.printability(mesh), "info": mesh_utils.model_info(mesh)}


@app.get("/api/convert/{job_id}")
def convert_endpoint(job_id: str, format: str = "stl", scale: str = "M"):
    sess = SESSIONS.get(job_id)
    if not sess:
        raise HTTPException(404, "no such session")
    mesh = mesh_utils.load((sess["dir"] / "model.glb").read_bytes(), "glb")
    mesh_utils.bake_scale(mesh, scale)
    try:
        data = convert.to_bytes(mesh, format)
    except NotImplementedError as e:
        raise HTTPException(501, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))

    ext = convert.suggested_extension(format)
    out = sess["dir"] / f"model.{ext}"
    mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
    with open(out, mode) as f:
        f.write(data)
    return FileResponse(out, filename=f"conboart-model.{ext}")


# --- Serve the frontend (mount last so /api/* wins) -------------------------
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
