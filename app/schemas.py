"""Pydantic response models (also drive the OpenAPI docs at /docs)."""
from typing import Any

from pydantic import BaseModel


class ParcelOut(BaseModel):
    id: int
    parcel_code: str
    district_code: str
    taluk_code: str
    survey_block: str
    address: str


class UnitOut(BaseModel):
    unit_id: int
    unit_code: str
    ulpin: str
    ulpin_grouped: str
    area_sqm: float
    status: str
    owner_name: str | None
    ownership_type: str | None
    synthetic: bool


class FloorOut(BaseModel):
    floor_number: int
    floor_code: str
    height_m: float
    elevation_m: float
    units: list[UnitOut]


class BuildingDetailOut(BaseModel):
    building_id: int
    name: str
    is_hero: bool
    osm_id: str | None
    levels: int
    height_m: float
    height_source: str
    is_estimated: bool
    centroid: list[float]
    footprint: dict[str, Any]
    parcel: ParcelOut
    floors: list[FloorOut]


class UnitDetailOut(BaseModel):
    unit_id: int
    unit_code: str
    ulpin: str
    ulpin_grouped: str
    area_sqm: float
    status: str
    owner_name: str | None
    ownership_type: str | None
    synthetic: bool
    floor_number: int
    floor_code: str
    building_id: int
    building_name: str
    is_hero_building: bool
    parcel: ParcelOut
