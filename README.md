# CONBOART

**Convert + boar.** A web-based AI system that turns a 2D image into a 3D-printable model — no modeling, no complex software, no technical background required.

> Design and Development of a Web-Based 2D Image to 3D Model Generation System Using Artificial Intelligence for 3D Printing
> School of Computer Studies · BS Computer Science · City College of Tagaytay

## What it does

Upload an image → an AI service (Meshy) generates a 3D model → the model is cleaned up, checked for printability, and previewed in an interactive viewer → export for 3D printing or SketchUp. Nothing is stored; each model lives only for the session.

## Tech stack

- **Backend:** Python · FastAPI
- **3D generation:** Meshy AI
- **Mesh processing:** Trimesh
- **3D viewer:** Three.js
- **Frontend:** HTML · CSS · JavaScript

## Project structure

```
conboart/
├── backend/
│   ├── main.py           # FastAPI app + routes; serves the frontend
│   ├── config.py         # Env config + limits + scale presets
│   ├── generator.py      # Picks the backend: mock / hf / meshy
│   ├── meshy_client.py   # Meshy image-to-3D wrapper (paid)
│   ├── hf_client.py      # Hugging Face TRELLIS wrapper (free)
│   ├── hf_probe.py       # Inspect / smoke-test a Hugging Face Space
│   ├── errors.py         # Shared GenerationError
│   ├── mesh_utils.py     # Trimesh: cleanup, printability, scale, info
│   ├── convert.py        # Format export (mesh / SketchUp / CAD tiers)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── index.html        # The full CONBOART UI (Upload / About / FAQs)
├── docs/
│   ├── DESIGN-SPEC.md            # Full design spec
│   ├── CONBOART-UI-documentation.html   # All screens for screenshots
│   └── ui-png/                   # Rendered UI screenshots (desktop + phone)
└── README.md
```

## Getting started

Requires **Python 3.10+**.

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Configure environment
cp backend/.env.example backend/.env
#   Ships as GENERATOR=mock — runs offline, no account needed.
#   See "Choosing a generator" below for free and paid real generation.

# 4. Run
uvicorn backend.main:app --reload

# 5. Open the app
#    http://127.0.0.1:8000/
```

### Choosing a generator

Set `GENERATOR` in `backend/.env` to pick what turns your image into a model:

| `GENERATOR` | Cost | What you get |
|-------------|------|--------------|
| `mock` | free | A sample sphere. Ignores your image — for building the UI and testing the pipeline offline. |
| `hf` | free | Real results from your real image, via open-source [TRELLIS](https://huggingface.co/spaces/trellis-community/TRELLIS) on a public Hugging Face Space. Limited daily quota. |
| `meshy` | paid | The Meshy API. |

Leaving `GENERATOR` unset keeps the old behaviour: `mock` unless `MESHY_API_KEY`
is set.

#### Free generation with `hf`

TRELLIS is MIT-licensed, so it's usable for academic and commercial work. Add a
free token from <https://huggingface.co/settings/tokens> (no credit card) to
`.env` as `HF_TOKEN` for a larger daily quota than the shared anonymous pool.

Public Spaces are **demos, not production APIs** — they queue, they're rate
limited, and they go offline. Good for testing and demos; not something to
build a deployed product on.

Each Space declares its own endpoint names, so `hf_client` discovers the right
one at runtime. To see what a Space offers, or to smoke-test a real generation:

```bash
python -m backend.hf_probe              # list endpoints
python -m backend.hf_probe photo.jpg    # generate from an image
```

If discovery picks the wrong endpoint, pin it with `HF_API_NAME` in `.env`.

> The frontend prototype currently runs a **simulated** generation flow so it
> works standalone. Wiring its buttons to the `/api/*` endpoints below is the
> next integration step.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/api/health` | Liveness + which generator is active |
| POST | `/api/generate` | `{ image_base64, mime }` → generate, clean up, check; returns `job_id` |
| GET  | `/api/status/{job_id}` | Generation status |
| GET  | `/api/report/{job_id}` | Printability report + model info |
| POST | `/api/cleanup/{job_id}` | Re-run Trimesh cleanup; returns refreshed report |
| GET  | `/api/convert/{job_id}?format=stl&scale=M` | Bake scale, convert, download |

## Export formats

- **Printing / mesh:** `STL`, `OBJ`, `PLY`, `GLB` — native via Trimesh.
- **SketchUp:** export `DAE` (or `GLB`), then Import + Save As `.skp` in SketchUp Pro/Studio. (`.skp` can't be written directly.)
- **CAD (STEP/IGES):** experimental — needs FreeCAD/OpenCASCADE and yields an approximate faceted solid. Not built in.

## The team

- Jethro Ronnel Jerome M. Zapanta — Lead Developer
- Diana Jayne M. Basiya — Researcher
- John Christopher P. Eulin — Researcher

## Push this to your own GitHub

This folder is already a git repository with an initial commit. To publish it:

```bash
# create an empty repo on GitHub first, then:
git remote add origin https://github.com/<you>/conboart.git
git branch -M main
git push -u origin main
```
