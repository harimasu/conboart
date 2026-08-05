"""Thin wrapper around the Meshy AI image-to-3D API.

Meshy is asynchronous: you submit an image, receive a task id, poll until the
task succeeds, then download the resulting model. This module isolates all of
that so the rest of the app doesn't care whether it's talking to Meshy or to
the local MOCK generator.

IMPORTANT: confirm the exact endpoints, request/response shapes, and limits
against Meshy's official docs before relying on this in production — the paths
below follow the documented v1 image-to-3D flow but may change.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time

import httpx

from .config import (
    MESHY_API_KEY,
    MESHY_BASE_URL,
    MESHY_MOCK,
    POLL_INTERVAL_S,
    POLL_TIMEOUT_S,
)


log = logging.getLogger(__name__)


class MeshyError(RuntimeError):
    pass


def _headers() -> dict:
    return {"Authorization": f"Bearer {MESHY_API_KEY}"}


def _fail(stage: str, r: httpx.Response) -> MeshyError:
    """Log the upstream body for debugging, but keep it out of the exception.

    The message ends up in the HTTP response the browser sees, and Meshy's
    error bodies can echo request detail we would rather not hand to a caller.
    """
    log.error("meshy %s failed: %s %s", stage, r.status_code, r.text[:2000])
    return MeshyError(f"{stage} failed (upstream status {r.status_code})")


async def submit_image(image_bytes: bytes, mime: str = "image/png") -> str:
    """Submit an image and return a task id.

    Because CONBOART stores nothing, the image is sent inline as a base64 data
    URI rather than a public URL.
    """
    if MESHY_MOCK:
        return f"mock-{int(time.time()*1000)}"

    data_uri = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
    payload = {
        "image_url": data_uri,
        "ai_model": "latest",
        "enable_pbr": True,
        # add prompt hints / topology / target polycount here as needed
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{MESHY_BASE_URL}/openapi/v1/image-to-3d",
            headers=_headers(),
            json=payload,
        )
        if r.status_code >= 400:
            raise _fail("submit", r)
        try:
            task_id = r.json()["result"]  # Meshy returns the task id under "result"
        except (ValueError, KeyError, TypeError) as e:
            log.error("unexpected submit response: %s", r.text[:2000])
            raise MeshyError("submit returned an unexpected response shape") from e
        return task_id


async def poll_until_done(task_id: str) -> dict:
    """Poll the task until it succeeds or fails. Returns the task JSON."""
    if MESHY_MOCK:
        await asyncio.sleep(1.0)
        return {"status": "SUCCEEDED", "model_urls": {"glb": "mock://model.glb"}}

    deadline = time.time() + POLL_TIMEOUT_S
    last_status, last_progress = "unknown", None
    async with httpx.AsyncClient(timeout=30) as client:
        while time.time() < deadline:
            r = await client.get(
                f"{MESHY_BASE_URL}/openapi/v1/image-to-3d/{task_id}",
                headers=_headers(),
            )
            if r.status_code >= 400:
                raise _fail("poll", r)
            data = r.json()
            status = data.get("status")
            last_status, last_progress = status, data.get("progress")
            if status == "SUCCEEDED":
                return data
            if status in {"FAILED", "CANCELED"}:
                log.error("meshy task %s ended as %s: %s", task_id, status, data)
                raise MeshyError(f"generation {status.lower()}")
            await asyncio.sleep(POLL_INTERVAL_S)
    # Distinguish "still going, just slow" from "actually stuck" — Meshy's
    # own progress percentage says which, rather than a bare opaque timeout.
    raise MeshyError(
        f"generation timed out after {POLL_TIMEOUT_S}s "
        f"(last status: {last_status}, progress: {last_progress}%)"
    )


async def download_model(task: dict) -> bytes:
    """Download the generated GLB and return its bytes."""
    if MESHY_MOCK:
        # Build a simple sample mesh locally so the pipeline can run offline.
        import trimesh  # lazy import

        mesh = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
        return mesh.export(file_type="glb")

    try:
        url = task["model_urls"]["glb"]
    except (KeyError, TypeError) as e:
        log.error("succeeded task carried no glb url: %s", task)
        raise MeshyError("the finished task did not include a GLB url") from e

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.get(url)
        if r.status_code >= 400:
            raise _fail("download", r)
        return r.content
