# Shared API format

This is the response format for the frontend and visualizations.

## visibility request

`GET /api/visibility`

query params:

- `lat` - lunar latitude in degrees, from -90 to 90
- `lon` - lunar longitude in degrees, from -180 to 180
- `time` - ISO 8601 timestamp with a timezone; results are returned in UTC

Coordinates are interpreted in the lunar mean Earth/rotation-axis frame (`MOON_ME`).

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
