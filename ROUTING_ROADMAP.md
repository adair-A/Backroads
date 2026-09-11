# Routing quality roadmap

## Current measured baseline

Using the schema-v1 Minnesota desktop snapshot (299,726 roads), a cold 35-mile
Minneapolis loop loaded 64,114 candidate roads and built an 81,115-node graph.
The multi-candidate selector returned 36.96 miles with 0.5% repeated road
distance and 5.6% distance error in 12.7 seconds. This is a useful quality
baseline, but not an acceptable interactive cold-start target.

## Decisions

### Keep PostgreSQL/PostGIS as the source of truth

PostGIS remains the right store for OSM geometry, spatial enrichment, score
versioning, regional exports, and offline analysis. SQLite/RTree remains the
right immutable desktop snapshot. A vector database does not solve this
structured graph/spatial problem.

### Adopt Valhalla as the navigation-grade path layer

Backroads should generate and rank scenic waypoint skeletons. Valhalla should
resolve legal paths between those waypoints and supply turn restrictions,
maneuvers, map matching, elevation, and eventually traffic overlays. Backroads
then re-scores the returned geometry and selects the final alternative.

Official references:

- https://valhalla.github.io/valhalla/api/turn-by-turn/overview/
- https://valhalla.github.io/valhalla/sif/
- https://valhalla.github.io/valhalla/concepts/speeds/

GraphHopper is the strongest hosted alternative when operating Valhalla is too
expensive. Mapbox Directions is the fastest route to commercial live traffic
and closures, but it cannot directly execute Backroads' per-edge scenic cost.
OSRM is fast and simple, but less attractive for dynamic scenic costing and
elevation. pgRouting is useful for analysis and K-shortest-path experiments
inside PostGIS, but it is not a replacement for navigation guidance.

### Add Redis only for hosted deployments

Redis should hold short-lived graph/result caches, distributed route-generation
locks, rate limits, and provider responses. It should not become the canonical
road database. Desktop builds continue without Redis.

### Add live data behind provider interfaces

Recommended order:

1. Valhalla legal-path and maneuver adapter.
2. Elevation enrichment (implemented through Valhalla `/height`).
3. Mapbox traffic/closure adapter or regional 511/WZDx feeds.
4. NWS forecast and alert context for US routes.
5. Optional imagery experiments after route feedback provides ground truth.

Waze should be treated as a navigation handoff/deep-link destination, not as a
general-purpose traffic-data API.

## Next implementation milestones

1. Persist benchmark cases with expected distance, overlap, connector share,
   runtime, and known-bad-road assertions.
2. Reject or re-rank provider routes that violate distance or repetition limits.
3. Replace linear nearest-node scans with a spatial index.
4. Cache graph builds by region/tile and move CPU-heavy generation out of the
   synchronous FastAPI request thread.
5. Return two or three genuinely diverse alternatives to the client.

Implemented: the `ValhallaRoutingProvider` sends a bounded set of scenic
shaping points as `break`/`via` locations, decodes Valhalla's navigation
geometry, returns maneuvers, and fails open to the original scenic planning
route. The API/UI/GPX path all expose the validation state.
