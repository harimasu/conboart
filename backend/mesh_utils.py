"""Mesh processing with Trimesh: cleanup, printability check, scaling, info.

Design notes:
- Generation happens at native size. The S/M/L scale is applied (baked) only at
  export, so the viewer can preview scale live without re-processing.
- Uniform scaling does not change watertightness or winding, so the printability
  result stays valid after scaling and only needs re-running after cleanup.
"""
from __future__ import annotations

from .config import SCALE_PRESETS_MM


class NotAMeshError(ValueError):
    """The loaded file did not contain usable triangle geometry."""


def load(data: bytes, file_type: str = "glb"):
    import trimesh

    mesh = trimesh.load(file_obj=_bytes_io(data), file_type=file_type, force="mesh")
    # force="mesh" concatenates a scene into one Trimesh, but a file with no
    # triangles still comes back as a PointCloud/empty geometry — every caller
    # below assumes .faces exists, so reject it here rather than 500 later.
    if not hasattr(mesh, "faces") or len(mesh.faces) == 0:
        raise NotAMeshError("the generated file contains no triangle geometry")
    return mesh


def _bytes_io(data: bytes):
    import io

    return io.BytesIO(data)


def cleanup(mesh):
    """Repair common issues in AI-generated meshes. Returns the same mesh."""
    mesh.merge_vertices()
    mesh.update_faces(mesh.unique_faces())
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    mesh.fix_normals()
    try:
        mesh.fill_holes()
    except Exception:
        pass  # fill_holes is best-effort
    return mesh


def printability(mesh) -> dict:
    """Read-only diagnostic. Never modifies the mesh."""
    watertight = bool(mesh.is_watertight)
    winding = bool(mesh.is_winding_consistent)
    bodies = mesh.split(only_watertight=False)
    single_body = len(bodies) <= 1
    positive_volume = bool(mesh.is_volume) and bool(mesh.volume > 0)

    checks = {
        "watertight": watertight,
        "consistent_normals": winding,
        "single_body": single_body,
        "positive_volume": positive_volume,
    }
    if all(checks.values()):
        verdict = "ok"          # Ready to print
    elif watertight:
        verdict = "warn"        # Prints, but may need attention/supports
    else:
        verdict = "fail"        # Open/non-manifold mesh
    return {"verdict": verdict, "checks": checks}


def bake_scale(mesh, size: str):
    """Scale the mesh uniformly so its longest axis matches the S/M/L preset."""
    target_mm = SCALE_PRESETS_MM.get(size.upper())
    if not target_mm:
        return mesh
    longest = max(mesh.extents)
    if longest <= 0:
        return mesh
    mesh.apply_scale(target_mm / longest)
    return mesh


def model_info(mesh) -> dict:
    """Measurements in the mesh's own native units — NOT millimetres.

    Scale is baked at export, so nothing here has been scaled yet. The client
    multiplies by the S/M/L factor to get mm and cm³ for display.

    Do not round these: a generated mesh is typically only 1-2 units across, so
    its raw volume is ~1e-3 of a "unit cm³". Rounding here and cubing the scale
    factor on the client turned every volume into 0.
    """
    return {
        "dimensions": [float(x) for x in mesh.extents],
        "triangles": int(len(mesh.faces)),
        "volume": float(mesh.volume) if mesh.is_volume else None,
    }
