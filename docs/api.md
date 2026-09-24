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
