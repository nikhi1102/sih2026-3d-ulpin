# 3D ULPIN Generation & Vertical Property Mapping

Prototype for **SIH26011**. Real building footprints for a Mylapore, Chennai
neighbourhood, extruded to 3D. Select the hero building, watch it explode
into its 5 floors, click a unit, and resolve its 14-digit ULPIN, owner,
floor/unit, area, and parent parcel — the vertical/stacked-property
ownership problem the statement asks for.

Built for a 2-day hackathon timeline. Optimized for **zero-setup
reliability**: one `pip install`, one `uvicorn` command, works fully
offline, no Docker, no PostGIS, no npm/build step.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open **http://localhost:8000**. The database is created and seeded
automatically on first request — no manual migration or seed step. The app
is pre-populated: 46 real building footprints, one exploded into 5 floors
x 4 units each.

Requires Python 3.10+ (built and tested on 3.11, per the brief; also
verified against the plain `python3.14`). `requirements.txt` intentionally
pins minimum versions, not exact ones — pinning old exact versions of
`pydantic` breaks on brand-new Python releases that don't have prebuilt
wheels for them yet, which is exactly the kind of setup failure this
prototype is trying to avoid on demo day.

The app's **data** works fully offline (see "Data & offline behaviour"
below) — it never calls Overpass at runtime. The one exception is
Three.js itself: per the specified stack, it loads from a CDN
(`<script src="https://cdnjs.../three.min.js">`) rather than being
vendored, so the *first* page load needs internet; the browser caches it
after that.

### Using it

1. **Orbit** the scene (drag to rotate, scroll to zoom) — the amber
   building is the hero.
2. **Click the hero building** — it animates open into its 5 floors, each
   with 4 individually-clickable units (green = owned, blue = vacant).
3. **Click a unit** — the right-hand panel resolves its ULPIN, synthetic
   owner, floor/unit, area, and parent parcel.
4. **Search a ULPIN** (top-right box, e.g. `33-01-01-0001-05-01`) — flies
   the camera to that unit and opens the same panel. Works for units in
   any building, not just the hero.
5. **Collapse building** / **Reset view** — self-explanatory controls,
   bottom of the top-right control panel.

## What's real vs. illustrative (read this to judges)

- **Footprints are real**: fetched from OpenStreetMap (Overpass API) for a
  small area of Mylapore, Chennai near Kapaleeshwarar Temple. A snapshot
  is committed to the repo (`app/data/footprints_sample.geojson`) and
  loaded by default, so the demo works offline and is immune to Overpass
  being slow/down.
- **Heights/floor counts are mostly estimated**: read from OSM
  `building:levels` where the tag exists, else a documented default of
  3.0 m/floor. Every building's API response says whether its height was
  measured (`osm_levels`) or guessed (`estimated_default`) via
  `is_estimated` / `height_source`.
- **The hero building's 5-floor split is a deliberate demo override**, not
  from OSM data (OSM has no floor-level tagging for individual units in
  this area — no residential registry is open data). Flagged
  `height_source: "demo_hero_override"` in the API, still `is_estimated: true`.
- **ULPIN numbers are synthetic but deterministically generated** from a
  documented scheme (state+district+taluk+survey-block+floor+unit,
  `app/ulpin.py`) — not real Bhu-Aadhaar numbers, no such open registry
  exists to draw from.
- **Ownership data is 100% synthetic** — seeded fake names or names, marked
  `synthetic: true` in every API response and shown with an
  "Illustrative" badge in the UI. Never presented as real records.

## Data & offline behaviour

`scripts/fetch_osm_footprints.py` is the **only** thing that talks to the
network. It queries the Overpass API for a small bounding box in
Mylapore, Chennai and writes a GeoJSON `FeatureCollection` to
`app/data/footprints_sample.geojson`. That output file is committed to
the repo and is what the running app actually loads — the app itself
**never** calls Overpass at runtime.

To refresh the sample with current OSM data:

```bash
python3 scripts/fetch_osm_footprints.py
rm app/data/ulpin.db   # force a reseed from the refreshed footprints
uvicorn app.main:app --reload
```

If Overpass is unreachable, the script exits with an error and leaves the
committed file untouched — the app keeps working from whatever was last
committed.

## ULPIN scheme

```
33            Tamil Nadu state code (fixed)      2 digits
district      district code                       2 digits
taluk         taluk code                           2 digits
survey_block  cadastral survey block number         4 digits
floor         floor number within the building      2 digits
unit          unit number within the floor          2 digits
------------------------------------------------------------
total                                              14 digits
```

The brief lists `taluk(3)` alongside the other widths, but summing all
the listed segments gives 15 digits, not the 14 the brief also specifies
— real ULPIN (Bhu-Aadhaar) has no public codebook to defer to either way.
This prototype compresses taluk to 2 digits to land on exactly 14, and
documents the deviation in `app/ulpin.py` rather than silently guessing.
Every other segment matches the brief exactly. Display format groups it
as `33-01-01-0001-05-01`.

## Architecture

```
parcel (1) --- (N) building (1) --- (N) floor (1) --- (N) unit
```

- **Backend**: Python 3.11, FastAPI, SQLAlchemy ORM, SQLite (file-based,
  zero server setup). OpenAPI docs at `/docs`.
- **Frontend**: one static HTML page (`static/index.html` +
  `static/app.js`), Three.js r128 + OrbitControls from CDN. No build
  step, no npm.
- **DB**: `app/data/ulpin.db`, created and seeded automatically on first
  app startup if empty (`app/seed.py`).

### API

| Endpoint                  | Description                                            |
|----------------------------|--------------------------------------------------------|
| `GET /api/footprints`      | GeoJSON `FeatureCollection` of all building footprints |
| `GET /api/building/{id}`   | Full vertical breakdown: floors -> units, with ULPIN   |
| `GET /api/unit/{ulpin}`    | Single unit by ULPIN (raw or grouped format); 404 if not found |
| `GET /docs`                | Interactive OpenAPI docs                                |

### Architecture seams (stubbed on purpose, not implemented)

Two modules exist purely as documented extension points for future work,
per the brief — implementing them was explicitly out of scope for this
prototype:

- **`app/height_estimator.py`** — floor-count/height estimation.
  Currently: OSM `building:levels` tag, else a 3.0 m/floor default.
  Swap target: an ML model (shadow-length or photogrammetry-based height
  regression). Nothing else in the codebase needs to change — `seed.py`
  and the API only depend on this module's function signature.
- **`app/reconstruction.py`** — the hero building's 3D form.
  Currently: a flat extrusion of its OSM footprint polygon. Swap target:
  a real reconstructed mesh (photogrammetry/LiDAR capture, e.g. via
  COLMAP), served as glTF from a (not-yet-implemented)
  `GET /api/building/{id}/mesh`.

## Production path (PostGIS)

This prototype uses SQLite with GeoJSON stored as `TEXT` columns
(`Building.footprint_geojson`, `Parcel.geojson`) specifically so it runs
with zero setup — no Docker, no Postgres install, no spatial extension.
The real target for this system is **PostGIS**. The mapping is a storage
change, not a rewrite:

- `TEXT` GeoJSON columns -> `geometry(Polygon, 4326)` columns, populated
  via `ST_GeomFromGeoJSON`.
- Add a GiST index on every geometry column for spatial queries
  (`ST_Intersects`, `ST_Contains`, "find building under this click"
  server-side instead of client-side raycasting).
- `GET /api/footprints` would use `ST_AsGeoJSON` at the DB layer instead
  of `json.loads()` on a stored string; the API response shape is
  unchanged either way.
- SQLAlchemy models would swap `Text` columns for GeoAlchemy2's
  `Geometry` type; everything else (relationships, the parcel -> building
  -> floor -> unit hierarchy, the ULPIN generation logic) is
  storage-agnostic and carries over unchanged.
- The 1-building-per-parcel simplification in this prototype (parcel
  geometry set equal to building footprint) would be replaced by real
  cadastral parcel boundaries, which can differ from the building
  footprint sitting on them (setbacks, undeveloped portions, etc).

## Project structure

```
app/
  main.py              FastAPI app, routes
  models.py            SQLAlchemy models: Parcel, Building, Floor, Unit
  schemas.py           Pydantic response models
  database.py          SQLite engine/session
  seed.py              Seeds DB from the committed OSM sample on startup
  ulpin.py             ULPIN generation/parsing/formatting
  geo.py               lon/lat <-> local meters, polygon area
  height_estimator.py  ARCHITECTURE SEAM (stub, documented)
  reconstruction.py    ARCHITECTURE SEAM (stub, documented)
  data/
    footprints_sample.geojson   committed real OSM data (offline default)
    ulpin.db                    generated on first run, gitignored
scripts/
  fetch_osm_footprints.py   optional: refresh the committed sample from Overpass
static/
  index.html          the single page
  app.js              Three.js scene, explode animation, picking, search
requirements.txt
```
