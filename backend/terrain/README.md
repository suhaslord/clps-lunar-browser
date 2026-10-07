# LOLA terrain coverage

## Global locations

`python -m backend.setup_terrain` downloads NASA SVS's [64-pixel/degree LOLA displacement TIFF](https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/ldem_64_uint.tif), described in the [CGI Moon Kit](https://svs.gsfc.nasa.gov/4720/). This elevation map was reformatted directly from the LOLA team's spring-2019 gridded data. It is separate from the site's colour maps, which are optimized for appearance. The source [PDS label](https://imbrium.mit.edu/DATA/LOLA_GDR/CYLINDRICAL/IMG/LDEM_64.LBL) identifies the grid's mean Earth/polar axis DE421 coordinates, planetocentric latitude, east-positive longitude and 1,737,400 m spherical datum.

The uncompressed unsigned-16-bit TIFF is 23,040 × 11,520, north at the top, centred on 0° longitude (-180° at its western edge, +180° at its eastern edge). Pixel centres are half a cell inside the edges. Its integer encoding is `height_m = DN * 0.5 - 10000`, relative to 1,737,400 m. Equivalently, radius is `1727400 + DN * 0.5`. North/south spacing is about 473.8 m; east/west spacing narrows with latitude. The 506 MiB file is downloaded once, SHA-256 verified and ignored by Git. `LUNAR_DEM_PATH` can select a different storage path; `setup_terrain --check` verifies offline.

`global_dem.py` memory-maps the TIFF, reads only the surrounding cells in bounded stripes, and caches up to 64 exact coordinate profiles. The local spherical bounding box wraps longitude and includes every longitude when its range crosses either pole. Observer elevation is bilinearly interpolated across surrounding cells, with longitude wrapping. In the innermost polar half-cell, it blends to the first/last latitude ring’s mean at the pole, giving each exact pole one longitude-independent elevation estimate. DEM cell centres are placed at their spherical radii, the observer position is subtracted, and local east/north/up components determine azimuth and elevation. This includes curvature. Each cell's half-diagonal approximates its angular footprint and contributes to overlapping 0.5° bins; the highest elevation is retained. Missing/invalid cells cause an error.

The profile spans 40 km and excludes the nearest two pixels (about 948 m globally). This is a coarse planning model: it cannot resolve smaller landforms or very local slopes, and it omits obstructions beyond the range. The LOLA gridded source fills/interpolates areas between laser measurements and notes possible artifacts at latitude band boundaries. It is not a high-resolution measured survey at every location. At exact poles, supplied longitude defines the local north/east basis; it does not change observer elevation.

## Detailed Athena profile

`profiles/athena-im2.json` comes from NASA PGDA's [LDEM_80S_80MPP_ADJ.TIF](https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_80MPP_ADJ.TIF), described on the [product page](https://pgda.gsfc.nasa.gov/products/90). This is an 80 m/pixel south-polar stereographic LOLA DEM in DE421 `MOON_ME`. The CRS gives a 1,737,400 m spherical radius; pixels contain metres above that radius. The checked-in profile is about 19 KB and applies to Athena's listed coordinates through both named and coordinate routes.

Regenerate with `python -m backend.terrain.preprocess athena-im2`. GDAL reads a window of the remote cloud-optimized GeoTIFF. You can pass `--dem /path/to/LDEM_80S_80MPP_ADJ.TIF`. `--radius-km`, `--step` and `--height-m` control range, azimuth spacing and instrument height. Defaults match the checked-in 40 km, 0.5°, assumed 2 m observer profile. The closest 160 m is excluded. The API does not need this large polar DEM because the skyline is checked in. Odysseus uses the global DEM because its 40 km surroundings extend beyond the detailed south-polar dataset's edge.

Preprocessing rejects masked observer elevations, including finite nodata sentinels. The DEM must contain the entire projected read window, which extends 10% beyond the requested radius to allow for polar projection scale. A window crossing the dataset edge is rejected instead of silently clipping distant terrain; use a smaller radius or a larger DEM.

The projected CRS must use metres and the spherical 1,737,400 m lunar reference radius. Other planetary datums and projected units are rejected instead of being labelled as LOLA lunar data.

## Shared observer and model limits

Single-time, timeline, summary and skyline routes select the same profile. SPICE body directions use the same radial observer position as terrain: datum radius + site DEM elevation + 2 m. `terrain=false` explicitly requests the original reference-surface, flat-horizon calculation. Missing global data never silently switches the requested model.

NAIF's [DE440 lunar frame kernel](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/fk/moon_de440_220930.tf) defines runtime `MOON_ME` as `MOON_ME_DE440_ME421`, aligned to DE421 `MOON_ME` within 3.071 × 10⁻⁷ radians (about 0.53 m on the Moon) over 2000–2040. We use this close approximation without an invented rotation. Listed landing coordinates are rounded to hundredths of a degree; more precise positions can change the terrain horizon. Both profiles record provenance, source/runtime frames, datum, site elevation, resolution, range, height, skyline and peak ranges.

Visibility uses body centres rather than disk edges. Earth line of sight is not a communications link budget; sunlight visibility is not solar power output. Timeline boundaries are approximate at the chosen sampling cadence. The frontend's NASA GLB is a textured sphere and supplies no terrain data to this service.
