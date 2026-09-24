# SPICE kernels

Download these NAIF kernels into this folder. The `.bsp` and `.bpc` files are binary data and should not be committed.

- [`naif0012.tls`](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls) — leap seconds for UTC to ephemeris time conversion
- [`de440s.bsp`](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp) — Sun, Earth, and Moon positions
- [`pck00011.tpc`](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/pck00011.tpc) — lunar radii and other body constants
- [`moon_pa_de440_200625.bpc`](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/moon_pa_de440_200625.bpc) — high accuracy lunar orientation
- [`moon_de440_220930.tf`](https://naif.jpl.nasa.gov/pub/naif/pds/pds4/clps/clps_spice/spice_kernels/fk/moon_de440_220930.tf) — lunar `MOON_ME` frame definitions

The backend loads these files on the first visibility request. By default, it looks here. To use another folder, set `SPICE_KERNELS_DIR` to its path.

Start the API from the repository root with:

```sh
uvicorn backend.app:app --reload
```
