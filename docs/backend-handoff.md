# Backend handoff

The backend covers named CLPS sites and arbitrary lunar coordinates for Sun/Earth visibility, terrain skylines, timelines and mission planning summaries. It preserves the existing FastAPI/SPICE architecture and project objective.

## Start the backend

Follow the root README: install requirements, run `python -m backend.setup_kernels`, run **`python -m backend.setup_terrain`**, then start Uvicorn. The global dataset download is 506 MiB; it stays outside Git. Both setup commands verify SHA-256 checksums, reuse verified local data and support `--check` for offline verification. Use `LUNAR_DEM_PATH` for another storage path; use `--path` when downloading there. `/ready` checks the required data.

## Connect the website

Use `http://127.0.0.1:8000` as the local API base or proxy `/api` to it. Default CORS allows both local Vite origins on port 5173. Configure `CORS_ORIGINS` before starting the server for a hosted frontend.

| Website feature | Route |
| --- | --- |
| Site picker | `/api/sites` |
| Coordinate + timestamp | `/api/visibility?lat=...&lon=...&time=...` |
| Coordinate + timeline | `/api/visibility/window?lat=...&lon=...&start=...&end=...&step_minutes=30` |
| Coordinate + planning summary | `/api/summary?lat=...&lon=...&start=...&end=...&step_minutes=30` |
| Coordinate terrain skyline | `/api/horizon?lat=...&lon=...` |
| Named site + timestamp | `/api/sites/odysseus-im1/visibility?time=...` |
| Named site + timeline | `/api/sites/odysseus-im1/visibility/window?start=...&end=...&step_minutes=30` |
| Named site + summary | `/api/sites/odysseus-im1/summary?start=...&end=...&step_minutes=30` |
| Named site terrain skyline | `/api/sites/odysseus-im1/horizon` |

Terrain is enabled by default everywhere. Coordinates exactly matching Athena or Odysseus use their named 20 m or 30 m profiles. Detailed profiles combine their local 40 km skyline with global terrain out to 300 km. Other positions use global LOLA terrain out to 300 km; exact custom coordinate profiles can also be prepared offline. Add `terrain=false` to visibility/timeline/summary requests for an explicitly labelled flat estimate. No request silently falls back when terrain data is missing.

Example browser request; `URLSearchParams` correctly encodes timezone offsets:

```js
const query = new URLSearchParams({
  lat: '-80.13', lon: '1.44',
  start: '2026-10-15T00:00:00Z',
  end: '2026-10-16T00:00:00Z', step_minutes: '30',
})
const response = await fetch(`${apiBase}/api/summary?${query}`)
if (!response.ok) {
  const error = await response.json()
  throw new Error(error.detail ?? 'Calculation unavailable')
}
const summary = await response.json()
```

Show the percentages, longest outages and UTC windows. `horizon_mode` labels terrain or flat; `terrain` provides source, resolution, range and observer height. Render failures as errors rather than zero sunlight or communications. Label visibility as a model estimate: `terrain.accuracy` remains unvalidated and `survey_grade` is false. Resolution is not positional accuracy; do not label a result measured or certain from a Boolean or grid spacing.

For the skyline, fetch `/api/horizon` for the same coordinates or the named site's `/horizon`. Plot `profile.horizon[i]` at `i * profile.azimuth_step` degrees under Sun/Earth markers. North is 0° and east is 90°. The terrain used by single-time, timeline and summary routes is identical.

## Scope and accuracy

- SPICE directions and terrain geometry use the same radial observer at DEM elevation plus an assumed 2 m height. Flat mode preserves the original reference-surface calculation.
- Athena uses 20 m and Odysseus uses 30 m local LOLA terrain. Global coverage remains about 474 m north/south. The combined skyline reaches 300 km; excluded inner radii are about 14 m, 21 m and 335 m respectively. The distant raster ceiling is conditional on represented heights, not a real-terrain accuracy certificate. Smaller landforms and unsurveyed instrument surroundings can be missed.
- Visibility uses body centres, and timelines are sampled at the selected cadence. Earth line of sight does not guarantee communications; sunlight visibility does not estimate electrical power.
- The terrain source uses DE421 `MOON_ME`, closely aligned to the runtime DE440 `MOON_ME_DE440_ME421` frame. Exact poles use one elevation estimate; longitude defines the local north/east basis. See [terrain documentation](../backend/terrain/README.md).
- The map branch's NASA GLB is a textured sphere without elevation. Its lighting does not represent backend Sun illumination. A sourced Blender terrain mesh can be displayed through Cesium while the backend continues these calculations.

Full response and error details are in [the API contract](api.md). The automated workflow verifies kernels, downloads/caches the global DEM, and runs geometry and API tests.
