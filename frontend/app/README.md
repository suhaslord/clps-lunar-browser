# CLPS Lunar Explorer

React + JavaScript + Vite + Cesium frontend.

## Run locally

From this directory:

```sh
npm install
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

Open http://127.0.0.1:5174/ and leave the terminal running. If the port is busy, use the existing server or choose another port and open the URL printed by Vite.

## Explore

- Drag the Moon to rotate and scroll/pinch to zoom.
- Choose near side, far side, or south pole; reset the view at any time.
- Toggle the rotation axis and the 30-degree latitude/longitude grid.
- Click the Moon to select lunar coordinates and copy them as JSON.
- At narrow widths, the map appears above the controls.

## Files

- `src/MoonMap.jsx`: NASA model loading, camera, lighting, coordinate picking.
- `src/moonGuides.js`: reference sphere, coordinate grid and axis.
- `src/App.jsx`: controls and shared selected-location state.
- `src/index.css`: responsive layout and styling.
- `public/MODEL-SOURCES.md`: source credits and model limitations.

The local NASA model includes imagery, without terrain relief. Camera-relative lighting is illustrative. Picks return latitude and east-positive longitude in degrees on the reference sphere. Model alignment is approximate, not validated for scientific measurements.

Selected coordinates reach the parent component through `onLocationSelect({ latitude, longitude })`. This viewer does not yet make requests to Suhas's backend or display mission markers. Backend integration will need to map these fields to the API's `lat` and `lon` parameters and supply a time where required.

## Checks

```sh
npm run build
npm run lint
```

Cesium currently produces a large bundle warning; the NASA model is approximately 13 MB and may take a moment to load the first time.
