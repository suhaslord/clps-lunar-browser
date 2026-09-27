# Moon model sources

## nasa-moon.glb

- Credit: NASA's Goddard Space Flight Center.
- Source: https://svs.gsfc.nasa.gov/14959/
- Original download: https://svs.gsfc.nasa.gov/vis/a010000/a014900/a014959/moon_small.glb
- Downloaded September 25, 2026; stored locally so the map does not depend on a remote embed.
- NASA describes this variant as a lunar color map wrapped onto a sphere without topography. Lighting in this app is illustrative, not a computed Sun position.
- This replaces the unavailable legacy embed at https://solarsystem.nasa.gov/gltf_embed/2366/ ; it is not asserted to be the identical legacy asset.
- The app rotates the model into lunar coordinates and scales its maximum radius to Cesium's Moon radius. Coordinate picking uses that reference sphere rather than terrain intersections. Imagery alignment is approximate and needs control-point validation before scientific use.

## moon-lroc-2k.jpg

- NASA's Goddard Space Flight Center, CGI Moon Kit: https://svs.gsfc.nasa.gov/4720/
- Download: https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/lroc_color_2k.jpg
- Retained as an orientation reference; not used by the active model renderer.
