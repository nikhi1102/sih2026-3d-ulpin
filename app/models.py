"""
SQLAlchemy ORM models: parcel -> building -> floor -> unit.

PRODUCTION NOTE (see README.md "Production path" for the full mapping):
  - `footprint_geojson` / `geojson` (TEXT columns holding GeoJSON strings)
    become PostGIS `geometry(Polygon, 4326)` columns in production, with a
    GiST index for spatial queries. The API contract (GeoJSON in/out) does
    not change -- only the storage type does.
"""
from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Parcel(Base):
    """Cadastral parcel -- the land record a building sits on."""

    __tablename__ = "parcels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parcel_code: Mapped[str] = mapped_column(String, unique=True)
    district_code: Mapped[str] = mapped_column(String(2))
    taluk_code: Mapped[str] = mapped_column(String(2))
    survey_block: Mapped[str] = mapped_column(String(4))
    address: Mapped[str] = mapped_column(String)
    # Parcel boundary as GeoJSON (lon/lat). In this prototype it is set
    # equal to the building footprint (1 building : 1 parcel simplification)
    # -- see PRODUCTION note in README for how real cadastral parcels differ.
    geojson: Mapped[str] = mapped_column(Text)

    buildings: Mapped[list["Building"]] = relationship(back_populates="parcel")


class Building(Base):
    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parcel_id: Mapped[int] = mapped_column(ForeignKey("parcels.id"))
    name: Mapped[str] = mapped_column(String)
    osm_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # Real-world footprint, GeoJSON Polygon, coordinates in [lon, lat].
    footprint_geojson: Mapped[str] = mapped_column(Text)
    centroid_lon: Mapped[float] = mapped_column(Float)
    centroid_lat: Mapped[float] = mapped_column(Float)

    levels: Mapped[int] = mapped_column(Integer)
    height_m: Mapped[float] = mapped_column(Float)
    # "osm_levels" (real tag) or "estimated_default" (3.0 m/floor fallback,
    # or a deliberate demo override for the hero building -- see seed.py).
    height_source: Mapped[str] = mapped_column(String)
    is_estimated: Mapped[bool] = mapped_column(Boolean, default=True)

    is_hero: Mapped[bool] = mapped_column(Boolean, default=False)

    parcel: Mapped["Parcel"] = relationship(back_populates="buildings")
    floors: Mapped[list["Floor"]] = relationship(
        back_populates="building", order_by="Floor.floor_number"
    )


class Floor(Base):
    __tablename__ = "floors"
    __table_args__ = (UniqueConstraint("building_id", "floor_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    building_id: Mapped[int] = mapped_column(ForeignKey("buildings.id"))
    floor_number: Mapped[int] = mapped_column(Integer)  # 1-based
    floor_code: Mapped[str] = mapped_column(String(2))  # ULPIN segment
    height_m: Mapped[float] = mapped_column(Float)
    elevation_m: Mapped[float] = mapped_column(Float)  # height of floor slab above ground

    building: Mapped["Building"] = relationship(back_populates="floors")
    units: Mapped[list["Unit"]] = relationship(
        back_populates="floor", order_by="Unit.unit_code"
    )


class Unit(Base):
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    floor_id: Mapped[int] = mapped_column(ForeignKey("floors.id"))
    unit_code: Mapped[str] = mapped_column(String(2))  # ULPIN segment
    ulpin: Mapped[str] = mapped_column(String(14), unique=True, index=True)

    area_sqm: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String)  # "owned" | "vacant"

    # SYNTHETIC ownership data -- illustrative only, never real records.
    owner_name: Mapped[str | None] = mapped_column(String, nullable=True)
    ownership_type: Mapped[str | None] = mapped_column(String, nullable=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)

    floor: Mapped["Floor"] = relationship(back_populates="units")
