"""Thin wrapper around the Meshy AI image-to-3D API.

Meshy is asynchronous: you submit an image, receive a task id, poll until the
task succeeds, then download the resulting model. This module isolates all of
that so the rest of the app doesn't care whether it's talking to Meshy or to
the local MOCK generator.

Endpoints confirmed against https://docs.meshy.ai/en/api/image-to-3d.

This module always talks to the real service. Offline/sample generation lives
in generator.py, so there is exactly one switch (GENERATOR) rather than a mock
flag buried in each backend.
"""
from __future__ import annotations

import asyncio
import base64
import time

import httpx

from .config import (
    MESHY_API_KEY,
    MESHY_BASE_URL,
    POLL_INTERVAL_S,
    POLL_TIMEOUT_S,
)
from .errors import GenerationError


class MeshyError(GenerationError):
    pass


def _headers() -> dict:
    return {"Authorization": f"Bearer {MESHY_API_KEY}"}


async def _request_with_retry(
    client: httpx.AsyncClient, method: str, url: str, *, max_retries: int = 5, **kwargs
) -> httpx.Response:
    """Issue a request, retrying on 429 (rate limit / queue full) with backoff.

    Network failures (timeouts, connection errors) and non-retryable error
    statuses are raised as MeshyError so callers only need to catch one thing.
    """
    backoff = 1.0
    for attempt in range(max_retries + 1):
        try:
            r = await client.request(method, url, **kwargs)
        except httpx.HTTPError as e:
            raise MeshyError(f"network error calling Meshy: {e}") from e

        if r.status_code == 429 and attempt < max_retries:
            retry_after = r.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else backoff
            await asyncio.sleep(wait)
            backoff = min(backoff * 2, 30)
            continue

        if r.status_code >= 400:
            raise MeshyError(f"{method} {url} failed: {r.status_code} {r.text}")
        return r

    raise MeshyError(f"{method} {url}: still rate-limited after {max_retries} retries")


async def generate(image_bytes: bytes, mime: str = "image/png") -> bytes:
    """Submit -> poll -> download, as one call. Returns GLB bytes."""
    task_id = await submit_image(image_bytes, mime)
    task = await poll_until_done(task_id)
    return await download_model(task)


async def submit_image(image_bytes: bytes, mime: str = "image/png") -> str:
    """Submit an image and return a task id.

    Because CONBOART stores nothing, the image is sent inline as a base64 data
    URI rather than a public URL.
    """
    data_uri = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
    payload = {
        "image_url": data_uri,
        "enable_pbr": True,
        # add prompt hints / topology / target polycount here as needed
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await _request_with_retry(
            client,
            "POST",
            f"{MESHY_BASE_URL}/openapi/v1/image-to-3d",
            headers=_headers(),
            json=payload,
        )
        return r.json()["result"]  # Meshy returns the task id under "result"


async def poll_until_done(task_id: str) -> dict:
    """Poll the task until it succeeds or fails. Returns the task JSON."""
    deadline = time.time() + POLL_TIMEOUT_S
    async with httpx.AsyncClient(timeout=30) as client:
        while time.time() < deadline:
            r = await _request_with_retry(
                client,
                "GET",
                f"{MESHY_BASE_URL}/openapi/v1/image-to-3d/{task_id}",
                headers=_headers(),
            )
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
    url = task["model_urls"]["glb"]
    async with httpx.AsyncClient(timeout=120) as client:
        r = await _request_with_retry(client, "GET", url)
        return r.content
