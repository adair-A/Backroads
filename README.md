# Scenic Route Generator

An early local-first route-planning prototype built from OpenStreetMap data. It supports point-to-point drives and return loops, with route scoring that favors curves, scenery, optional elevation, and fewer dense-area interruptions. GPX export and navigation-app handoffs are available; live traffic, stops, saved/shared Backroads routes, and native turn-by-turn navigation are not implemented.

## About this fork

This is my personal fork of the [original Backroads project by ixbh](https://github.com/ixbh/Backroads). I used it as an AI-assisted development experiment, extending the fork with address search, route and elevation experiments, navigation handoffs, interface changes, and additional tests. The original project and upstream history remain credited through GitHub's fork relationship.

Development on this fork was heavily AI-assisted. I directed the changes, tested the project, and iterated on the results.

## Architecture

- `load_osm.py`: imports a regional OSM extract into PostGIS, rejecting private/inaccessible and unsuitable road classes.
- `curviness.py`: computes geometry-based curvature and intersection-conflict signals, then normalizes curvature to a regional 0–100 percentile.
- `load_scenic_features.py` and `scenery.py`: import explicit OSM landscape features and assign explainable water, forest, protected-land, countryside, natural-land, and viewpoint scores.
- `routing.py`: builds directed NetworkX graphs from exact OSM node identities, preserves forward and reverse one-way restrictions, filters known unpaved surfaces, keeps residential roads out of the preferred graph, combines stop/signal density with local road-network density for city avoidance, and uses residential streets only as penalized/connector fallbacks.
- `api.py`: FastAPI adapter for route generation and response summaries, with a bounded five-minute cache for the most recent expensive graph build.
- `road_store.py`: runtime provider boundary that keeps PostgreSQL/PostGIS and the read-only desktop SQLite snapshot interchangeable.
- `viewer.html`: MapLibre/OpenFreeMap click-to-pin client.

The route score combines length-weighted curviness with OSM scenery evidence. Dense-area avoidance combines nearby OSM stop/signal density with a local road-network-density proxy; it is not census population or live traffic. ETA uses documented road-class speed assumptions. These values are not navigation-grade.

## Setup

1. Create a Python 3.11+ virtual environment and run `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and set the server-side `DATABASE_URL`.
3. Apply `schema.sql`, import an OSM extract with `load_osm.py`, and run `curviness.py`. Existing databases created before the topology update should apply `migration_road_topology.sql` and re-run `load_osm.py` so exact OSM node IDs are populated.
4. Import and score landscape signals with `load_scenic_features.py --pbf minnesota-latest.osm.pbf --region minnesota --replace`, then `scenery.py --region minnesota`.
5. Optionally run a regional Valhalla height service and enrich terrain with `python elevation.py --region minnesota --valhalla-url http://localhost:8002`.
6. Start the API with `uvicorn api:app --reload --port 8000`.
7. Open `http://localhost:8000/`; FastAPI serves the viewer and API together. Opening `viewer.html` directly still falls back to `http://localhost:8000` for local development.

See `DEPLOYMENT.md` for the hosted beta architecture and iPhone/navigation roadmap.

## Windows desktop beta

The desktop beta keeps route calculation on the tester's Windows PC and does
not require Python, PostgreSQL, Docker, or a Render account. PostgreSQL remains
the source of truth; `export_desktop_data.py` creates a separate read-only
SQLite/RTree snapshot containing only runtime roads and precomputed scores.

Build flow:

```powershell
python export_desktop_data.py --region minnesota --output data/backroads.sqlite3
python -m pip install -r requirements-desktop.txt
python -m PyInstaller --noconfirm --clean BackroadBeta.spec
Compress-Archive -Path 'dist\Backroad Beta' -DestinationPath 'release\Backroad-Beta-Windows.zip'
```

The distributable is the complete `Backroad Beta` folder or its zip, not the
executable by itself. `Backroad Beta.exe` starts a loopback-only API, opens the
existing browser UI, and stops when the tester presses Enter in its small
console window. The basemap still requires internet access. See
`BETA_README.txt` and `DATA_LICENSE.txt` for tester and
OpenStreetMap data-distribution notices.

Opening the viewer as a plain `file://` URL may be restricted by browser security policies. The map style and tiles require internet access; routing itself uses the local database.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The focused tests use synthetic networks and do not require PostgreSQL.

## Environment and external services

- `DATABASE_URL` — required by import/scoring and the normal route API; never expose it to the browser.
- `BACKROADS_SQLITE_PATH` — optional route-API alternative pointing at a generated, read-only desktop snapshot.
- `VALHALLA_URL` — optional self-hosted Valhalla URL used by elevation enrichment and navigation validation (for example `http://localhost:8002`).
- `VALHALLA_ROUTE_VALIDATION=true` — opt in to resolving Backroads shaping points through Valhalla for legal driving geometry and turn maneuvers.
- `VALHALLA_TIMEOUT_SECONDS` — optional route-validation timeout; defaults to 30 seconds.
- `GEOCODER_URL` — replaceable address-search endpoint; defaults to the public OpenStreetMap Nominatim service for modest beta use.
- `GEOCODER_USER_AGENT` — identifying application/contact string sent to the geocoder.
- `GEOCODER_TIMEOUT_SECONDS` — address-search timeout; defaults to 10 seconds.
- PostgreSQL + PostGIS — required for importing, scoring, exporting, and normal development; not required on a tester's desktop.
- OpenFreeMap — public basemap style/tiles used by `viewer.html`; no API key.
- Geofabrik — optional source for downloading regional OSM PBF extracts.

## Current product limitations

- Route entry is address-first: a start address is required and the destination is optional. A blank destination generates a scenic return loop. Address searches are submitted only when building a route, cached locally, serialized to at most one public Nominatim request per second, and restricted to US results. See https://operations.osmfoundation.org/policies/nominatim/ before broader distribution.
- Loop distance is approximate. Ordinary loops evaluate deterministic alternative orientations and penalize repeated road pieces before selecting a winner; exploration loops still return one internally selected result.
- Exploration requests reject a target distance that is physically too short for the selected area's out-and-back distance; generated scenic legs are capped to prevent extreme preference-driven detours.
- Curviness, dense-area avoidance, OSM scenery proximity, and optional elevation enrichment are heuristics; visual-quality grading is not implemented.
- Paved-only mode excludes explicit dirt, gravel, compacted, unpaved surfaces and unknown tracks. Regular roads with no OSM surface tag remain usable but are disclosed, so pavement cannot yet be guaranteed for every mile.
- No toll, motorway, POI, or live traffic preferences yet.
- GPX track export and Google Maps, Apple Maps, and Waze handoff are available. Destination apps may recalculate between shaping points; saved/shareable Backroads URLs and native mobile turn-by-turn shells are not implemented.
- Exact OSM nodes prevent false bridge/underpass intersections. The internal planner does not model every OSM turn restriction, but optional Valhalla route validation resolves its scenic shaping points onto a navigation-grade path and supplies maneuver instructions. Without Valhalla, routes remain exploratory.
