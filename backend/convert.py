"""Export/convert a mesh to the requested format.

Tiers (see docs/2d-to-3d-converter.md):
  1. Mesh formats (STL/OBJ/PLY/GLB/GLTF/OFF/DAE) — native via Trimesh.
  2. SketchUp — we can't write .skp directly. Export DAE (or GLB) and let the
     user Import + Save As .skp in SketchUp Pro/Studio.
  3. CAD (STEP/IGES) — approximate. A photo-derived mesh is not parametric CAD;
     producing STEP requires FreeCAD/OpenCASCADE and still yields a faceted
     solid. Left unimplemented on purpose.
"""
from __future__ import annotations

from .config import CAD_FORMATS, MESH_FORMATS


def to_bytes(mesh, fmt: str) -> bytes:
    fmt = fmt.lower().lstrip(".")

    if fmt == "gltf":
        # Without embed_buffers, trimesh splits gltf into a {json, .bin} dict.
        # Embed so the endpoint can serve a single self-contained file.
        return next(iter(mesh.export(file_type="gltf", embed_buffers=True).values()))

    if fmt in MESH_FORMATS:
        # trimesh uses "glb" and "dae" (collada) file types directly
        return mesh.export(file_type=fmt)

    if fmt in CAD_FORMATS:
        raise NotImplementedError(
            "CAD export (STEP/IGES) is not built in. It requires FreeCAD or "
            "OpenCASCADE (pythonocc) and produces an approximate faceted solid. "
            "See docs for the recommended approach."
        )

    raise ValueError(f"Unsupported format: {fmt!r}")


def suggested_extension(fmt: str) -> str:
    fmt = fmt.lower().lstrip(".")
    return "gltf" if fmt == "gltf" else fmt
