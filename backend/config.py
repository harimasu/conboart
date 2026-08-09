"""Configuration and limits for CONBOART. Read from environment (see .env.example)."""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Generator selection: mock / fal — falls back to mock if unrecognized
GENERATOR = os.getenv("GENERATOR", "mock").strip().lower()
if GENERATOR not in {"mock", "fal"}:
    GENERATOR = "mock"

# --- fal.ai (only used when GENERATOR=fal) -----------------------------------
# Get a key from https://fal.ai/dashboard/keys.
FAL_KEY = os.getenv("FAL_KEY", "")

# --- Guard rails ------------------------------------------------------------
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
SESSION_TTL_MIN = int(os.getenv("SESSION_TTL_MIN", "30"))
POLL_TIMEOUT_S = int(os.getenv("POLL_TIMEOUT_S", "600"))
POLL_INTERVAL_S = float(os.getenv("POLL_INTERVAL_S", "3"))

# --- CORS (only for a separately hosted frontend) ---------------------------
# Example: ALLOWED_ORIGINS=https://conboart.example.com,https://staging.example.com
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
]

# --- Rate limiting (in-process, per-worker) ----------------------------------
RATE_LIMIT_GENERATES = int(os.getenv("RATE_LIMIT_GENERATES", "0"))
RATE_LIMIT_WINDOW_S = int(os.getenv("RATE_LIMIT_WINDOW_S", "600"))

# --- Auto-scale presets (longest bounding-box dimension, in millimetres) ----
# Tune these to your target printer's bed size.
SCALE_PRESETS_MM = {"S": 50.0, "M": 100.0, "L": 150.0}

# --- Formats ----------------------------------------------------------------
# Tier 1 mesh formats handled natively by Trimesh.
MESH_FORMATS = {"stl", "obj", "ply", "glb", "gltf", "off", "dae"}
# Tier 3 CAD formats — approximate, require FreeCAD/OpenCASCADE (not built-in).
CAD_FORMATS = {"step", "stp", "iges"}
