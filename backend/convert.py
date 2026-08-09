"""Export/convert a mesh to the requested format.

Tiers (see docs/DESIGN-SPEC.md):
  1. Mesh formats (STL/OBJ/PLY/GLB/GLTF/OFF/DAE) — native via Trimesh.
  2. SketchUp — export DAE (or GLB), Import + Save As .skp in SketchUp.
  3. CAD (STEP/IGES) — unimplemented; needs FreeCAD/OpenCASCADE.
"""
from __future__ import annotations

from .config import CAD_FORMATS, MESH_FORMATS


def to_bytes(mesh, fmt: str) -> bytes:
    fmt = fmt.lower().lstrip(".")

    if fmt == "gltf":
        # embed buffers into a single file
        return next(
            iter(
                mesh.export(
                    file_type="gltf", embed_buffers=True, include_normals=True
                ).values()
            )
        )

    if fmt == "glb":
        return mesh.export(file_type="glb", include_normals=True)

    if fmt in MESH_FORMATS:
        # trimesh uses "dae" (collada) etc. file types directly
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
