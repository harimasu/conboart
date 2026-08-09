"""fal.ai queue client — Hunyuan3D v3.1 (submit / poll / download)."""
from __future__ import annotations

import asyncio
import base64
import logging
import time

import httpx

from .config import FAL_KEY, POLL_INTERVAL_S, POLL_TIMEOUT_S

log = logging.getLogger(__name__)

FAL_BASE_URL = "https://queue.fal.run"
SINGLE_MODEL = "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d" #model used for single image
MULTI_MODEL = "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d" #model used for multi view
_SLOT_FIELDS = {"back": "back_image_url", "left": "left_image_url", "right": "right_image_url"}
_MULTI_FACE_COUNT_MIN = 40000  # pro model's documented minimum


class FalError(RuntimeError):
    pass


def _headers() -> dict:
    return {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}


def _fail(stage: str, r: httpx.Response) -> FalError:
    log.error("fal %s failed: %s %s", stage, r.status_code, r.text[:2000])
    return FalError(f"{stage} failed (upstream status {r.status_code})")


def _data_uri(image_bytes: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"


async def submit_image(images: list[tuple[bytes, str, str]]) -> tuple[str, str]:
    """Submit 1-4 (bytes, mime, slot) images, slot in {front, back, left, right}."""
    by_slot = {slot: (b, m) for b, m, slot in images}
    front_bytes, front_mime = by_slot.get("front", images[0][:2])

    others = {slot: img for slot, img in by_slot.items() if slot != "front"}
    if not others:
        model = SINGLE_MODEL
        payload = {"input_image_url": _data_uri(front_bytes, front_mime), "enable_pbr": False}
    else:
        model = MULTI_MODEL
        payload = {"input_image_url": _data_uri(front_bytes, front_mime), "enable_pbr": False}
        for slot, (b, m) in others.items():
            field = _SLOT_FIELDS.get(slot)
            if field:
                payload[field] = _data_uri(b, m)
        payload["face_count"] = _MULTI_FACE_COUNT_MIN

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{FAL_BASE_URL}/{model}", headers=_headers(), json=payload)
        if r.status_code >= 400:
            raise _fail("submit", r)
        data = r.json()
        try:
            return data["status_url"], data["response_url"]
        except KeyError as e:
            log.error("unexpected fal submit response: %s", r.text[:2000])
            raise FalError("submit returned an unexpected response shape") from e


async def poll_until_done(task: tuple[str, str]) -> str:
    """Poll until COMPLETED. Returns the response_url for download_model."""
    status_url, response_url = task
    deadline = time.time() + POLL_TIMEOUT_S
    last_status = "unknown"
    async with httpx.AsyncClient(timeout=30) as client:
        while time.time() < deadline:
            r = await client.get(status_url, headers=_headers())
            if r.status_code >= 400:
                raise _fail("poll", r)
            data = r.json()
            status = data.get("status")
            last_status = status
            if status == "COMPLETED":
                return response_url
            if status == "ERROR":
                log.error("fal task at %s ended as ERROR: %s", status_url, data)
                raise FalError("generation error")
            await asyncio.sleep(POLL_INTERVAL_S)
    raise FalError(f"generation timed out after {POLL_TIMEOUT_S}s (last status: {last_status})")


async def download_model(response_url: str) -> bytes:
    """Fetch the result payload, then download the GLB it points to."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(response_url, headers=_headers())
        if r.status_code >= 400:
            raise _fail("result", r)
        result = r.json()
    try:
        glb_url = result["model_urls"]["glb"]["url"]
    except (KeyError, TypeError) as e:
        log.error("completed task carried no model_urls.glb.url: %s", result)
        raise FalError("the finished task did not include a GLB url") from e

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.get(glb_url)
        if r.status_code >= 400:
            raise _fail("download", r)
        return r.content
