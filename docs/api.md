# shared api format

this is the main format frontend + visualizations should build around for now.

## visibility request

`GET /api/visibility`

query params:

- `lat` - lunar latitude in degrees
- `lon` - lunar longitude in degrees
- `time` - UTC time in ISO format

example:

```
/api/visibility?lat=-89.5&lon=135&time=2026-10-03T18:00:00Z
```

## response

```json
{
  "site": "Shackleton Rim",
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

azimuth/elevation are degrees. `visible` will eventually include terrain blocking too.
