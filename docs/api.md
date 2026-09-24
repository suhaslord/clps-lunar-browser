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

Azimuth and elevation are in degrees. For now, `visible` is true when elevation is above the flat local horizon; terrain blocking is not included yet. `site` stays `null` until requests are matched to a named landing site.

Sun and Earth positions are geometric at the requested timestamp, with no light-time correction.

Invalid coordinates or timestamps return `422`. Missing kernels return `503`, and SPICE calculation errors return `502`.

## Landing sites

`GET /api/sites` returns the small set in `data/landing_sites.json`. The listed coordinates use south latitudes as negative numbers and east longitudes as positive numbers. They are projected onto the SPICE lunar reference ellipsoid at zero height; terrain and site elevation are not applied yet.

To calculate a named site, use `GET /api/sites/{site_id}/visibility?time=...`. It returns the same visibility response as `/api/visibility`, with `site` set to the site ID. Unknown IDs return `404`.

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

Invalid coordinates, timestamps, ranges, or steps return `422`. Missing kernels return `503`, and SPICE calculation errors return `502`.

## JPL Horizons check

I checked five equator, mid-latitude, and south-pole cases against JPL Horizons using a topocentric lunar observer (`CENTER=coord@301`, geodetic `SITE_COORD` as east longitude, latitude, and zero km). The observer table used quantity 4 (airless apparent azimuth/elevation). Horizons reports apparent positions from DE441; this backend reports geometric positions from the DE440s kernel set, so the values are close rather than identical. Across the five cases, the largest differences were 0.0058° in Sun azimuth, 0.0057° in Sun elevation, 0.0022° in Earth azimuth, and 0.0002° in Earth elevation. The snapshots and a 0.02° tolerance are in `tests/test_spice_calculations.py`; the test suite does not call Horizons.

Reference: [JPL Horizons API](https://ssd-api.jpl.nasa.gov/doc/horizons.html) and [Horizons manual](https://ssd.jpl.nasa.gov/horizons/manual.html).
