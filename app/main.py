import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload

from app.database import SessionLocal
from app.models import Building, Floor, Unit
from app.schemas import BuildingDetailOut, FloorOut, ParcelOut, UnitDetailOut, UnitOut
from app.seed import seed_if_empty
from app.ulpin import format_ulpin

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="SIH26011 - 3D ULPIN Generation and Vertical Property Mapping",
    description="Prototype: real OSM footprints extruded to 3D, with synthetic vertical "
    "ownership (ULPIN / floor / unit) resolution.",
    version="0.1.0",
)


@app.on_event("startup")
def on_startup():
    seed_if_empty()


@app.get("/api/footprints")
def get_footprints():
    """GeoJSON FeatureCollection of every building footprint in the demo area."""
    db: Session = SessionLocal()
    try:
        buildings = db.query(Building).all()
        features = []
        for b in buildings:
            geometry = json.loads(b.footprint_geojson)
            features.append({
                "type": "Feature",
                "properties": {
                    "building_id": b.id,
                    "name": b.name,
                    "is_hero": b.is_hero,
                    "levels": b.levels,
                    "height_m": b.height_m,
                    "height_source": b.height_source,
                    "is_estimated": b.is_estimated,
                    "centroid": [b.centroid_lon, b.centroid_lat],
                },
                "geometry": geometry,
            })
        return {"type": "FeatureCollection", "features": features}
    finally:
        db.close()


def _building_to_detail_out(b: Building) -> BuildingDetailOut:
    parcel = b.parcel
    return BuildingDetailOut(
        building_id=b.id,
        name=b.name,
        is_hero=b.is_hero,
        osm_id=b.osm_id,
        levels=b.levels,
        height_m=b.height_m,
        height_source=b.height_source,
        is_estimated=b.is_estimated,
        centroid=[b.centroid_lon, b.centroid_lat],
        footprint=json.loads(b.footprint_geojson),
        parcel=ParcelOut(
            id=parcel.id,
            parcel_code=parcel.parcel_code,
            district_code=parcel.district_code,
            taluk_code=parcel.taluk_code,
            survey_block=parcel.survey_block,
            address=parcel.address,
        ),
        floors=[
            FloorOut(
                floor_number=f.floor_number,
                floor_code=f.floor_code,
                height_m=f.height_m,
                elevation_m=f.elevation_m,
                units=[
                    UnitOut(
                        unit_id=u.id,
                        unit_code=u.unit_code,
                        ulpin=u.ulpin,
                        ulpin_grouped=format_ulpin(u.ulpin),
                        area_sqm=u.area_sqm,
                        status=u.status,
                        owner_name=u.owner_name,
                        ownership_type=u.ownership_type,
                        synthetic=u.synthetic,
                    )
                    for u in f.units
                ],
            )
            for f in b.floors
        ],
    )


@app.get("/api/building/{building_id}", response_model=BuildingDetailOut)
def get_building(building_id: int):
    """Full vertical breakdown of one building: floors -> units, with ULPIN/owner per unit."""
    db: Session = SessionLocal()
    try:
        b = (
            db.query(Building)
            .options(joinedload(Building.parcel), joinedload(Building.floors))
            .filter(Building.id == building_id)
            .first()
        )
        if b is None:
            raise HTTPException(status_code=404, detail=f"No building with id {building_id}")
        return _building_to_detail_out(b)
    finally:
        db.close()


@app.get("/api/unit/{ulpin}", response_model=UnitDetailOut)
def get_unit(ulpin: str):
    """Resolve a single unit (and its parent floor/building/parcel) by its 14-digit ULPIN.

    Accepts either the raw 14-digit string or the grouped display form
    (e.g. "33-01-01-0001-01-01") -- non-digit characters are stripped
    before lookup.
    """
    digits = "".join(ch for ch in ulpin if ch.isdigit())
    if len(digits) != 14:
        raise HTTPException(status_code=404, detail=f"Not a valid 14-digit ULPIN: {ulpin!r}")

    db: Session = SessionLocal()
    try:
        u = (
            db.query(Unit)
            .options(
                joinedload(Unit.floor)
                .joinedload(Floor.building)
                .joinedload(Building.parcel)
            )
            .filter(Unit.ulpin == digits)
            .first()
        )
        if u is None:
            raise HTTPException(status_code=404, detail=f"No unit with ULPIN {digits}")

        floor = u.floor
        building = floor.building
        parcel = building.parcel
        return UnitDetailOut(
            unit_id=u.id,
            unit_code=u.unit_code,
            ulpin=u.ulpin,
            ulpin_grouped=format_ulpin(u.ulpin),
            area_sqm=u.area_sqm,
            status=u.status,
            owner_name=u.owner_name,
            ownership_type=u.ownership_type,
            synthetic=u.synthetic,
            floor_number=floor.floor_number,
            floor_code=floor.floor_code,
            building_id=building.id,
            building_name=building.name,
            is_hero_building=building.is_hero,
            parcel=ParcelOut(
                id=parcel.id,
                parcel_code=parcel.parcel_code,
                district_code=parcel.district_code,
                taluk_code=parcel.taluk_code,
                survey_block=parcel.survey_block,
                address=parcel.address,
            ),
        )
    finally:
        db.close()


# Static frontend (single-page Three.js app). Mounted last so /api/* wins.
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
