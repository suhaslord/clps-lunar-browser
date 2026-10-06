# Shared API format

This is the response format for the frontend and visualizations.

## visibility request

`GET /api/visibility`

query params:

- `lat` - lunar latitude in degrees, from -90 to 90
- `lon` - lunar longitude in degrees, from -180 to 180
- `time` - ISO 8601 timestamp with a timezone; results are returned in UTC

Coordinates are interpreted in the lunar mean Earth/rotation-axis frame (`MOON_ME`). Longitude is east-positive and accepted from -180 to 180 degrees, matching the backend's coordinate convention.

example:

```
/api/visibility?lat=-89.5&lon=135&time=2026-10-03T18:00:00Z
```

## response

```json
{
  "site": null,
  "latitude": -89.5,
  "longitude": 135.0,
  "time": "2026-10-03T18:00:00Z",
  "sun": {
    "azimuth": 124.2,
    "elevation": 3.7,
    "visible": true
  },
  "earth": {
    "azimuth": 241.8,
    "elevation": 7.1,
    "visible": true
  }
}
```

Azimuth and elevation are in degrees. For coordinate requests, `visible` means elevation is above the flat local horizon. `site` is `null` for coordinate requests.

Sun and Earth positions are geometric at the requested timestamp, with no light-time correction.

Invalid coordinates or timestamps return `422`. Missing kernels return `503`, and SPICE calculation errors return `502`.

## Landing sites

`GET /api/sites` returns the small set in `data/landing_sites.json`. The listed coordinates use south latitudes as negative numbers and east longitudes as positive numbers. The SPICE observer is projected onto the reference ellipsoid at zero height.

To calculate a named site, use `GET /api/sites/{site_id}/visibility?time=...`. It returns the same visibility response as `/api/visibility`, with `site` set to the site ID. Unknown IDs return `404`.

Athena has a [LOLA terrain profile](../backend/terrain/README.md). Its Sun and Earth records also include `flat_visible` and `terrain_horizon` (degrees); `visible` compares body elevation with that horizon. The profile uses a 2 m instrument height above the DEM surface. Sites without a profile keep the old flat-horizon response. The DEM frame is DE421 `MOON_ME`, closely aligned with this backend's DE440 `MOON_ME`; see the terrain README for the remaining frame and site-location uncertainty.

`GET /api/sites/{site_id}/visibility/window` takes the same `start`, `end`, and `step_minutes` parameters as the coordinate window and returns the same sample structure, including terrain fields when available.

`GET /api/sites/{site_id}/summary` takes those parameters and returns `sunlight_percent`, `earth_visible_percent`, `both_available_percent`, longest darkness/communication blackout in minutes, and `windows` for sunlight, Earth visibility, and both together. Each window has `start` and `end`. A sample describes the interval from its timestamp to the next step (or requested `end` if sooner). The sample at `end` contributes no duration. Boundaries are only accurate to the requested sampling step; no crossing time is refined. The summary requires `end` after `start`.

## visibility window request

`GET /api/visibility/window`

query params:

- `lat` - lunar latitude in degrees, from -90 to 90
- `lon` - lunar longitude in degrees, from -180 to 180
- `start` - ISO 8601 timestamp with a timezone
- `end` - ISO 8601 timestamp with a timezone, at or after `start`
- `step_minutes` - positive integer sample interval; defaults to 30

The response is a list of `{ "time", "sun", "earth" }` records. Samples start at `start` and continue at the requested interval. `end` is included when it falls on that interval; an off-grid `end` is not added as an extra sample. The records use the same body fields as `/api/visibility` and return timestamps in UTC.

Example:

```text
/api/visibility/window?lat=-89.5&lon=135&start=2026-10-03T00:00:00Z&end=2026-10-04T00:00:00Z&step_minutes=30
```

```json
[
  {
    "time": "2026-10-03T00:00:00Z",
    "sun": {"azimuth": 143.4794, "elevation": 0.6287, "visible": true},
    "earth": {"azimuth": 226.0028, "elevation": 4.9491, "visible": true}
  }
]
```

Invalid coordinates, timestamps, ranges, or steps return `422`. Windows over 2,000 samples return `422`. Missing kernels or an invalid terrain profile return `503`, and SPICE calculation errors return `502`.

## JPL Horizons check

I checked five equator, mid-latitude, and south-pole cases against JPL Horizons using a topocentric lunar observer (`CENTER=coord@301`, geodetic `SITE_COORD` as east longitude, latitude, and zero km). The observer table used quantity 4 (airless apparent azimuth/elevation). Horizons reports apparent positions from DE441; this backend reports geometric positions from the DE440s kernel set, so the values are close rather than identical. Across the five cases, the largest differences were 0.0058° in Sun azimuth, 0.0057° in Sun elevation, 0.0022° in Earth azimuth, and 0.0002° in Earth elevation. The snapshots and a 0.02° tolerance are in `tests/test_spice_calculations.py`; the test suite does not call Horizons.

Reference: [JPL Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html) and [Horizons manual](https://ssd.jpl.nasa.gov/horizons/manual.html).

## Frontend integration endpoints

`GET /api/summary` accepts `lat`, `lon`, `start`, `end`, and optional `step_minutes` (30 by default). It returns the same percentages, longest outages, and windows as the named-site summary, with `site: null`, the requested `latitude` and `longitude`, and `horizon_mode: "flat"`. It requires `end` after `start` and uses the same 2,000 sample limit and error codes as visibility windows. It does not automatically apply terrain at coordinates that happen to match a named site.

Named-site summaries additionally return `horizon_mode: "terrain"` for a site with a profile, or `"flat"` otherwise.

`GET /api/sites/{site_id}/horizon` returns `{ "site": "athena-im2", "terrain_available": true, "profile": { ... } }`. The profile is the exact stored data used for masking, including `horizon`, `azimuth_step`, `source`, lunar frames, datum radius, pixel scale, range and observer height. Skyline elevation `horizon[i]` is in degrees at azimuth `i * azimuth_step`. Sites without a profile return `terrain_available: false` and `profile: null`. Unknown sites return 404 and invalid profiles return 503. This endpoint does not require SPICE kernels.

`GET /health` returns `{ "ok": true }` for a running API. `GET /ready` also checks a real SPICE calculation at the project reference date and validates all configured terrain profiles. It returns 503 if these checks fail. Readiness does not guarantee ephemeris coverage at every user-requested date.

Cross-origin GET requests from the local Vite origins on port 5173 are allowed by default. Set `CORS_ORIGINS` before startup for a comma-separated list of other origins, or an empty string to disable CORS. See [backend handoff](backend-handoff.md) for browser request examples and accuracy limits.
