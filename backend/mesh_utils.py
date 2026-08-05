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


_PRINT_GRAY = (0.55, 0.55, 0.55, 1.0)  # RGBA 0-1, a neutral filament-like gray

# Cap on boundary-loop size (edge count) fan-filling will attempt to close.
# trimesh's own docs warn a fan triangulation "may result in bad answers if
# the holes are non-convex" — fine for a handful of edges, but AI meshes are
# irregular, and a thin-shell part (eg. a hollow chair leg with an open
# bottom) can have a large, jagged, non-convex opening that IS the object's
# real boundary, not damage to repair. Fanning that produces a mess of
# crossing sliver triangles across the whole part. Leaving a large opening
# unfilled (honestly non-watertight) beats visually wrecking the shape.
_MAX_FILLABLE_HOLE_EDGES = 12


def _fill_small_holes(mesh) -> None:
    """Fan-fill only small boundary loops; leave large openings alone.

    Reimplements trimesh.repair.fill_holes(mesh, use_fan=True) but skips any
    boundary loop bigger than _MAX_FILLABLE_HOLE_EDGES — see that constant.
    """
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


# Default weld tolerance as a fraction of the model's longest dimension.
# Chair-leg-to-seat style contact gaps from AI mesh generation are usually a
# tiny fraction of the model's overall size; this is deliberately small so it
# bridges true near-touching contact points without measurably rounding off
# real surface detail elsewhere.
_WELD_TOLERANCE_FRAC = 0.01


def _weld_nearby(mesh, tolerance_frac: float = _WELD_TOLERANCE_FRAC) -> None:
    """Snap vertices from DIFFERENT connected parts within a small tolerance
    together, in-place, to bridge near-touching contact points (eg. a chair
    leg that doesn't quite reach the seat it was meant to join) into real
    shared topology.

    Deliberately restricted to cross-part pairs: mesh.merge_vertices() only
    catches exact (floating-point) duplicates, not "close enough", but a
    naive proximity merge across *all* vertices would also fuse ordinary
    fine tessellation within a single part — points that are legitimately
    close together as part of normal surface detail, not a gap. Only
    vertices belonging to different connected components are candidates.
    """
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
        return  # nothing separate to bridge

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

    # Union-find: group every vertex that ends up transitively close to
    # another into one cluster, then collapse each cluster to its centroid.
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
    mesh.merge_vertices()  # collapse the now-identical positions into shared indices


def cleanup(mesh, *, weld: bool = False):
    """Repair common issues in AI-generated meshes.

    Image-to-3D output is typically littered with tiny disconnected debris
    specks around the real object and small surface gaps — the two biggest
    reasons printability() below comes back "single_body": false or
    "watertight": false. Discarding everything but the dominant body and then
    hole-filling clears most of that.

    weld=True additionally snaps near-touching vertices together first (see
    _weld_nearby) to bridge separate-but-adjacent parts — eg. a chair's legs,
    seat and backrest — into one connected solid. Off by default because it's
    a deliberate, coarser repair a user should ask for (the "clean up model"
    action), not something every generation silently applies.

    May return a different Trimesh object than the one passed in (the largest
    body becomes a fresh mesh) — always use the return value, not the arg.
    """
    import trimesh

    mesh.merge_vertices()
    mesh.update_faces(mesh.unique_faces())
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()

    if weld:
        _weld_nearby(mesh)

    # Two passes: fan hole-filling occasionally leaves a near-zero-volume
    # sliver of its own (a hole boundary closed with a couple of degenerate
    # triangles that end up geometrically separate from the body once
    # exported/reloaded). One debris-drop pass won't catch a sliver that
    # doesn't exist until the fill runs, so repeat until it's actually stable.
    for _ in range(3):
        bodies = mesh.split(only_watertight=False)
        if len(bodies) > 1:
            # Debris specks are a handful of faces, orders of magnitude
            # smaller than any real part — but a multi-part object (chair
            # legs, seat, backrest as separate shells) has several bodies
            # that are each a substantial fraction of the whole. Keeping only
            # the single largest body would silently discard the rest of the
            # object (a chair reduced to one leg); keep every body that isn't
            # obviously debris instead.
            max_faces = max(len(b.faces) for b in bodies)
            keep = [b for b in bodies if len(b.faces) >= max(8, max_faces * 0.01)]
            mesh = trimesh.util.concatenate(keep) if len(keep) > 1 else keep[0]

        mesh.fix_normals()
        try:
            _fill_small_holes(mesh)
        except Exception:
            pass  # best-effort

        if mesh.is_watertight and len(bodies) <= 1:
            break

    # mesh_utils.load() forces a scene merge (see its docstring), which drops
    # per-submesh materials/textures. Re-exported with no material, three.js's
    # GLTFLoader falls back to a default *white* MeshStandardMaterial — a
    # blown-out, hard-to-see preview. Give it back a uniform, visible gray.
    mesh.visual = trimesh.visual.TextureVisuals(
        material=trimesh.visual.material.PBRMaterial(
            baseColorFactor=_PRINT_GRAY, metallicFactor=0.05, roughnessFactor=0.75
        )
    )
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
