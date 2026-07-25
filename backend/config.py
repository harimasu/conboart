"""Configuration and limits for CONBOART.

Values are read from environment variables (see .env.example). Nothing here is
secret except the Meshy API key, which must come from the environment and must
never be committed to source control.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Meshy AI ---------------------------------------------------------------
# Get a key from https://www.meshy.ai (a free test-mode key works for wiring
# things up without spending credits). Leave unset to run in MOCK mode.
MESHY_API_KEY = os.getenv("MESHY_API_KEY", "")
MESHY_BASE_URL = os.getenv("MESHY_BASE_URL", "https://api.meshy.ai")

# When true (or when no API key is set), the backend fabricates a sample model
# instead of calling Meshy — handy for local development before subscribing.
MESHY_MOCK = os.getenv("MESHY_MOCK", "").lower() in {"1", "true", "yes"} or not MESHY_API_KEY

# --- Hugging Face (free, open-source generation) -----------------------------
# TRELLIS is MIT-licensed and its public demo Space can be called as an API,
# which is enough to test real generation without paying for Meshy. A free
# token from https://huggingface.co/settings/tokens raises the daily quota;
# without one you share a much smaller anonymous pool.
HF_SPACE = os.getenv("HF_SPACE", "trellis-community/TRELLIS")
HF_TOKEN = os.getenv("HF_TOKEN", "")
# Optional: pin the endpoint instead of discovering it (see hf_probe.py).
HF_API_NAME = os.getenv("HF_API_NAME", "")

# --- Which generator to use -------------------------------------------------
#   mock  — built-in sample sphere; offline, instant, costs nothing
#   hf    — free open-source TRELLIS via a Hugging Face Space
#   meshy — the paid Meshy API
# Defaults preserve the old behaviour: mock unless a Meshy key is configured.
GENERATOR = os.getenv("GENERATOR", "").strip().lower() or ("mock" if MESHY_MOCK else "meshy")

# --- Guard rails ------------------------------------------------------------
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
SESSION_TTL_MIN = int(os.getenv("SESSION_TTL_MIN", "30"))
POLL_TIMEOUT_S = int(os.getenv("POLL_TIMEOUT_S", "180"))
POLL_INTERVAL_S = float(os.getenv("POLL_INTERVAL_S", "3"))

# --- Auto-scale presets (longest bounding-box dimension, in millimetres) ----
# Tune these to your target printer's bed size.
SCALE_PRESETS_MM = {"S": 50.0, "M": 100.0, "L": 150.0}

# --- Formats ----------------------------------------------------------------
# Tier 1 mesh formats handled natively by Trimesh.
MESH_FORMATS = {"stl", "obj", "ply", "glb", "gltf", "off", "dae"}
# Tier 3 CAD formats — approximate, require FreeCAD/OpenCASCADE (not built-in).
CAD_FORMATS = {"step", "stp", "iges"}
