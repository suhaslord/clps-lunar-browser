# Backend handoff

The backend accepts east-positive longitude in -180..180 degrees, latitude in -90..90 degrees, and timestamps with a timezone. Responses use UTC. All routes are GET requests.

## Connect the website

Run the backend using the root README. Set your frontend's API base URL to `http://127.0.0.1:8000` for local development, or proxy `/api` to that server. Use the backend's named-site ID when selecting Athena so the terrain profile is applied; copying its coordinates to the generic coordinate endpoint produces a flat-horizon estimate.

| Website feature | Route |
| --- | --- |
| Site picker | `/api/sites` |
| Selected coordinate + timestamp | `/api/visibility?lat=...&lon=...&time=...` |
| Selected coordinate + timeline | `/api/visibility/window?lat=...&lon=...&start=...&end=...&step_minutes=30` |
| Selected coordinate + planning summary | `/api/summary?lat=...&lon=...&start=...&end=...&step_minutes=30` |
| Named site + timestamp | `/api/sites/athena-im2/visibility?time=...` |
| Named site + timeline | `/api/sites/athena-im2/visibility/window?start=...&end=...&step_minutes=30` |
| Named site + planning summary | `/api/sites/athena-im2/summary?start=...&end=...&step_minutes=30` |
| Terrain skyline and provenance | `/api/sites/athena-im2/horizon` |

Example browser request (use `URLSearchParams` so timezone offsets are encoded):

```js
const query = new URLSearchParams({
  start: '2026-10-15T00:00:00Z',
  end: '2026-10-16T00:00:00Z',
  step_minutes: '30',
})
const response = await fetch(`${apiBase}/api/sites/athena-im2/summary?${query}`)
if (!response.ok) {
  const error = await response.json()
  throw new Error(error.detail ?? 'Calculation unavailable')
}
const summary = await response.json()
```

Show summary percentages, longest darkness/communications blackout, and the returned UTC windows. Use `horizon_mode` to label the result as `terrain` or `flat`. Do not turn a failed request into zero sunlight or zero communications; show the error and let the user retry.

The horizon response is `{site, terrain_available, profile}`. A profile's `horizon[i]` is the skyline elevation in degrees at azimuth `i * azimuth_step` (north = 0, east = 90). Plot it under the Sun/Earth markers. A missing profile returns `terrain_available: false` and `profile: null`; it is not an all-zero measured terrain horizon. Unknown sites return 404, invalid profiles return 503.

## Scope and accuracy

- Sun/Earth directions use NAIF SPICE and the documented DE440 kernel set. Existing tests compare five cases against saved JPL Horizons references with a 0.02 degree tolerance.
- Athena's skyline comes from NASA PGDA LOLA, 80 m/pixel, within 40 km, at an assumed 2 m observer height. The closest 160 m is excluded. The profile includes lunar curvature and records its data source, coordinate frame, and elevation datum.
- Body directions still use the reference surface at zero altitude; the skyline uses the DEM surface. This is an approximation, not a complete high-precision surface-observer model.
- Arbitrary coordinates and Odysseus have flat-horizon visibility. There is no global terrain service behind coordinate picking.
- Visibility uses the centre of each body. Earth visibility indicates geometric line of sight, not guaranteed communications; sunlight visibility does not estimate power generation.
- Timeline transitions are sampled, with no substep crossing refinement. A 30 minute step gives approximate windows at that cadence. Requests are limited to 2,000 samples.
- The map branch's NASA GLB is a textured sphere without elevation. Its illustrative light is not backend Sun illumination. It does not supply terrain to the API.

Terrain meshes made in Blender should use sourced elevation data and preserve lunar coordinates, metres, and the reference datum. They can be displayed through Cesium while the backend continues to calculate the visibility results.
