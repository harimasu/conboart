"""Inspect the configured Hugging Face Space and (optionally) smoke-test it.

hf_client discovers the right endpoint at runtime, but Spaces change and the
discovery can guess wrong. Run this to see exactly what the Space offers, and
to confirm a real generation works before wiring it into the app.

    python -m backend.hf_probe                 # list endpoints
    python -m backend.hf_probe photo.jpg       # also generate from an image

If the endpoint it picks is wrong, pin the right one in .env:

    HF_API_NAME=/image_to_3d
"""
from __future__ import annotations

import asyncio
import sys

from .config import HF_API_NAME, HF_SPACE, HF_TOKEN


def main() -> int:
    try:
        import gradio_client  # noqa: F401
    except ImportError:
        print("gradio_client is missing. Run: pip install -r requirements.txt")
        return 1

    from . import hf_client

    print(f"Space:  {HF_SPACE}")
    print(f"Token:  {'set' if HF_TOKEN else 'NOT set (smaller anonymous quota)'}")
    print(f"Pinned: {HF_API_NAME or '(none — will auto-discover)'}\n")

    try:
        client = hf_client.make_client()
    except Exception as e:
        print(f"Could not connect: {e}")
        return 1

    api = client.view_api(print_response=False, return_format="dict") or {}
    endpoints = api.get("named_endpoints", {}) or {}
    if not endpoints:
        print("This Space exposes no named API endpoints.")
        return 1

    print("Endpoints:")
    for name, spec in endpoints.items():
        params = spec.get("parameters", []) or []
        print(f"  {name}")
        for p in params:
            label = p.get("parameter_name") or p.get("label") or "?"
            ptype = p.get("python_type", {}).get("type", "?")
            default = (
                f" = {p.get('parameter_default')!r}"
                if p.get("parameter_has_default")
                else "  (required)"
            )
            print(f"      {label}: {ptype}{default}")

    if len(sys.argv) < 2:
        print("\nPass an image path to also run a real generation.")
        return 0

    image_path = sys.argv[1]
    print(f"\nGenerating from {image_path} — this can take a few minutes...")
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
    except OSError as e:
        print(f"Could not read {image_path}: {e}")
        return 1

    try:
        glb = asyncio.run(hf_client.generate(image_bytes))
    except Exception as e:
        print(f"FAILED: {e}")
        return 1

    out = "hf_probe_output.glb"
    with open(out, "wb") as f:
        f.write(glb)
    print(f"OK — wrote {out} ({len(glb):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
