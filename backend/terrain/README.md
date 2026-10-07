# Terrain data and accuracy

## Sources and selection

`python -m backend.setup_terrain` downloads NASA SVS's [64-pixel/degree LOLA elevation TIFF](https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/ldem_64_uint.tif), described in the [CGI Moon Kit](https://svs.gsfc.nasa.gov/4720/). Elevation is derived from scientific LOLA gridded data; the display colour map is separate. The source [PDS label](https://imbrium.mit.edu/DATA/LOLA_GDR/CYLINDRICAL/IMG/LDEM_64.LBL) identifies planetocentric latitude, east-positive longitude, DE421 mean Earth/polar axis coordinates and the 1,737,400 m datum.

The 23,040 × 11,520 unsigned-16-bit TIFF is north-up, spanning −180° to +180° longitude, with half-cell pixel centres. Decode `height_m = DN * 0.5 - 10000`. Its north/south spacing is about 473.8 m; east/west spacing narrows with latitude. The 0.5 m encoding increment does not establish vertical accuracy. The 506 MiB file is checksum verified, memory mapped, read in bounded stripes and ignored by Git. `LUNAR_DEM_PATH` selects another path; `setup_terrain --check` verifies offline.

Exact catalog positions use checked-in profiles generated from [NASA PGDA's polar LOLA products](https://pgda.gsfc.nasa.gov/products/90):

| Position | Local source | Grid spacing | Local range | Excluded inner radius |
| --- | --- | ---: | ---: | ---: |
| Athena | `LDEM_80S_20MPP_ADJ.TIF` | 20 m | 40 km | 14.142 m |
| Odysseus | `LDEM_75S_30MPP_ADJ.TIF` | 30 m | 40 km | 21.213 m |
| Other coordinates | NASA global 64 ppd | 473.8 m north/south | 300 km | 335.029 m |

Odysseus's surrounding terrain crosses the 80°S dataset boundary, so its profile uses the larger 75°S coverage. Named profiles include coarse global terrain outside the local range, with half-cell overlap at the seam, extending the combined horizon to 300 km. `outer_terrain` records that source's separate resolution and range. The outer geometry uses the detailed site's elevation and observer height; it does not introduce a second observer. All routes select the same profile.

Coordinates not matching a detailed profile retain global coverage. Finer raster cells do not automatically establish finer positional accuracy, resolve every landform, or certify a survey.

## Geometry and distant terrain

Global observer elevation uses bilinear interpolation, longitude wrapping and a longitude-independent polar-cap estimate. Projected observers now also use bilinear pixel-centre interpolation. Positive-weight missing observer cells fail; zero-weight neighbours are ignored. Missing terrain cells in the requested annulus fail.

Each terrain cell is placed at its spherical radius and converted to local east/north/up components, including lunar curvature. The approximate half-diagonal footprint contributes to overlapping 0.5° azimuth bins; each retains its maximum elevation. The inner exclusion now corresponds to a half-diagonal rather than two full pixels. Terrain within this radius and sub-cell slopes or obstacles remain unresolved. Preprocessing uses bounded stripes, validates north-up metres, true scale at the projection pole and the lunar spherical datum, bounds polar projection scale, and requires full window coverage.

The pinned global raster is checked for missing cells and its maximum encoded height is calculated, including half a quantization increment. `distant_terrain_ceiling_deg` is a decreasing spherical envelope for omitted distant raster cell centres, including overlap at the range edge. `distant_raster_bounded` means this ceiling lies below every represented skyline bin. If false, more distant represented terrain may still affect the skyline; per-body `distant_raster_may_block` checks elevation against the ceiling.

**This is a bound on the represented raster only.** It does not bound unresolved real terrain, registration error, interpolation error or instrument position uncertainty. The ceiling assumes the pinned raster's encoded height envelope; it is not a physical terrain certificate.

## Building a detailed profile

Regenerate either named profile with:

```sh
python -m backend.terrain.preprocess athena-im2 --fetch-window backend/terrain/data/athena20-window.tif
python -m backend.terrain.preprocess odysseus-im1
```

For another position and an appropriate independently sourced polar DEM:

```sh
python -m backend.terrain.preprocess research-site --lat -85.123456 --lon 30.123456 \
  --dem /path/to/lunar-dem.tif --source-url https://example.org/lunar-dem.tif
```

The coordinate form writes `profiles/coordinate-research-site.json`; the service selects it at exactly those coordinates. Multiple matching profiles return 503. Nearby positions do not reuse the observer's skyline. Custom data must actually use the documented frame and datum: the CRS checks cannot independently verify a caller's scientific provenance. Local custom input requires `--source-url`, avoiding an invented NASA attribution.

`--fetch-window` downloads the necessary native COG tiles with byte-range/length and source-ETag checks, bounded retries and a 512-tile/256 MiB tile-transfer limit. It publishes a sparse local TIFF for this window only and records header/tile hashes plus a subset digest. The digest is not a hash of the complete remote file. Unhonored ranges are rejected before reading a whole file. Source interruptions preserve the previous window and profile. Sparse TIFFs must not be used for other positions. The fetch helper supports sites poleward of 75° and radii up to 100 km.

`--radius-km`, `--step`, `--height-m`, `--min-distance-m` and `--output` control preprocessing. Heights default to an assumed 2 m. The CLI requires latitude and longitude together and safe site IDs. A failed build does not replace the previous profile. Remote COG reads may fail due to source/network interruptions; rerun or use a local verified source. Set an appropriate GDAL CA bundle when required by the environment.

## Accuracy and validation

Every runtime terrain profile exposes `accuracy.status: "unvalidated"`, `survey_grade: false`, unknown absolute horizontal/vertical/horizon error, and model limitations. Catalog coordinate precision is reported separately as a conditional rounding displacement, not a measured error. Visibility retains the existing model Boolean for compatibility and adds clearance and validation status. Timeline samples include the same terrain metadata; summary `sampling` explicitly states that continuous transition accuracy is unknown.

NAIF's [DE440 frame kernel](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/fk/moon_de440_220930.tf) closely aligns runtime `MOON_ME_DE440_ME421` with source DE421 `MOON_ME`: about 0.53 m over 2000–2040. This approximation, rounded catalog positions and assumed instrument height remain in the uncertainty budget.

Use the independent-control comparison tool after obtaining measured, matched reference features in the same frame/datum:

```sh
python -m backend.terrain.validate_accuracy references.json \
  --horizontal-tolerance-m 1 --vertical-tolerance-m 0.5 --output comparison.json
```

Those example tolerances are illustrative, not a project acceptance standard. Input JSON:

```json
{
  "source": "https://example.org/independent-lunar-control",
  "source_frame": "MOON_ME_DE421",
  "datum_radius_m": 1737400,
  "points": [
    {"feature_id": "control-1", "model_latitude": -85.123456,
     "model_longitude": 30.123456, "reference_latitude": -85.123457,
     "reference_longitude": 30.123458, "reference_elevation_m": 1234.5}
  ]
}
```

Provide at least three unique independently matched features; the one-record example shows the schema only. The tool samples the selected model's ground elevation and reports spherical horizontal residuals, vertical bias/RMSE/percentiles, maximum observed residuals and whether all supplied observations satisfy the chosen tolerances. Matching features and verifying reference independence remain external scientific responsibilities. An observed maximum is not an unsampled worst-case guarantee; passing comparisons never sets `survey_grade` to true.

NASA also publishes source uncertainty/effective-resolution layers and [selected 5 m polar datasets with uncertainty ensembles](https://pgda.gsfc.nasa.gov/products/78). These are useful for further validation, but source uncertainty is not independent backend accuracy and cannot certify all lunar locations. No independent control measurements or numerical acceptance contract are currently supplied. Software regression tests establish specific tested properties, not absence of every possible defect.
