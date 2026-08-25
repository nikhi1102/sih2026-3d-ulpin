"""Small geometry helpers: lon/lat <-> local-meter conversion and area."""
import math

METERS_PER_DEG_LAT = 110_540.0


def meters_per_deg_lon(lat_deg: float) -> float:
    return 111_320.0 * math.cos(math.radians(lat_deg))


def lonlat_to_local(lon: float, lat: float, origin_lon: float, origin_lat: float) -> tuple[float, float]:
    """Equirectangular projection to local meters, good enough at this scale (few hundred m)."""
    x = (lon - origin_lon) * meters_per_deg_lon(origin_lat)
    y = (lat - origin_lat) * METERS_PER_DEG_LAT
    return x, y


def polygon_area_m2(ring_lonlat: list[list[float]], origin_lon: float, origin_lat: float) -> float:
    """Shoelace formula area (m^2) for a closed [lon, lat] ring."""
    pts = [lonlat_to_local(lon, lat, origin_lon, origin_lat) for lon, lat in ring_lonlat]
    area = 0.0
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0
