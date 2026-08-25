"""
Ingestion script: fetch REAL building footprints for a small Chennai
neighbourhood (Mylapore, near Kapaleeshwarar Temple) from OpenStreetMap
via the Overpass API, and write them out as a GeoJSON FeatureCollection.

This is the ONLY script that talks to the network. The app itself never
calls Overpass at runtime -- it loads the committed file this script
produces (app/data/footprints_sample.geojson) so the demo works fully
offline and is immune to Overpass being slow/down on demo day.

Usage:
    python3 scripts/fetch_osm_footprints.py

Re-run it any time to refresh the committed sample with the latest OSM
data for the same bounding box. It is NOT run automatically by the app.
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# Small bounding box around Kapaleeshwarar Temple, Mylapore, Chennai.
# (south, west, north, east) -- dense, well-mapped, walkable-sized area.
BBOX = (13.0330, 80.2680, 13.0370, 80.2720)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OUT_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "footprints_sample.geojson"

# Cap on context buildings kept in the sample (in addition to the hero).
MAX_CONTEXT_BUILDINGS = 45


def fetch_overpass(bbox, timeout=40):
    south, west, north, east = bbox
    query = (
        f'[out:json][timeout:30];'
        f'(way["building"]({south},{west},{north},{east}););'
        f'out geom;'
    )
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(
        OVERPASS_URL,
        data=data,
        headers={
            "User-Agent": "SIH26011-3D-ULPIN-Prototype/1.0 (educational hackathon prototype)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def way_to_polygon_coords(el):
    """Convert an Overpass 'geometry' array into a closed GeoJSON polygon ring."""
    geom = el.get("geometry")
    if not geom or len(geom) < 4:
        return None
    ring = [[pt["lon"], pt["lat"]] for pt in geom]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def build_feature_collection(elements):
    features = []
    for el in elements:
        if el.get("type") != "way":
            continue
        ring = way_to_polygon_coords(el)
        if ring is None:
            continue
        tags = el.get("tags", {})
        lons = [c[0] for c in ring]
        lats = [c[1] for c in ring]
        centroid = [sum(lons) / len(lons), sum(lats) / len(lats)]
        features.append({
            "type": "Feature",
            "properties": {
                "osm_id": el["id"],
                "osm_type": "way",
                "building": tags.get("building", "yes"),
                "name": tags.get("name"),
                "building_levels_tag": tags.get("building:levels"),
                "addr_housenumber": tags.get("addr:housenumber"),
                "addr_street": tags.get("addr:street"),
                "centroid": centroid,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [ring],
            },
        })
    return features


def main():
    print(f"Fetching OSM building footprints for bbox {BBOX} ...")
    try:
        raw = fetch_overpass(BBOX)
    except Exception as exc:  # network down, Overpass busy, etc.
        print(f"Overpass fetch FAILED ({exc}).", file=sys.stderr)
        print("The committed app/data/footprints_sample.geojson (if present) is left untouched.", file=sys.stderr)
        sys.exit(1)

    features = build_feature_collection(raw.get("elements", []))
    print(f"Fetched {len(features)} building footprints from OSM.")

    if len(features) > MAX_CONTEXT_BUILDINGS + 1:
        # Keep the buildings closest to the bbox centre so the sample
        # stays a compact, demo-able cluster instead of the whole tile.
        south, west, north, east = BBOX
        cx, cy = (west + east) / 2, (south + north) / 2

        def dist(f):
            lon, lat = f["properties"]["centroid"]
            return (lon - cx) ** 2 + (lat - cy) ** 2

        features.sort(key=dist)
        features = features[: MAX_CONTEXT_BUILDINGS + 1]

    fc = {
        "type": "FeatureCollection",
        "properties": {
            "source": "OpenStreetMap contributors, via Overpass API",
            "license": "ODbL",
            "area": "Mylapore, Chennai (near Kapaleeshwarar Temple)",
            "bbox": list(BBOX),
            "fetched_feature_count": len(features),
        },
        "features": features,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(fc, indent=2))
    print(f"Wrote {len(features)} features to {OUT_PATH}")


if __name__ == "__main__":
    main()
