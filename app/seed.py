"""
Seed the SQLite DB from the committed OSM sample GeoJSON.

Builds parcel -> building -> floor -> unit for every footprint in
app/data/footprints_sample.geojson. One building is promoted to the
"hero" building (5 floors x 4 units, individually pickable in the UI);
every other building gets a single whole-floor unit per storey so the
API/schema stays uniform across the whole dataset.

Run directly to (re)seed:  python -m app.seed
main.py also calls seed_if_empty() automatically on startup.
"""
import json
import random
from pathlib import Path

from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.geo import polygon_area_m2
from app.height_estimator import estimate_levels_and_height
from app.models import Building, Floor, Parcel, Unit
from app.ulpin import generate_ulpin

DATA_PATH = Path(__file__).resolve().parent / "data" / "footprints_sample.geojson"

DISTRICT_CODE = "01"  # Chennai (fixed, documented synthetic scheme -- see app/ulpin.py)
TALUK_CODE = "01"  # Mylapore (single-neighbourhood demo area)

HERO_LEVELS = 5
HERO_UNITS_PER_FLOOR = 4

OWNER_FIRST_NAMES = [
    "Arun", "Divya", "Karthik", "Lakshmi", "Suresh", "Priya", "Ramesh", "Meena",
    "Vijay", "Anitha", "Senthil", "Kavitha", "Balaji", "Revathi", "Ganesh", "Shanthi",
    "Mohan", "Deepa", "Rajesh", "Uma", "Prakash", "Geetha", "Vikram", "Nithya",
]
OWNER_LAST_NAMES = [
    "Subramaniam", "Krishnan", "Iyer", "Raman", "Natarajan", "Venkatesh",
    "Chandran", "Murugan", "Pillai", "Rajan", "Sundaram", "Narayanan",
]
OWNERSHIP_TYPES = ["Freehold", "Leasehold", "Cooperative Society"]


def synth_owner(rng: random.Random) -> str:
    return f"{rng.choice(OWNER_FIRST_NAMES)} {rng.choice(OWNER_LAST_NAMES)}"


def pick_hero_index(features: list[dict]) -> int:
    """Pick a good hero building: compact (not a sliver/compound-wall),
    a plausible single-building footprint area, and central in the
    dataset -- not simply "largest area", which tends to pick up long
    thin OSM ways (walls, arcades) that make poor demo buildings."""
    from app.geo import lonlat_to_local

    origin_lon, origin_lat = dataset_origin(features)

    def local_bbox(ring):
        pts = [lonlat_to_local(lo, la, origin_lon, origin_lat) for lo, la in ring]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs), max(xs), min(ys), max(ys)

    candidates = []
    for i, f in enumerate(features):
        ring = f["geometry"]["coordinates"][0]
        area = polygon_area_m2(ring, origin_lon, origin_lat)
        min_x, max_x, min_y, max_y = local_bbox(ring)
        bbox_area = (max_x - min_x) * (max_y - min_y)
        compactness = area / bbox_area if bbox_area > 0 else 0
        cx, cy = f["properties"]["centroid"]
        dist_from_center = ((cx - origin_lon) ** 2 + (cy - origin_lat) ** 2) ** 0.5
        if compactness >= 0.55 and 120 <= area <= 400:
            candidates.append((dist_from_center, i))

    if not candidates:
        # Fallback: just the largest footprint, if nothing meets the bar.
        return max(range(len(features)), key=lambda i: polygon_area_m2(
            features[i]["geometry"]["coordinates"][0], origin_lon, origin_lat
        ))

    candidates.sort()
    return candidates[0][1]


def dataset_origin(features: list[dict]) -> tuple[float, float]:
    lons = [f["properties"]["centroid"][0] for f in features]
    lats = [f["properties"]["centroid"][1] for f in features]
    return sum(lons) / len(lons), sum(lats) / len(lats)


def seed_if_empty() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Building).count() > 0:
            return
        _seed(db)
    finally:
        db.close()


def _seed(db: Session) -> None:
    rng = random.Random(42)  # deterministic synthetic data
    fc = json.loads(DATA_PATH.read_text())
    features = fc["features"]
    origin_lon, origin_lat = dataset_origin(features)
    hero_idx = pick_hero_index(features)

    for i, feature in enumerate(features):
        props = feature["properties"]
        ring = feature["geometry"]["coordinates"][0]
        centroid_lon, centroid_lat = props["centroid"]
        footprint_area = polygon_area_m2(ring, origin_lon, origin_lat)
        is_hero = i == hero_idx
        survey_block = f"{i + 1:04d}"

        parcel = Parcel(
            parcel_code=f"TN-{DISTRICT_CODE}-{TALUK_CODE}-{survey_block}",
            district_code=DISTRICT_CODE,
            taluk_code=TALUK_CODE,
            survey_block=survey_block,
            address=_address_for(props, i),
            geojson=json.dumps(feature["geometry"]),
        )
        db.add(parcel)
        db.flush()  # get parcel.id

        if is_hero:
            levels, height_m = HERO_LEVELS, HERO_LEVELS * 3.0
            height_source, is_estimated = "demo_hero_override", True
        else:
            est = estimate_levels_and_height(props.get("building_levels_tag"))
            levels, height_m = est.levels, est.height_m
            height_source, is_estimated = est.source, est.is_estimated

        building = Building(
            parcel_id=parcel.id,
            name=props.get("name") or ("Hero Building" if is_hero else f"Building {survey_block}"),
            osm_id=str(props.get("osm_id")) if props.get("osm_id") else None,
            footprint_geojson=json.dumps(feature["geometry"]),
            centroid_lon=centroid_lon,
            centroid_lat=centroid_lat,
            levels=levels,
            height_m=height_m,
            height_source=height_source,
            is_estimated=is_estimated,
            is_hero=is_hero,
        )
        db.add(building)
        db.flush()

        units_per_floor = HERO_UNITS_PER_FLOOR if is_hero else 1
        floor_height = height_m / levels
        for floor_num in range(1, levels + 1):
            floor = Floor(
                building_id=building.id,
                floor_number=floor_num,
                floor_code=f"{floor_num:02d}",
                height_m=floor_height,
                elevation_m=floor_height * (floor_num - 1),
            )
            db.add(floor)
            db.flush()

            unit_area = footprint_area / units_per_floor if units_per_floor else footprint_area
            for unit_num in range(1, units_per_floor + 1):
                unit_code = f"{unit_num:02d}"
                ulpin = generate_ulpin(DISTRICT_CODE, TALUK_CODE, survey_block, floor.floor_code, unit_code)
                # Small deterministic vacancy sprinkle for demo variety.
                status = "vacant" if (is_hero and floor_num == 3 and unit_num == 2) else "owned"
                unit = Unit(
                    floor_id=floor.id,
                    unit_code=unit_code,
                    ulpin=ulpin,
                    area_sqm=round(unit_area, 1),
                    status=status,
                    owner_name=None if status == "vacant" else synth_owner(rng),
                    ownership_type=None if status == "vacant" else rng.choice(OWNERSHIP_TYPES),
                    synthetic=True,
                )
                db.add(unit)

    db.commit()


def _address_for(props: dict, index: int) -> str:
    house = props.get("addr_housenumber")
    street = props.get("addr_street")
    if house and street:
        return f"{house} {street}, Mylapore, Chennai"
    if street:
        return f"{street}, Mylapore, Chennai"
    return f"Survey Block {index + 1:04d}, Mylapore, Chennai"


if __name__ == "__main__":
    Base.metadata.drop_all(bind=engine)
    seed_if_empty()
    print("Seeded database.")
