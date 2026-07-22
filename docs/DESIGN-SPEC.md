# 2D to 3D Converter

A web application that converts 2D images into 3D models using AI. Users upload an image, the app generates a 3D mesh via the Meshy AI API, and the result is displayed in an interactive in-browser viewer.

The app is **per-session only** — there is no gallery and models are not stored. Each generated model exists just long enough to be processed, previewed, and downloaded, then it is discarded.

## Overview

- **Input:** A 2D image (e.g. `.png`, `.jpg`).
- **Process:** The image is sent to Meshy AI's image-to-3D endpoint, which returns a generated 3D model. Optional post-processing (cleanup, format conversion, decimation) is handled with Trimesh.
- **Output:** A downloadable 3D model (`.glb` / `.obj`) rendered live in an interactive viewer.

## Features

### 1. Auto Scale (S / M / L)

Rescale the generated model to preset physical sizes so it's ready to print without manual resizing. Meshy output has no meaningful real-world units, so each preset maps to a target bounding-box dimension.

| Preset | Target longest dimension | Typical use |
|--------|--------------------------|-------------|
| Small (S) | ~50 mm | Keychains, minis, desk trinkets |
| Medium (M) | ~100 mm | Figurines, standard display pieces |
| Large (L) | ~150 mm | Statement pieces (check against printer bed size) |

**Implementation:** Generation happens at the model's **native size**. The S/M/L choice is applied as a **live uniform transform in the Three.js viewer** (the preview just scales) — no regeneration, instant feedback. The chosen scale is only **baked into the geometry at export** (Trimesh: compute `mesh.extents`, find the longest axis, apply a uniform factor so it matches the preset). Uniform scaling preserves proportions, and because it's uniform it does **not** change watertightness/manifold status — so the printability result stays valid without a re-check (see [Printability Check](#3-printability-check)). Exact target values are configurable — treat the ones above as defaults.

### 2. Basic Cleanup

Repair common issues in AI-generated meshes before preview and export. Typical Trimesh operations:

- Merge duplicate/close vertices.
- Remove duplicate, degenerate, and unreferenced (unused) faces and vertices.
- Fix face winding and recompute consistent normals.
- Fill small holes where possible.

The goal is a tidier, more consistent mesh — not a guaranteed perfect one. Cleanup runs automatically after generation, before the printability check.

### 3. Printability Check

Report whether the model is likely to print successfully and surface warnings. This is a **read-only diagnostic** — it informs the user rather than modifying the mesh. Checks to consider:

- **Watertight / manifold:** Is the mesh closed with no holes? (`mesh.is_watertight`)
- **Consistent winding / normals:** Are faces oriented consistently? (`mesh.is_winding_consistent`)
- **Single vs. multiple bodies:** Does it split into disconnected pieces that may need supports or separate printing? (`mesh.split()` / connected components)
- **Volume validity:** Does the mesh have a positive, well-defined volume?
- **(Optional) thin walls / tiny features:** Flag geometry likely too fine to print reliably.

Present results as a simple status (e.g. ✅ Printable / ⚠️ Warnings) with a short list of what failed and why. **Re-run the check after Clean Up** (repair changes the mesh), but **not after scaling** — uniform S/M/L scaling doesn't alter watertightness or winding, so the existing result stays valid.

> **Suggested pipeline order:** generate (native size) → cleanup → printability check → preview (with live scale) → export (bake scale + convert). Cleanup first gives the printability check a healthier mesh to work with.

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Backend | Python + FastAPI | REST API, request handling, orchestration |
| 3D generation | Meshy AI API | Core image-to-3D conversion |
| Mesh processing | Trimesh | Load, inspect, clean, and convert generated meshes |
| Frontend viewer | Three.js | Interactive 3D rendering in the browser |

> **Note:** A Meshy AI subscription is not yet active. See [Meshy AI Setup](#meshy-ai-setup) before running the generation flow.

## Architecture

```
┌──────────┐   upload    ┌──────────────┐   image    ┌────────────┐
│ Browser  │ ──────────► │   FastAPI     │ ─────────► │  Meshy AI  │
│ (Three.js│             │   backend     │            │    API     │
│  viewer) │ ◄────────── │  + Trimesh    │ ◄───────── │            │
└──────────┘   .glb      └──────────────┘   3D model  └────────────┘
```

### Flow

1. User selects/drops an image. The frontend **validates it** (type, size cap) and encodes it as **base64** — since nothing is stored, there's no public URL to hand Meshy, so base64 is the input path.
2. FastAPI receives the image and submits it to Meshy AI's image-to-3D endpoint.
3. Meshy is asynchronous: it returns a task ID; the backend polls for completion. Meanwhile the frontend shows a **"Generating…" loading screen** (Meshy typically takes ~1 minute).
4. On completion, the backend downloads the model at **native size** and runs the Trimesh pipeline: **cleanup → printability check**.
5. The processed model + printability report are returned to the browser and the loading screen switches to the viewer.
6. Three.js loads the model; the user previews it, tries S/M/L scale (live transform), optionally cleans up, then exports.
7. Scale is baked in and the file converted at export. The temporary file is cleaned up on download or when the session's TTL expires.

> **Per-session note:** No database or persistent file storage. Work happens in a temp directory keyed by a session `job_id` with a short **TTL**, then discarded. This keeps the app simple and sidesteps storage/privacy concerns.

## Meshy AI Setup

Before the generation flow will work:

1. Create an account at [meshy.ai](https://www.meshy.ai) and choose a plan (the API requires a paid subscription — verify current pricing and free-tier limits on their site).
2. Generate an API key from the dashboard.
3. Store it as an environment variable — **never commit it to source control**.

```bash
# .env
MESHY_API_KEY=your_api_key_here
```

### Key API concepts to plan around

- **Asynchronous tasks:** Image-to-3D requests return a task ID. You must poll a status endpoint until the task reports success (or failure) before downloading the result.
- **Polling:** Implement a poll loop with a sensible interval and timeout so requests don't hang indefinitely.
- **Credits:** Generations consume credits/quota. Handle "out of credits" and rate-limit responses gracefully.
- **Output formats:** Confirm which formats Meshy returns (commonly `.glb`, `.fbx`, `.obj`) and pick what best fits Three.js (`.glb` is convenient).

> Confirm exact endpoints, request/response shapes, and limits against Meshy's official API docs, since these can change.

## Frontend Design

The UI uses the **City College of Tagaytay (CCT) brand palette** — a warm, collegiate parchment-and-maroon system with heraldic accents.

### Color Tokens

```css
:root {
  /* Core */
  --maroon:        #6D1214;  /* primary: headers, primary buttons, links */
  --ink:           #2F322F;  /* body text, footers, dark UI surfaces */
  --gold:          #C59230;  /* rules, highlights, secondary accents */

  /* Accents (use sparingly) */
  --blue:          #324299;  /* info states, tags */
  --red:           #DB2522;  /* alerts, errors, emphasis */
  --sun:           #DED836;  /* highlights, badges */
  --green:         #5DAF53;  /* success, "printable" state */
  --brick:         #9C3C20;  /* warm secondary, warnings */

  /* Neutrals */
  --parchment:     #F3EEDF;  /* page background, cards, light surfaces */
  --near-black:    #141010;  /* max-contrast text, 3D viewer backdrop */
}
```

### Suggested Typography

Carried over from the brand sheet:

- **Fraunces** — display serif for headings / the app title.
- **Spectral** — serif for body copy.
- **IBM Plex Mono** — monospace for labels, hex/technical readouts, and the printability report metrics.

### Role Mapping for This App

| UI element | Color |
|------------|-------|
| App title / primary buttons ("Generate", "Download") | `--maroon` |
| Body text, labels | `--ink` |
| Dividers, highlights, secondary accents | `--gold` |
| Page background / cards | `--parchment` |
| **3D viewer backdrop** | `--near-black` (dark background makes light meshes pop) |

### Printability Status → Accent Colors

The accent palette lines up naturally with the printability check's result states:

| Status | Meaning | Color |
|--------|---------|-------|
| ✅ Printable | Watertight, consistent, single body | `--green` |
| ⚠️ Warnings | Minor issues (multiple bodies, thin features) | `--sun` / `--brick` |
| ❌ Not printable | Non-manifold / open mesh / invalid volume | `--red` |
| ℹ️ Info / tags | Format, poly count, dimensions | `--blue` |

## Pages & User Flow

The site is intentionally **simple, clean, and accessible**. A persistent top **header** carries three items:

| Nav item | Purpose |
|----------|---------|
| **Upload** | The core converter — a single page that steps through upload → generating → viewer → export |
| **About** | About the creator and the website itself |
| **FAQs** | Conversion instructions and other useful info |

The header stays visible across the site (maroon wordmark left, nav links right, gold underline on the active item). State carries across the Upload steps within a single session (no storage).

---

### Upload — single page, four views

The Upload flow is **one page (`index.html`) that switches between views** in-place (no page reloads), so the session model stays in memory and transitions are smooth. `job_id` is mirrored in `sessionStorage` so a refresh can attempt to restore state (and falls back to the empty state if the temp file/TTL is gone).

**View A — Upload**
- **Centered upload zone** (drag-and-drop + click-to-browse) as the hero.
- One-line tagline above; a short "how it works in 3 steps" strip below.
- **Client-side validation:** accepted types (`.png`/`.jpg`/`.jpeg`), size cap, and a gentle hint ("clear subject, plain background, good lighting").
- **Generate** button disables on click; only **one active job per session** (guards against credit burn).

**View B — Generating…**
- A dedicated **loading screen**: animated indicator + "Generating…" and a rotating status line ("Sending to Meshy… / Building mesh… / Almost there…").
- Reflects poll status; on failure shows a friendly error with a **Try again** button (returns to View A).

**View C — Model Viewer**
- **Three.js viewer** on a `--near-black` backdrop with a `--gold` frame — orbit / zoom / pan.
- **Auto Scale (S / M / L)** selector — a **live preview transform**; updates displayed dimensions instantly, no regeneration.
- **Model info** panel: dimensions, triangle/poly count, format, volume (IBM Plex Mono readout).
- **Printability check** card with ✅ / ⚠️ / ❌ status and reasons.
- **Clean Up** button — runs the Trimesh repair pass, refreshes the viewer, and **re-runs the printability check**.
- **Export** button → opens the **confirmation popup**.

**View D — Export & Convert**
- **Format dropdown** (grouped — see [File Conversion & Formats](#file-conversion--formats)).
- Summary of the model + chosen scale; a "which format should I pick?" link to the FAQ.
- **Download** button → bakes scale, converts, serves the file, then clears the session temp files.

**Empty / re-entry state**
- If the viewer/export view is reached with no active model (e.g. direct link or refresh after TTL), show a friendly "No model yet — start here" that routes back to View A. No blank/broken screens.

#### Confirmation Popup (View C → D)

A modal, not a browser `confirm()`, styled in-palette:

- Restates chosen **size** and current **printability status**.
- If status is ⚠️ or ❌, show a gentle warning ("This model may not print cleanly — export anyway?").
- Buttons: **Cancel** (`--ink` outline) and **Confirm export** (`--maroon` fill).

---

### About

A single, calm page about the project and the person behind it.

- **What this is** — a short plain-language description of the 2D-to-3D converter.
- **Why it exists** — the motivation / context (e.g. a City College of Tagaytay project).
- **The creator** — name, role, and a short bio; optional links (GitHub, contact).
- **Tech credits** — a line acknowledging Meshy AI, Trimesh, Three.js, and FastAPI.
- Styled in-palette with Fraunces headings on parchment; keep it to one screen.

---

### FAQs

Practical help, in expandable accordion items. Covers conversion guidance and common questions. Suggested entries:

- **What file format should I choose?** → the SketchUp / CAD / printing guidance below.
- **How do I open the file in SketchUp?** → import steps + which format to pick.
- **Can I get a CAD (STEP) file?** → the faceted-solid caveat.
- **What does the printability check mean?** → watertight, single body, etc.
- **What images work best?** → clear subject, plain background, good lighting.
- **Are my models stored?** → no; per-session only, files are discarded after download.
- **Is it free?** → depends on the Meshy plan in use; note current limits.

See [File Conversion & Formats](#file-conversion--formats) for the detailed format guidance that populates the conversion FAQ entries.

## File Conversion & Formats

Meshy returns **triangle-mesh** formats; conversion between mesh formats is straightforward with Trimesh. CAD and SketchUp are a different geometry paradigm and need extra care — this section is honest about what's clean vs. approximate.

### Tiers

**Tier 1 — Native mesh (fully supported via Trimesh)**
`.stl`, `.obj`, `.ply`, `.glb`/`.gltf`, `.off`, `.dae` (Collada). Reliable, ideal for 3D printing and general use.

**Tier 2 — SketchUp path**
Your app can't write a true `.skp` (proprietary format), so instead you export a format SketchUp **imports**, and the user does `File → Save As → .skp` themselves. Which format to recommend:

- **DAE (Collada)** — ★ recommended. Imports **natively in SketchUp Pro/Studio** and keeps materials/textures.
- **GLB** — also imports natively in current SketchUp. Since Meshy outputs GLB, this can pass through with no conversion.
- **STL** — imports for 3D-printing workflows, but **geometry only** (no color/texture).
- **OBJ** — avoid as the primary path: SketchUp does **not** import OBJ natively; it needs a plugin (Skimp, SimLab, FluidImporter) even on Pro.

> **Edition caveat:** OBJ/FBX/DAE/STL native import is a **Pro/Studio** feature. SketchUp **Free (web)** is limited (essentially `.skp` and images), so recommend Pro for the SketchUp workflow.

**Tier 3 — CAD (approximate / faceted)**
`.step`/`.stp`, `.iges` are parametric **solid** (B-rep) formats. An AI-generated triangle mesh has no parametric solid to export. Two realities to communicate:

- Your Tier 1 mesh files (STL/OBJ/DAE) **do** open in CAD tools (Fusion, FreeCAD, SolidWorks) — but they arrive as a **mesh**, which the user then converts to a solid inside the CAD app.
- Converting a mesh to a solid (here, or in the CAD app) yields a **dense faceted solid** — every triangle becomes a face. It's usable for reference and basic operations, but it is **not** clean, editable parametric CAD. That limit is inherent to starting from a mesh; no format avoids it.

If you want the backend to emit real `.step`/`.iges`, use **FreeCAD** or **OpenCASCADE** (`pythonocc`) to wrap the mesh — still faceted, just pre-converted. Label CAD options clearly as **approximate**.

### Dropdown Grouping (suggested UI)

```
Print & Mesh
  ├─ STL  (3D printing)
  ├─ GLB
  ├─ PLY
  └─ OBJ
For SketchUp (Pro/Studio)
  ├─ DAE (Collada) — import, then Save As .skp   ★ recommended
  └─ GLB — native import
CAD (approximate — imports as faceted solid)
  ├─ STEP
  └─ IGES
```

> **Design honesty:** add a small tooltip/note on the SketchUp and CAD options — `.skp` isn't produced directly (import + Save As), and STEP/IGES come in as faceted, not parametric. Setting expectations beats shipping a "broken"-feeling export.

## Project Structure (proposed)

```
2d-to-3d-converter/
├── backend/
│   ├── main.py            # FastAPI app + routes
│   ├── meshy_client.py    # Meshy API wrapper (submit, poll, download)
│   ├── mesh_utils.py      # Trimesh: cleanup, scale (bake at export), printability check
│   ├── convert.py         # Format conversion (mesh + CAD/SketchUp paths)
│   ├── config.py          # Env/config loading + limits (size cap, TTL)
│   └── requirements.txt
├── frontend/
│   ├── index.html         # Upload — single page, 4 views (upload/loading/viewer/export)
│   ├── app.js             # View switching + session/job state (sessionStorage)
│   ├── viewer.js          # Three.js scene, loader, controls, live scale
│   ├── about.html         # About — creator & project
│   ├── faqs.html          # FAQs — conversion guide & info
│   ├── theme.css          # CCT palette tokens + fonts
│   └── style.css
├── .env                   # API key (gitignored)
├── .gitignore
└── README.md
```

## API Endpoints (proposed)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/generate` | Accept a base64 image (validated), submit to Meshy, return a `job_id`. Rejects if a job is already active for the session |
| `GET` | `/status/{job_id}` | Return generation status (pending / processing / done / failed) for the loading screen to poll |
| `GET` | `/model/{job_id}` | Return the generated **native-size** model (cleaned) for the viewer |
| `GET` | `/report/{job_id}` | Return the printability check results as JSON |
| `POST` | `/cleanup/{job_id}` | Run the Trimesh repair pass; return updated model + refreshed report |
| `GET` | `/convert/{job_id}?format=stl&scale=M` | Bake the chosen scale, convert to the requested format, and return the file |

> `job_id` is a short-lived session reference tied to a temp dir with a **TTL**, not a stored record. It clears on download or expiry. Server also enforces an **upload size cap** and **one active job per session** as guard rails against accidental credit burn.

## Dependencies

```txt
# backend/requirements.txt
fastapi
uvicorn[standard]
python-multipart      # file uploads
httpx                 # async calls to Meshy API
trimesh
python-dotenv

# Optional — only for Tier 3 CAD export (STEP/IGES)
# Requires FreeCAD or OpenCASCADE; pythonocc-core is conda-friendly
# pythonocc-core
```

Frontend loads Three.js (via CDN or npm) plus a `GLTFLoader` for `.glb` models and `OrbitControls` for camera interaction. Styling uses the CCT palette tokens with Fraunces / Spectral / IBM Plex Mono from Google Fonts.

## Roadmap

- [ ] Scaffold FastAPI backend with a base64 image endpoint + validation
- [ ] Subscribe to Meshy AI and add API key handling
- [ ] Implement Meshy client (submit → poll → download)
- [ ] Add session store: `job_id` + temp dir with TTL; enforce one active job + size cap
- [ ] Add basic cleanup (Trimesh repair/merge/normals)
- [ ] Add printability check + report endpoint (re-run after cleanup)
- [ ] Add scale bake at export (native-size generation; S/M/L applied at convert)
- [ ] Build persistent header nav (Upload / About / FAQs) with active-state styling
- [ ] Build Upload single page with 4-view switching (upload / generating / viewer / export)
- [ ] Build "Generating…" loading screen tied to status polling
- [ ] Build viewer — Three.js, live S/M/L scale, model info, printability card, clean-up
- [ ] Build export view — grouped format dropdown (mesh / SketchUp / CAD)
- [ ] Add export confirmation popup (size + printability recap)
- [ ] Add empty / re-entry state (no active model → route to upload)
- [ ] Build About page — creator + project + tech credits
- [ ] Build FAQs page — accordion with conversion guide + common questions
- [ ] Implement mesh format conversion (Tier 1) via Trimesh
- [ ] Add SketchUp path (DAE/GLB export + import instructions in FAQ)
- [ ] (Optional) Add approximate CAD export via FreeCAD/OpenCASCADE
- [ ] Add error handling (invalid image, timeout, out of credits)
- [ ] Clean up temp files on download / TTL expiry

## Open Questions

- Which Meshy plan best fits expected usage volume?
- What exact mm targets should the S/M/L presets use? (Confirm against your target printer's bed size.)
- What image constraints (size, format, subject) give the best results?
- How long should a session's temp model persist before automatic cleanup?
- Is experimental CAD (STEP/IGES) export worth the FreeCAD/OpenCASCADE dependency for v1, or defer it?
