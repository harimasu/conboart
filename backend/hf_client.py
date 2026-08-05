"""Thin wrapper around the free TRELLIS Hugging Face Space (image-to-3D).

HF_SPACE's default, "trellis-community/TRELLIS", exposes a two-step Gradio
pipeline (confirmed via `python -m backend.hf_probe`):

    preprocess_image(image) -> image_prompt                 # crop/center
    generate_and_extract_glb(image, ...) -> (video, model, glb)  # the rest

Forks vary — some split generation and GLB extraction into separate calls
instead of one. If HF_API_NAME is unset and /generate_and_extract_glb isn't
found, run the probe to see what the configured Space actually calls things
and set HF_API_NAME to the real generation endpoint.

Unlike Meshy's async submit/poll/download API, a Gradio call blocks until the
result is ready. To keep the same three-call shape main.py uses for every
generator, the blocking work happens inside submit_image (off the event loop
via asyncio.to_thread) and poll_until_done/download_model just unwrap it.
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import tempfile
from pathlib import Path

from .config import HF_API_NAME, HF_SPACE, HF_TOKEN

log = logging.getLogger(__name__)

# TRELLIS defaults, matching the reference app's UI sliders.
_SS_GUIDANCE_STRENGTH = 7.5
_SS_SAMPLING_STEPS = 12
_SLAT_GUIDANCE_STRENGTH = 3.0
_SLAT_SAMPLING_STEPS = 12
_MESH_SIMPLIFY = 0.95
_TEXTURE_SIZE = 1024


class HFError(RuntimeError):
    pass


_client = None


def _get_client():
    """Lazily create (and cache) the gradio_client.Client for HF_SPACE."""
    global _client
    if _client is None:
        try:
            from gradio_client import Client
        except ImportError as e:
            raise HFError(
                "gradio_client is not installed — add it to requirements.txt "
                "and pip install it to use GENERATOR=hf"
            ) from e
        _client = Client(HF_SPACE, token=HF_TOKEN or None)
    return _client


def _generate_sync(image_bytes: bytes, mime: str) -> Path:
    from gradio_client import handle_file

    client = _get_client()

    # The reference app creates a per-session temp dir (keyed by session_hash)
    # in a demo.load() handler, which a browser fires automatically but a bare
    # API client never does. Without it, the space's own file-save calls fail
    # server-side with a bare, detail-stripped FileNotFoundError. Mirror what
    # the browser does by calling it explicitly before the pipeline.
    try:
        client.predict(api_name="/start_session")
    except Exception as e:
        log.warning("hf start_session unavailable (%s); continuing without it", e)

    suffix = mimetypes.guess_extension(mime) or ".png"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(image_bytes)
        src_path = f.name

    try:
        try:
            processed_path = client.predict(
                handle_file(src_path), api_name="/preprocess_image"
            )
            image_input = handle_file(processed_path)
        except Exception as e:
            # Some forks skip preprocessing or name it differently — fall back
            # to the raw upload rather than failing the whole generation.
            log.warning("hf preprocess_image unavailable (%s); using raw upload", e)
            image_input = handle_file(src_path)

        _video, _model, glb_path = client.predict(
            image=image_input,
            multiimages=[],
            seed=0,
            ss_guidance_strength=_SS_GUIDANCE_STRENGTH,
            ss_sampling_steps=_SS_SAMPLING_STEPS,
            slat_guidance_strength=_SLAT_GUIDANCE_STRENGTH,
            slat_sampling_steps=_SLAT_SAMPLING_STEPS,
            multiimage_algo="stochastic",
            mesh_simplify=_MESH_SIMPLIFY,
            texture_size=_TEXTURE_SIZE,
            api_name=HF_API_NAME or "/generate_and_extract_glb",
        )
    finally:
        Path(src_path).unlink(missing_ok=True)

    if not glb_path:
        raise HFError("the space returned no GLB file")
    return Path(glb_path)


async def submit_image(image_bytes: bytes, mime: str = "image/png") -> Path:
    try:
        return await asyncio.to_thread(_generate_sync, image_bytes, mime)
    except HFError:
        raise
    except Exception as e:
        log.exception("hf generation failed")
        detail = str(e) or type(e).__name__
        raise HFError(f"Hugging Face generation failed: {detail}") from e


async def poll_until_done(task: Path) -> Path:
    # The Space call above already blocks until the model is ready.
    return task


async def download_model(task: Path) -> bytes:
    return task.read_bytes()
