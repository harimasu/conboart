"""Free image-to-3D generation via a public Hugging Face Space (TRELLIS).

Why this exists: Meshy is a paid service. TRELLIS is an MIT-licensed open
model, and its public demo Space can be called as an API for free, which is
enough to test the real pipeline before subscribing to anything.

Two things make this trickier than the Meshy client:

1. Every Gradio Space exposes its own endpoint names and parameter lists, and
   they change when the Space owner updates the demo. So instead of hardcoding
   a call signature, we read the Space's API at runtime (`view_api`) and build
   the arguments from what it actually declares. Set HF_API_NAME to skip
   discovery and pin a specific endpoint.

2. TRELLIS-style Spaces are two-step: one endpoint builds the 3D
   representation and returns an opaque state, a second extracts the GLB from
   it. We detect that and run both.

Quota: anonymous callers share a small daily pool. Set HF_TOKEN (a free
huggingface.co account token) for your own, larger allowance.
"""
from __future__ import annotations

import asyncio
import mimetypes
import os
import tempfile

from .config import HF_API_NAME, HF_SPACE, HF_TOKEN
from .errors import GenerationError

# Endpoint names worth trying first, most specific to least, when the Space
# doesn't tell us plainly which one does image -> 3D. Includes the name used
# by trellis-community/TRELLIS itself, which does the whole pipeline in one
# call rather than needing a separate extract step.
_GENERATE_CANDIDATES = (
    "/generate_and_extract_glb",
    "/image_to_3d",
    "/generate",
    "/process",
    "/run",
    "/predict",
)

# Endpoints that turn a TRELLIS state into a downloadable mesh, for Spaces
# that split generation from extraction into two calls.
_EXTRACT_CANDIDATES = ("/extract_glb", "/extract_mesh", "/download_glb")

# Endpoint name fragments that take an image but aren't the real generator —
# skip these when falling back to "any endpoint with an image parameter", or
# a preprocessing step gets called instead of the actual pipeline.
_NOT_A_GENERATOR = ("preprocess", "session", "seed")

_MODEL_SUFFIXES = (".glb", ".gltf", ".obj", ".ply", ".stl")


async def generate(image_bytes: bytes, mime: str = "image/png") -> bytes:
    """Return GLB bytes for the given image. Raises GenerationError."""
    # gradio_client is blocking, so keep it off the event loop.
    return await asyncio.to_thread(_generate_sync, image_bytes, mime)


def _generate_sync(image_bytes: bytes, mime: str) -> bytes:
    try:
        from gradio_client import Client, handle_file
    except ImportError as e:  # pragma: no cover - depends on install extras
        raise GenerationError(
            "gradio_client is not installed. Run: pip install -r requirements.txt"
        ) from e

    suffix = mimetypes.guess_extension(mime) or ".png"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(image_bytes)
        tmp.close()

        client = make_client()
        endpoints = _named_endpoints(client)

        # Some Spaces allocate per-visitor state before any real work.
        if "/start_session" in endpoints:
            try:
                client.predict(api_name="/start_session")
            except Exception:
                pass  # best-effort; not all Spaces require it

        gen_name = HF_API_NAME or _pick(endpoints, _GENERATE_CANDIDATES, needs_image=True)
        if not gen_name:
            raise GenerationError(
                f"no image-to-3D endpoint found on {HF_SPACE!r}. Available: "
                f"{sorted(endpoints)}. Pin one with HF_API_NAME in .env."
            )

        result = _call(client, endpoints, gen_name, image_path=tmp.name)

        path = _model_path(result)
        if path:
            return _read(path)

        # No mesh yet: this is a two-step Space, so feed the state to an
        # extract endpoint.
        extract_name = _pick(endpoints, _EXTRACT_CANDIDATES, needs_image=False)
        if not extract_name:
            raise GenerationError(
                f"{gen_name} on {HF_SPACE!r} returned no model file and no "
                f"extract endpoint was found. Available: {sorted(endpoints)}."
            )

        extracted = _call(client, endpoints, extract_name)
        path = _model_path(extracted)
        if not path:
            raise GenerationError(
                f"{extract_name} on {HF_SPACE!r} returned no model file "
                f"(got {type(extracted).__name__})."
            )
        return _read(path)
    finally:
        os.unlink(tmp.name)


def make_client():
    """Connect to the configured Space.

    The auth argument was renamed `hf_token` -> `token` in gradio_client, so
    pick whichever this install actually accepts.
    """
    import inspect

    from gradio_client import Client

    kwargs = {"verbose": False}
    if HF_TOKEN:
        params = inspect.signature(Client.__init__).parameters
        kwargs["token" if "token" in params else "hf_token"] = HF_TOKEN
    try:
        return Client(HF_SPACE, **kwargs)
    except Exception as e:
        raise GenerationError(f"could not reach Space {HF_SPACE!r}: {e}") from e


def _named_endpoints(client) -> dict:
    """view_api()'s silence-the-printout kwarg has changed names across
    gradio_client versions (`print_response` -> `print_info`), so pick
    whichever this install actually declares.
    """
    import inspect

    kwargs = {"return_format": "dict"}
    params = inspect.signature(client.view_api).parameters
    for name in ("print_info", "print_response"):
        if name in params:
            kwargs[name] = False
            break

    try:
        api = client.view_api(**kwargs) or {}
    except Exception as e:
        raise GenerationError(f"could not read the API of {HF_SPACE!r}: {e}") from e
    return api.get("named_endpoints", {}) or {}


def _pick(endpoints: dict, candidates: tuple[str, ...], *, needs_image: bool) -> str | None:
    """Choose an endpoint: preferred names first, then any plausible match."""
    for name in candidates:
        if name in endpoints:
            return name
    if needs_image:
        for name, spec in endpoints.items():
            if any(bad in name for bad in _NOT_A_GENERATOR):
                continue
            if _image_param_index(spec) is not None:
                return name
    return None


def _image_param_index(spec: dict) -> int | None:
    """Index of the first parameter that takes an image/file, if any."""
    for i, p in enumerate(spec.get("parameters", []) or []):
        blob = " ".join(
            str(p.get(k, "")) for k in ("python_type", "type", "component", "label")
        ).lower()
        if "filepath" in blob or "image" in blob or "file" in blob:
            return i
    return None


def _call(client, endpoints: dict, api_name: str, image_path: str | None = None):
    """Invoke an endpoint, filling declared defaults for every argument.

    Spaces routinely declare a dozen tuning parameters (guidance strength,
    sampling steps, seed...). We only care about the image, so everything else
    is sent as the default the Space itself advertises.
    """
    from gradio_client import handle_file

    spec = endpoints.get(api_name, {})
    params = spec.get("parameters", []) or []
    img_at = _image_param_index(spec) if image_path else None

    args = []
    for i, p in enumerate(params):
        if i == img_at:
            args.append(handle_file(image_path))
        elif p.get("parameter_has_default"):
            args.append(p.get("parameter_default"))
        else:
            args.append(_fallback_value(p))

    try:
        return client.predict(*args, api_name=api_name)
    except Exception as e:
        raise GenerationError(f"{api_name} on {HF_SPACE!r} failed: {e}") from e


def _fallback_value(param: dict):
    """A best-guess value for a required parameter with no declared default."""
    t = str(param.get("python_type", {}).get("type", "")).lower()
    if "float" in t or "int" in t or "number" in t:
        return 0
    if "bool" in t:
        return False
    if "list" in t or "dict" in t:
        return None
    return ""


def _model_path(result) -> str | None:
    """Dig a .glb/.obj/... path out of whatever shape the Space returned."""
    if isinstance(result, str):
        return result if result.lower().endswith(_MODEL_SUFFIXES) else None
    if isinstance(result, dict):
        for key in ("path", "url", "name", "video", "file"):
            found = _model_path(result.get(key))
            if found:
                return found
        return None
    if isinstance(result, (list, tuple)):
        for item in result:
            found = _model_path(item)
            if found:
                return found
    return None


def _read(path: str) -> bytes:
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as e:
        raise GenerationError(f"could not read the generated model: {e}") from e
