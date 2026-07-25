"""Shared exception types.

Lives in its own module so the generator backends (meshy_client, hf_client) and
the dispatcher (generator) can share a base error without importing each other.
"""
from __future__ import annotations


class GenerationError(RuntimeError):
    """Any failure while turning an image into a 3D model.

    main.py catches this one type and turns it into a 502, so backends don't
    each need special handling at the route layer.
    """
