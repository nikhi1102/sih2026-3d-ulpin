"""
ARCHITECTURE SEAM: height/floor-count estimation.

Current implementation: read OSM `building:levels` when present, else
fall back to a fixed default of 3.0 m per floor. This is intentionally
the simplest possible thing that works.

SWAP TARGET: replace `estimate_levels_and_height()` with a call into an
ML model (e.g. shadow-length or LiDAR/photogrammetry-based height
regression from satellite/drone imagery) that returns the same
`HeightEstimate` shape. Nothing outside this module needs to change --
`seed.py` and the API only depend on this function's signature and
return type.

TODO(ml-height-model): train/plug in a real estimator. Candidate inputs:
  - satellite imagery patch for the footprint's bounding box
  - footprint area/perimeter (shadow-independent shape features)
  - neighbouring building heights (spatial smoothing prior)
"""
from dataclasses import dataclass

DEFAULT_METERS_PER_FLOOR = 3.0
DEFAULT_LEVELS_WHEN_UNKNOWN = 3


@dataclass
class HeightEstimate:
    levels: int
    height_m: float
    source: str  # "osm_levels" | "estimated_default"
    is_estimated: bool


def estimate_levels_and_height(building_levels_tag: str | None) -> HeightEstimate:
    """Estimate floor count + total height for a building footprint.

    Args:
        building_levels_tag: raw OSM `building:levels` tag value, if present.

    Returns:
        HeightEstimate with levels, total height in meters, and provenance.
    """
    if building_levels_tag:
        try:
            levels = max(1, int(round(float(building_levels_tag))))
            return HeightEstimate(
                levels=levels,
                height_m=levels * DEFAULT_METERS_PER_FLOOR,
                source="osm_levels",
                is_estimated=False,
            )
        except (ValueError, TypeError):
            pass  # fall through to default

    return HeightEstimate(
        levels=DEFAULT_LEVELS_WHEN_UNKNOWN,
        height_m=DEFAULT_LEVELS_WHEN_UNKNOWN * DEFAULT_METERS_PER_FLOOR,
        source="estimated_default",
        is_estimated=True,
    )
