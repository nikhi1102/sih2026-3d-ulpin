"""
ARCHITECTURE SEAM: 3D reconstruction source for the hero building.

Current implementation: the hero building's 3D form is a simple extrusion
of its 2D OSM footprint polygon to a flat height per floor (done client
-side in Three.js from the footprint GeoJSON + floor count returned by
GET /api/building/{id}). It is a massing model, not a true 3D scan.

SWAP TARGET: replace the extrusion with a real reconstructed mesh --
e.g. a photogrammetry point cloud / mesh (drone or phone capture,
processed with something like COLMAP or an off-the-shelf photogrammetry
pipeline) or a LiDAR scan, exported as glTF and served from
GET /api/building/{id}/mesh (not implemented). The frontend would load
that mesh instead of extruding, while floors/units/ULPIN data keeps
coming from the same building/floor/unit API shape.

TODO(photogrammetry): once a captured mesh exists for the hero building,
  1. add a `mesh_url` field to the Building API response
  2. serve the glTF as a static file
  3. in static/app.js, branch: if mesh_url present -> GLTFLoader; else ->
     current extrude-from-footprint path (keep as fallback for every
     other, non-scanned building).
"""

MESH_AVAILABLE = False  # flip to True once a real scanned mesh is wired up


def get_hero_mesh_url() -> str | None:
    """Return a URL to a reconstructed mesh for the hero building, if any.

    TODO(photogrammetry): implement once a real capture pipeline exists.
    Returns None today, which tells the frontend to fall back to
    extruding the OSM footprint (the current, working behaviour).
    """
    if not MESH_AVAILABLE:
        return None
    raise NotImplementedError("Photogrammetry mesh pipeline not implemented in this prototype.")
