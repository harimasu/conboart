"""Vercel entrypoint. Vercel's Python runtime looks for an ASGI `app` in
files under /api — this just re-exports the real FastAPI app so the
backend package layout doesn't have to change.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.main import app  # noqa: E402,F401
