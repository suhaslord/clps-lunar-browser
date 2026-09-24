"""Build a small horizon profile from a PGDA LOLA elevation GeoTIFF."""

import argparse
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.windows import Window, from_bounds

from backend.landing_sites import get_landing_site
from backend.terrain.horizon import PROFILE_DIR, validate_profile


PGDA_DEM = "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_80MPP_ADJ.TIF"


def build_profile(
    dem: str,
    site: dict,
    source_url: str,
    max_distance_m: float = 40000,
    azimuth_step: float = 0.5,
    observer_height_m: float = 2,
    min_distance_m: float = 160,
) -> dict:
    settings = (max_distance_m, azimuth_step, observer_height_m, min_distance_m)
    if not all(math.isfinite(value) for value in settings):
        raise ValueError("preprocessing settings must be finite")
    if not (max_distance_m > min_distance_m > 0 and observer_height_m >= 0):
        raise ValueError("invalid terrain distance or observer height")
    count = 360 / azimuth_step if azimuth_step > 0 else 0
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

        to_map = Transformer.from_crs(geographic, projected, always_xy=True)
        to_geo = Transformer.from_crs(projected, geographic, always_xy=True)
        x, y = to_map.transform(site["longitude"], site["latitude"])
        if not (
            dataset.bounds.left < x < dataset.bounds.right
            and dataset.bounds.bottom < y < dataset.bounds.top
        ):
            raise ValueError("site is outside the DEM")
        row, col = dataset.index(x, y)
        site_height = float(dataset.read(1, window=Window(col, row, 1, 1))[0, 0])
        if not math.isfinite(site_height):
            raise ValueError("site has no DEM elevation")

        # The projected scale at these latitudes stays within a few percent of ground distance.
        extent = max_distance_m * 1.1
        window = from_bounds(x - extent, y - extent, x + extent, y + extent, dataset.transform)
        window = window.round_offsets().round_lengths().intersection(
            Window(0, 0, dataset.width, dataset.height)
        )
        heights = dataset.read(1, window=window, masked=True)
        rows, cols = np.indices(heights.shape)
        transform = dataset.window_transform(window)
        xs = transform.c + (cols + 0.5) * transform.a + (rows + 0.5) * transform.b
        ys = transform.f + (cols + 0.5) * transform.d + (rows + 0.5) * transform.e
        longitudes, latitudes = to_geo.transform(xs, ys)

        lat0 = math.radians(site["latitude"])
        lon0 = math.radians(site["longitude"])
        lat = np.radians(latitudes)
        delta_lon = np.radians(longitudes) - lon0
        cos_arc = np.clip(
            np.sin(lat0) * np.sin(lat)
            + np.cos(lat0) * np.cos(lat) * np.cos(delta_lon),
            -1, 1,
        )
        ground_distance = lunar_radius * np.arccos(cos_arc)
        inside = (ground_distance >= min_distance_m) & (ground_distance <= max_distance_m)
        if not np.any(inside):
            raise ValueError("DEM has no terrain pixels in the requested radius")
        if np.any(inside & (np.ma.getmaskarray(heights) | ~np.isfinite(heights.data))):
            raise ValueError("DEM has missing pixels within the requested terrain radius")

        surface_radius = lunar_radius + np.asarray(heights)[inside]
        cos_lat = np.cos(lat[inside])
        delta = delta_lon[inside]
        east = surface_radius * cos_lat * np.sin(delta)
        north = surface_radius * (
            np.sin(lat[inside]) * np.cos(lat0)
            - cos_lat * np.sin(lat0) * np.cos(delta)
        )
        up = surface_radius * cos_arc[inside] - (lunar_radius + site_height + observer_height_m)
        azimuth = np.degrees(np.arctan2(east, north)) % 360
        angle = np.degrees(np.arctan2(up, np.hypot(east, north)))
        distances = ground_distance[inside]
        pixel_half_diagonal = math.hypot(*dataset.res) / 2
        half_width = np.degrees(np.arctan2(pixel_half_diagonal, distances))
        bins = np.floor(((azimuth + azimuth_step / 2) % 360) / azimuth_step).astype(int)
        horizon = np.full(int(count), -np.inf)

        # A cell spans an angle at the observer; count it in every bin it overlaps.
        max_offset = int(math.ceil(float(np.max(half_width)) / azimuth_step)) + 1
        contributions = []
        for offset in range(-max_offset, max_offset + 1):
            candidate = (bins + offset) % int(count)
            gap = np.abs((azimuth - candidate * azimuth_step + 180) % 360 - 180)
            covered = gap <= half_width + azimuth_step / 2
            if np.any(covered):
                np.maximum.at(horizon, candidate[covered], angle[covered])
                contributions.append((candidate[covered], angle[covered], distances[covered]))
        if not np.all(np.isfinite(horizon)):
            raise ValueError("DEM does not cover every azimuth bin")
        peak_distance = np.zeros(int(count))
        for candidate, elevations, ranges in contributions:
            winners = elevations == horizon[candidate]
            peak_distance[candidate[winners]] = ranges[winners]

        profile = {
            "site_id": site["id"],
            "latitude": site["latitude"],
            "longitude": site["longitude"],
            "source": source_url,
            "source_frame": "MOON_ME_DE421",
            "runtime_frame": "MOON_ME_DE440_ME421",
            "projection": dataset.crs.to_wkt(),
            "datum_radius_m": lunar_radius,
            "site_elevation_m": site_height,
            "pixel_resolution_m": abs(dataset.res[0]),
            "max_distance_m": max_distance_m,
            "min_distance_m": min_distance_m,
            "azimuth_step": azimuth_step,
            "observer_height_m": observer_height_m,
            "binning": "maximum cell angle over each overlapping azimuth bin",
            "horizon": [round(float(value), 4) for value in horizon],
            "peak_distance_m": [round(float(value), 1) for value in peak_distance],
        }
        return validate_profile(profile, site)


def main():
    parser = argparse.ArgumentParser(description="Make a LOLA horizon profile for a landing site")
    parser.add_argument("site_id")
    parser.add_argument("--dem", default="/vsicurl/" + PGDA_DEM)
    parser.add_argument("--source-url", default=PGDA_DEM)
    parser.add_argument("--radius-km", type=float, default=40)
    parser.add_argument("--step", type=float, default=0.5)
    parser.add_argument("--height-m", type=float, default=2)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    site = get_landing_site(args.site_id)
    profile = build_profile(
        args.dem, site, args.source_url, args.radius_km * 1000, args.step, args.height_m
    )
    output = args.output or PROFILE_DIR / f"{args.site_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
