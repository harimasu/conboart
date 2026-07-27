"""Mesh processing with Trimesh: cleanup, printability check, scaling, info.

Design notes:
- Generation happens at native size. The S/M/L scale is applied (baked) only at
  export, so the viewer can preview scale live without re-processing.
- Uniform scaling does not change watertightness or winding, so the printability
  result stays valid after scaling and only needs re-running after cleanup.
"""
from __future__ import annotations

from .config import SCALE_PRESETS_MM


def load(data: bytes, file_type: str = "glb"):
    import trimesh

    scene_or_mesh = trimesh.load(
        file_obj=_bytes_io(data), file_type=file_type, force="mesh"
    )
    return scene_or_mesh


def _bytes_io(data: bytes):
    import io

    return io.BytesIO(data)


def cleanup(mesh):
    """Repair common issues in AI-generated meshes, escalating until the mesh
    passes printability() or there's nothing left to try.

    Returns the repaired mesh. This can be a *different* object than the one
    passed in — isolating the main body (below) builds a new Trimesh — so
    callers must use the return value rather than assume in-place mutation.
    """
    mesh = _repair_pass(mesh)

    if not mesh.is_watertight:
        # AI-exported meshes often have vertices that are meant to coincide
        # but differ by float noise, which reads as a boundary hole rather
        # than a true gap. Re-weld at a coarser tolerance and retry.
        mesh.merge_vertices(digits_vertex=4)
        mesh = _repair_pass(mesh)

    bodies = mesh.split(only_watertight=False)
    if len(bodies) > 1:
        # Small disconnected shards are near-universal noise in generated
        # meshes, not an intentional multi-part model — keep the main body.
        mesh = max(bodies, key=lambda b: len(b.faces))
        mesh = _repair_pass(mesh)

    return mesh


def _repair_pass(mesh):
    mesh.merge_vertices()
    mesh.update_faces(mesh.unique_faces())
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    mesh.fix_normals(multibody=True)
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
    """Native-scale info. Generation happens at a small normalized size, so
    volume here is deliberately full precision — the frontend scales it up
    to the chosen S/M/L preset (cubically) before rounding for display.
    Rounding to 2dp here first would zero out that tiny native volume before
    scaling ever sees it.
    """
    ext = [round(float(x), 2) for x in mesh.extents]
    return {
        "dimensions_mm": ext,
        "triangles": int(len(mesh.faces)),
        "volume_cm3": float(mesh.volume) / 1000.0 if mesh.is_volume else None,
    }
