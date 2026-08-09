"""Mesh processing with Trimesh: cleanup, printability check, scaling, info.

Scale is baked only at export.
"""
from __future__ import annotations

from .config import SCALE_PRESETS_MM


class NotAMeshError(ValueError):
    """The loaded file did not contain usable triangle geometry."""


def load(data: bytes, file_type: str = "glb"):
    import trimesh

    mesh = trimesh.load(file_obj=_bytes_io(data), file_type=file_type, force="mesh")
    if not hasattr(mesh, "faces") or len(mesh.faces) == 0:
        raise NotAMeshError("the generated file contains no triangle geometry")
    return mesh


def _bytes_io(data: bytes):
    import io

    return io.BytesIO(data)


_PRINT_GRAY = (0.55, 0.55, 0.55, 1.0)  # RGBA 0-1


def ensure_visible_material(mesh) -> None:
    """Give the mesh a visible material if it has no real texture, in-place."""
    import trimesh

    material = getattr(mesh.visual, "material", None)
    if material is not None and getattr(material, "baseColorTexture", None) is not None:
        return
    mesh.visual = trimesh.visual.TextureVisuals(
        material=trimesh.visual.material.PBRMaterial(
            baseColorFactor=_PRINT_GRAY, metallicFactor=0.05, roughnessFactor=0.75
        )
    )


# Max hole size (boundary edges) eligible for fan-fill
_MAX_FILLABLE_HOLE_EDGES = 12


def _fill_small_holes(mesh) -> None:
    """Fan-fill boundary loops up to _MAX_FILLABLE_HOLE_EDGES; skip larger ones."""
    import networkx as nx
    import numpy as np
    from trimesh.geometry import faces_to_edges, triangulate_quads
    from trimesh.grouping import group_rows, hashable_rows

    if len(mesh.faces) < 3 or mesh.is_watertight:
        return
    boundary_groups = group_rows(mesh.edges_sorted, require_count=1)
    if len(boundary_groups) < 3:
        return
    boundary = mesh.edges[boundary_groups]
    holes = [h for h in nx.cycle_basis(nx.from_edgelist(boundary)) if len(h) <= _MAX_FILLABLE_HOLE_EDGES]
    if not holes:
        return
    new_faces = triangulate_quads(holes, use_fan=True)
    if len(new_faces) == 0:
        return
    new_edges = faces_to_edges(new_faces)
    hashable_new = hashable_rows(new_edges)
    hashable_old = hashable_rows(boundary)
    needs_reverse = np.isin(hashable_new, hashable_old).reshape((-1, 3)).any(axis=1)
    new_faces[needs_reverse] = np.fliplr(new_faces[needs_reverse])
    mesh.extend_faces(new_faces)


_WELD_TOLERANCE_FRAC = 0.01  # fraction of longest dimension treated as "touching"


def _weld_nearby(mesh, tolerance_frac: float = _WELD_TOLERANCE_FRAC) -> None:
    """Snap near-touching vertices across different parts into shared topology."""
    import numpy as np
    import trimesh
    from scipy.spatial import cKDTree

    if len(mesh.vertices) == 0:
        return
    longest = max(mesh.extents) if len(mesh.extents) else 0
    if longest <= 0:
        return
    tolerance = tolerance_frac * longest

    face_groups = trimesh.graph.connected_components(
        mesh.face_adjacency, nodes=np.arange(len(mesh.faces))
    )
    if len(face_groups) <= 1:
        return

    vertex_body = np.full(len(mesh.vertices), -1, dtype=np.int64)
    for body_id, faces_idx in enumerate(face_groups):
        vertex_body[np.unique(mesh.faces[faces_idx])] = body_id

    tree = cKDTree(mesh.vertices)
    cross_pairs = [
        (a, b)
        for a, b in tree.query_pairs(r=tolerance)
        if vertex_body[a] != vertex_body[b]
    ]
    if not cross_pairs:
        return

    # union-find, then collapse each cluster to its centroid
    parent = np.arange(len(mesh.vertices))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in cross_pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    roots = np.array([find(i) for i in range(len(mesh.vertices))])
    new_vertices = mesh.vertices.copy()
    for root in np.unique(roots):
        members = np.where(roots == root)[0]
        if len(members) > 1:
            new_vertices[members] = mesh.vertices[members].mean(axis=0)

    mesh.vertices = new_vertices
    mesh.merge_vertices()


_VOXEL_REMESH_PITCH_FRAC = 0.02  # fraction of longest dimension per voxel


def _voxel_remesh(mesh, pitch_frac: float = _VOXEL_REMESH_PITCH_FRAC):
    """Rebuild via voxelize+fill+marching_cubes — guaranteed watertight, single-body."""
    longest = max(mesh.extents) if len(mesh.extents) else 0
    if longest <= 0:
        return mesh
    try:
        vox = mesh.voxelized(pitch=pitch_frac * longest).fill()
        remeshed = vox.marching_cubes
        remeshed.apply_transform(vox.transform)  # voxel-index -> world space
    except Exception:
        return mesh
    if len(remeshed.faces) == 0:
        return mesh
    return remeshed


def cleanup(mesh, *, weld: bool = False, guarantee: bool = False):
    """Repair common AI-mesh issues: debris specks, small gaps, missing color.

    weld=True: also bridges near-touching separate parts.
    guarantee=True: falls back to _voxel_remesh if still not watertight.
    May return a different Trimesh object — always use the return value.
    """
    import trimesh

    mesh.merge_vertices()
    mesh.update_faces(mesh.unique_faces())
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()

    if weld:
        _weld_nearby(mesh)

    # up to 3 passes
    for _ in range(3):
        bodies = mesh.split(only_watertight=False)
        if len(bodies) > 1:
            # keep non-debris bodies (>=1% of largest, or >=8 faces)
            max_faces = max(len(b.faces) for b in bodies)
            keep = [b for b in bodies if len(b.faces) >= max(8, max_faces * 0.01)]
            mesh = trimesh.util.concatenate(keep) if len(keep) > 1 else keep[0]

        mesh.fix_normals()
        try:
            _fill_small_holes(mesh)
        except Exception:
            pass

        if mesh.is_watertight and len(bodies) <= 1:
            break

    if guarantee and not mesh.is_watertight:
        # per body, not globally
        bodies = mesh.split(only_watertight=False)
        fixed = [b if b.is_watertight else _voxel_remesh(b) for b in bodies]
        mesh = trimesh.util.concatenate(fixed) if len(fixed) > 1 else fixed[0]

    ensure_visible_material(mesh)
    return mesh


def printability(mesh) -> dict:
    """Read-only diagnostic. Never modifies the mesh.

    single_body is informational only, not required for verdict "ok".
    """
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
    if watertight and winding and positive_volume:
        verdict = "ok"
    elif watertight:
        verdict = "warn"
    else:
        verdict = "fail"
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
    """Measurements in native units (not mm) — client scales for display."""
    return {
        "dimensions": [float(x) for x in mesh.extents],
        "triangles": int(len(mesh.faces)),
        "volume": float(mesh.volume) if mesh.is_volume else None,
    }
