"""Local sample-model generator for GENERATOR=mock — no network, no API key."""
from __future__ import annotations

import asyncio


class MockError(RuntimeError):
    pass


async def submit_image(images: list[tuple[bytes, str, str]]) -> None:
    return None


async def poll_until_done(task: None) -> None:
    await asyncio.sleep(1.0)
    return None


async def download_model(task: None) -> bytes:
    import trimesh  # lazy import

    mesh = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
    return mesh.export(file_type="glb")
