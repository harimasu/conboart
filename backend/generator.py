"""Picks which backend turns an image into a 3D model.

The rest of the app calls `generate()` and doesn't care which service answered.
Choose with GENERATOR in .env: "mock", "hf", or "meshy".
"""
from __future__ import annotations

from .config import GENERATOR
from .errors import GenerationError

BACKENDS = ("mock", "hf", "meshy")


async def generate(image_bytes: bytes, mime: str = "image/png") -> bytes:
    """Return GLB bytes for an image. Raises GenerationError on failure."""
    if GENERATOR == "mock":
        return _mock()
    if GENERATOR == "hf":
        from . import hf_client

        return await hf_client.generate(image_bytes, mime)
    if GENERATOR == "meshy":
        from . import meshy_client

        return await meshy_client.generate(image_bytes, mime)
    raise GenerationError(
        f"unknown GENERATOR {GENERATOR!r}; expected one of {', '.join(BACKENDS)}"
    )


def _mock() -> bytes:
    """A sample sphere, so the pipeline can run offline and for free."""
    import trimesh  # lazy import

    return trimesh.creation.icosphere(subdivisions=3, radius=1.0).export(file_type="glb")
