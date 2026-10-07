"""Build bounded-memory lunar horizon profiles from projected elevation GeoTIFFs."""
import argparse
import json
import math
import re
import os
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.windows import Window, from_bounds

from backend.calculations.sun_earth import validate_coordinates
from backend.landing_sites import get_landing_site
from backend.terrain.global_dem import RADIUS_M
from backend.terrain.horizon import PROFILE_DIR, validate_profile

PGDA_DEM = "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_20MPP_ADJ.TIF"
PGDA_ODYSSEUS_DEM = "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_75S_30MPP_ADJ.TIF"


def write_profile(output: Path, profile: dict) -> None:
    """Publish a complete profile atomically; interrupted builds preserve the old one."""
    content = json.dumps(validate_profile(profile), indent=2, allow_nan=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         prefix=output.name + ".", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def sample_projected_height(dataset, x: float, y: float) -> float:
    """Bilinear pixel-centre interpolation; require only positive-weight cells."""
    inverse = ~dataset.transform
    col, row = inverse.a*x + inverse.b*y + inverse.c, inverse.d*x + inverse.e*y + inverse.f
    col, row = col - 0.5, row - 0.5
    c, r = math.floor(col), math.floor(row)
    fx, fy = col - c, row - r
    values = dataset.read(1, window=Window(c, r, 2, 2), masked=True, boundless=True)
    weights = np.array([[(1-fx)*(1-fy), fx*(1-fy)], [(1-fx)*fy, fx*fy]])
    used = weights > 0
    if np.any(np.ma.getmaskarray(values)[used]) or not np.all(np.isfinite(values.data[used])):
        raise ValueError("site has no DEM elevation")
    return float(np.sum(values.data[used] * weights[used]) / weights[used].sum())


def build_profile(
    dem: str, site: dict, source_url: str, max_distance_m: float = 40000,
    azimuth_step: float = 0.5, observer_height_m: float = 2,
    min_distance_m: float | None = None,
) -> dict:
    validate_coordinates(site["latitude"], site["longitude"])
    settings = (max_distance_m, azimuth_step, observer_height_m)
    if not all(math.isfinite(value) for value in settings):
        raise ValueError("preprocessing settings must be finite")
    if not (0 < max_distance_m < math.pi * RADIUS_M / 2 and observer_height_m >= 0):
        raise ValueError("invalid terrain distance or observer height")
    count = 360 / azimuth_step if azimuth_step > 0 else 0.0
    if not (count.is_integer() and 1 <= count <= 3600):
        raise ValueError("azimuth step must divide 360 degrees")

    with rasterio.open(dem) as dataset:
        if dataset.count != 1 or dataset.crs is None:
            raise ValueError("DEM needs one elevation band and a projected lunar CRS")
        projected = CRS.from_wkt(dataset.crs.to_wkt())
        geographic = projected.geodetic_crs
        if not projected.is_projected or geographic is None:
            raise ValueError("DEM needs a projected lunar CRS")
        operation = projected.coordinate_operation
        if operation is None or "Polar Stereographic" not in operation.method_name:
            raise ValueError("DEM must use polar stereographic coordinates")
        lunar_radius = geographic.ellipsoid.semi_major_metre
        if abs(lunar_radius - geographic.ellipsoid.semi_minor_metre) > 0.01:
            raise ValueError("DEM datum must be spherical")
        if abs(lunar_radius - RADIUS_M) > 0.01:
            raise ValueError("DEM datum must use the 1737400 m lunar reference radius")
        if len(projected.axis_info) < 2 or any(
            abs(axis.unit_conversion_factor - 1) > 1e-12 for axis in projected.axis_info[:2]
        ):
            raise ValueError("DEM projected coordinates must use metres")
        if dataset.transform.b or dataset.transform.d or dataset.transform.a <= 0 or dataset.transform.e >= 0:
            raise ValueError("DEM must use a north-up pixel grid")
        pixel_half_diagonal = math.hypot(*dataset.res) / 2
        minimum = pixel_half_diagonal if min_distance_m is None else min_distance_m
        if not math.isfinite(minimum) or not 0 < minimum < max_distance_m:
            raise ValueError("invalid terrain distance or observer height")
        to_map = Transformer.from_crs(geographic, projected, always_xy=True)
        to_geo = Transformer.from_crs(projected, geographic, always_xy=True)
        x, y = to_map.transform(site["longitude"], site["latitude"])
        if not (dataset.bounds.left < x < dataset.bounds.right and dataset.bounds.bottom < y < dataset.bounds.top):
            raise ValueError("site is outside the DEM")
        site_height = sample_projected_height(dataset, x, y)

        # Bound projection scale using the largest colatitude in the requested
        # circle, rather than assuming a fixed 10% margin for all polar sites.
        pole_latitude = next((p.value for p in operation.params if p.name in
                              ("Latitude of natural origin", "Latitude of standard parallel")), None)
        if pole_latitude is None or abs(abs(pole_latitude) - 90) > 1e-8:
            raise ValueError("DEM must use polar stereographic coordinates with true scale at the pole")
        scale_factor = next((p.value for p in operation.params if p.name == "Scale factor at natural origin"), 1)
        if abs(scale_factor - 1) > 1e-12:
            raise ValueError("DEM must use polar stereographic coordinates with true scale at the pole")
        # Both hemispheres are permitted only where the projection remains local.
        colatitude = math.radians(90 - (site["latitude"] if pole_latitude > 0 else -site["latitude"]))
        far_colatitude = colatitude + max_distance_m / lunar_radius
        if far_colatitude >= math.pi / 2:
            raise ValueError("site/radius is too far from the DEM projection pole")
        scale_bound = 2 / (1 + math.cos(far_colatitude))
        extent = max_distance_m * scale_bound + 2 * pixel_half_diagonal
        raw_window = from_bounds(x - extent, y - extent, x + extent, y + extent, dataset.transform)
        first_col, first_row = math.floor(raw_window.col_off), math.floor(raw_window.row_off)
        last_col = math.ceil(raw_window.col_off + raw_window.width)
        last_row = math.ceil(raw_window.row_off + raw_window.height)
        if first_col < 0 or first_row < 0 or last_col > dataset.width or last_row > dataset.height:
            raise ValueError("DEM does not cover the full terrain window; reduce the radius or use a larger DEM")
        width = last_col - first_col
        stripe_rows = max(1, 250000 // width)
        horizon = np.full(int(count), -np.inf)
        peak_distance = np.zeros(int(count))
        lat0, lon0 = math.radians(site["latitude"]), math.radians(site["longitude"])
        saw_terrain = False
        for start in range(first_row, last_row, stripe_rows):
            window = Window(first_col, start, width, min(stripe_rows, last_row - start))
            heights = dataset.read(1, window=window, masked=True)
            rows, cols = np.indices(heights.shape)
            transform = dataset.window_transform(window)
            xs = transform.c + (cols + 0.5) * transform.a
            ys = transform.f + (rows + 0.5) * transform.e
            longitudes, latitudes = to_geo.transform(xs, ys)
            lat = np.radians(latitudes)
            delta_lon = np.radians(longitudes) - lon0
            cos_arc = np.clip(np.sin(lat0)*np.sin(lat) + np.cos(lat0)*np.cos(lat)*np.cos(delta_lon), -1, 1)
            ground_distance = lunar_radius * np.arccos(cos_arc)
            inside = (ground_distance >= minimum) & (ground_distance <= max_distance_m)
            if not np.any(inside):
                continue
            saw_terrain = True
            if np.any(inside & (np.ma.getmaskarray(heights) | ~np.isfinite(heights.data))):
                raise ValueError("DEM has missing pixels within the requested terrain radius")
            surface_radius = lunar_radius + heights.data[inside]
            cos_lat, delta = np.cos(lat[inside]), delta_lon[inside]
            east = surface_radius * cos_lat * np.sin(delta)
            north = surface_radius * (np.sin(lat[inside])*np.cos(lat0) - cos_lat*np.sin(lat0)*np.cos(delta))
            up = surface_radius*cos_arc[inside] - (lunar_radius + site_height + observer_height_m)
            azimuth = np.degrees(np.arctan2(east, north)) % 360
            angle = np.degrees(np.arctan2(up, np.hypot(east, north)))
            distances = ground_distance[inside]
            half_width = np.degrees(np.arctan2(pixel_half_diagonal, distances))
            bins = np.floor(((azimuth + azimuth_step/2) % 360) / azimuth_step).astype(int)
            max_offset = int(math.ceil(float(np.max(half_width)) / azimuth_step)) + 1
            for offset in range(-max_offset, max_offset + 1):
                candidate = (bins + offset) % int(count)
                gap = np.abs((azimuth - candidate*azimuth_step + 180) % 360 - 180)
                covered = gap <= half_width + azimuth_step/2
                c, a, d = candidate[covered], angle[covered], distances[covered]
                if len(c):
                    np.maximum.at(horizon, c, a)
                    winners = a == horizon[c]
                    peak_distance[c[winners]] = d[winners]
        if not saw_terrain:
            raise ValueError("DEM has no terrain pixels in the requested radius")
        if not np.all(np.isfinite(horizon)):
            raise ValueError("DEM does not cover every azimuth bin")
        return validate_profile({
            "site_id": site["id"], "latitude": site["latitude"], "longitude": site["longitude"],
            "source": source_url, "source_frame": "MOON_ME_DE421", "runtime_frame": "MOON_ME_DE440_ME421",
            "projection": dataset.crs.to_wkt(), "datum_radius_m": lunar_radius,
            "site_elevation_m": site_height, "observer_elevation_method": "bilinear pixel-centre interpolation",
            "pixel_resolution_m": abs(dataset.res[0]), "max_distance_m": max_distance_m,
            "min_distance_m": minimum, "azimuth_step": azimuth_step, "observer_height_m": observer_height_m,
            "binning": "maximum cell angle over each overlapping azimuth bin",
            "horizon": [round(float(value), 4) for value in horizon],
            "peak_distance_m": [round(float(value), 3) for value in peak_distance],
        }, site)


def main():
    parser = argparse.ArgumentParser(description="Make a lunar horizon profile for a site or precise coordinates")
    parser.add_argument("site_id")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--dem")
    parser.add_argument("--source-url")
    parser.add_argument("--fetch-window", type=Path, help="download byte-checked COG tiles to a sparse local TIFF")
    parser.add_argument("--radius-km", type=float, default=40)
    parser.add_argument("--step", type=float, default=0.5)
    parser.add_argument("--height-m", type=float, default=2)
    parser.add_argument("--min-distance-m", type=float)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.dem and not args.source_url:
        parser.error("--source-url is required with --dem to preserve source provenance")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.site_id):
        parser.error("site ID must contain only letters, numbers, underscores or hyphens")
    if (args.lat is None) != (args.lon is None):
        parser.error("--lat and --lon must be provided together")
    site = get_landing_site(args.site_id) if args.lat is None else {
        "id": args.site_id, "latitude": args.lat, "longitude": args.lon}
    source = args.source_url or (PGDA_ODYSSEUS_DEM if args.site_id == "odysseus-im1" else PGDA_DEM)
    dem = args.dem or "/vsicurl/" + source
    if args.dem and args.fetch_window:
        parser.error("--dem and --fetch-window are mutually exclusive")
    provenance = None
    if args.fetch_window:
        from backend.terrain.fetch_window import fetch_window
        provenance = fetch_window(source, site["latitude"], site["longitude"], args.radius_km*1000, args.fetch_window)
        dem = str(args.fetch_window)
    profile = build_profile(dem, site, source, args.radius_km*1000, args.step,
                            args.height_m, args.min_distance_m)
    if provenance is not None:
        profile["source_subset"] = provenance
    filename = site['id'] if args.lat is None else f"coordinate-{site['id']}"
    output = args.output or PROFILE_DIR / f"{filename}.json"
    write_profile(output, profile)
    print(f"Wrote {output} ({len(profile['horizon'])} azimuth bins)")


if __name__ == "__main__":
    main()
