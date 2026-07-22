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
import time

import httpx

from .config import (
    MESHY_API_KEY,
    MESHY_BASE_URL,
    MESHY_MOCK,
    POLL_INTERVAL_S,
    POLL_TIMEOUT_S,
)


class MeshyError(RuntimeError):
    pass


def _headers() -> dict:
    return {"Authorization": f"Bearer {MESHY_API_KEY}"}


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
        "enable_pbr": True,
        # add prompt hints / topology / target polycount here as needed
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{MESHY_BASE_URL}/v1/image-to-3d",
            headers=_headers(),
            json=payload,
        )
        if r.status_code >= 400:
            raise MeshyError(f"submit failed: {r.status_code} {r.text}")
        return r.json()["result"]  # Meshy returns the task id under "result"


async def poll_until_done(task_id: str) -> dict:
    """Poll the task until it succeeds or fails. Returns the task JSON."""
    if MESHY_MOCK:
        await asyncio.sleep(1.0)
        return {"status": "SUCCEEDED", "model_urls": {"glb": "mock://model.glb"}}

    deadline = time.time() + POLL_TIMEOUT_S
    async with httpx.AsyncClient(timeout=30) as client:
        while time.time() < deadline:
            r = await client.get(
                f"{MESHY_BASE_URL}/v1/image-to-3d/{task_id}",
                headers=_headers(),
            )
            if r.status_code >= 400:
                raise MeshyError(f"poll failed: {r.status_code} {r.text}")
            data = r.json()
            status = data.get("status")
            if status == "SUCCEEDED":
                return data
            if status in {"FAILED", "CANCELED"}:
                raise MeshyError(f"generation {status}: {data}")
            await asyncio.sleep(POLL_INTERVAL_S)
    raise MeshyError("generation timed out")


async def download_model(task: dict) -> bytes:
    """Download the generated GLB and return its bytes."""
    if MESHY_MOCK:
        # Build a simple sample mesh locally so the pipeline can run offline.
        import trimesh  # lazy import

        mesh = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
        return mesh.export(file_type="glb")

    url = task["model_urls"]["glb"]
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.get(url)
        if r.status_code >= 400:
            raise MeshyError(f"download failed: {r.status_code}")
        return r.content
