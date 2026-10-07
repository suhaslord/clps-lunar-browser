import json
import math

import numpy as np
import pytest
import rasterio
from pyproj import CRS, Transformer
from rasterio.transform import from_origin

from backend.terrain.horizon import (
    HorizonError,
    apply_horizon,
    horizon_at,
    load_profile,
    validate_profile,
)
from backend.terrain.preprocess import build_profile


SITE = {"id": "test-site", "latitude": -84.79, "longitude": 29.2}
SOURCE = "https://pgda.gsfc.nasa.gov/products/90"


def make_dem(path, ridges=(), missing=False, radius=1737400, units="m"):
    crs = CRS.from_proj4(
        f"+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +R={radius} +units={units}"
    )
    to_map = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True)
    x, y = to_map.transform(SITE["longitude"], SITE["latitude"])
    grid = np.zeros((201, 201), dtype="float32")
    transform = from_origin(x - 10050, y + 10050, 100, 100)

    for bearing, distance, height in ridges:
        lat0 = math.radians(SITE["latitude"])
        lon0 = math.radians(SITE["longitude"])
        az = math.radians(bearing)
        arc = distance / radius
        lat = math.asin(math.sin(lat0) * math.cos(arc) + math.cos(lat0) * math.sin(arc) * math.cos(az))
        lon = lon0 + math.atan2(math.sin(az) * math.sin(arc) * math.cos(lat0), math.cos(arc) - math.sin(lat0) * math.sin(lat))
        rx, ry = to_map.transform(math.degrees(lon), math.degrees(lat))
        row, col = rasterio.transform.rowcol(transform, rx, ry)
        grid[row, col] = height
    if missing:
        grid[100, 110] = np.nan
    with rasterio.open(
        path, "w", driver="GTiff", height=201, width=201,
        count=1, dtype="float32", crs=crs.to_wkt(), transform=transform, nodata=np.nan,
    ) as dataset:
        dataset.write(grid, 1)


def profile_from_dem(tmp_path, ridges=(), height=0):
    dem = tmp_path / "synthetic.tif"
    make_dem(dem, ridges)
    return build_profile(str(dem), SITE, SOURCE, 2500, 10, height, 150)


def test_flat_spherical_terrain_and_hill_direction(tmp_path):
    flat = profile_from_dem(tmp_path)
    ridge = profile_from_dem(tmp_path, [(90, 1000, 200)])

    assert max(flat["horizon"]) < 0.02
    assert min(flat["horizon"]) > -0.1
    assert horizon_at(ridge, 90) > 5
    assert horizon_at(ridge, 270) == pytest.approx(horizon_at(flat, 270), abs=0.001)
    assert ridge["datum_radius_m"] == 1737400


def test_nearby_peak_wins_and_height_lowers_horizon(tmp_path):
    ridges = [(90, 1000, 100), (90, 1200, 300)]
    ground = profile_from_dem(tmp_path, ridges, height=0)
    raised = profile_from_dem(tmp_path, ridges, height=20)

    assert horizon_at(ground, 90) > 10
    assert horizon_at(raised, 90) < horizon_at(ground, 90)
    assert ground["observer_height_m"] == 0
    assert raised["observer_height_m"] == 20


def test_missing_terrain_is_rejected(tmp_path):
    dem = tmp_path / "gap.tif"
    make_dem(dem, missing=True)
    with pytest.raises(ValueError, match="missing pixels"):
        build_profile(str(dem), SITE, SOURCE, 2500, 10)


def test_horizon_wraparound_and_visibility():
    profile = {
        "site_id": "test-site", "latitude": -84.79, "longitude": 29.2,
        "source": SOURCE, "source_frame": "MOON_ME_DE421",
        "datum_radius_m": 1737400, "max_distance_m": 2500,
        "azimuth_step": 90, "observer_height_m": 2,
        "horizon": [2, 0, 0, 4],
    }
    validate_profile(profile, SITE)
    assert horizon_at(profile, 359.9) == pytest.approx(2.00222, abs=0.0001)
    assert horizon_at(profile, 0.1) == pytest.approx(1.99778, abs=0.0001)

    result = {
        "sun": {"azimuth": 0, "elevation": 1, "visible": True},
        "earth": {"azimuth": 180, "elevation": 1, "visible": True},
    }
    apply_horizon(result, profile)
    assert result["sun"] == {
        "azimuth": 0, "elevation": 1, "flat_visible": True,
        "terrain_horizon": 2, "visible": False,
    }
    assert result["earth"]["visible"] is True
    assert apply_horizon({"sun": {}, "earth": {}}, None) == {"sun": {}, "earth": {}}


def test_profile_loader_rejects_mismatch_and_bad_data(tmp_path):
    profile = profile_from_dem(tmp_path)
    path = tmp_path / "test-site.json"
    path.write_text(json.dumps(profile))
    assert load_profile(SITE, tmp_path)["horizon"] == profile["horizon"]
    with pytest.raises(HorizonError, match="does not match"):
        load_profile({**SITE, "latitude": -84.8}, tmp_path)
    profile["horizon"][0] = None
    path2 = tmp_path / "bad.json"
    path2.write_text(json.dumps({**profile, "site_id": "bad"}))
    with pytest.raises(HorizonError, match="invalid angle"):
        load_profile({**SITE, "id": "bad"}, tmp_path)


def test_finite_nodata_at_observer_is_rejected(tmp_path):
    dem = tmp_path / "nodata-observer.tif"
    make_dem(dem)
    with rasterio.open(dem, "r+") as dataset:
        grid = dataset.read(1)
        grid[100, 100] = -9999
        dataset.nodata = -9999
        dataset.write(grid, 1)
    with pytest.raises(ValueError, match="site has no DEM elevation"):
        build_profile(str(dem), SITE, SOURCE, 2500, 10, 0, 150)


def test_dem_edge_does_not_silently_truncate_declared_terrain_range(tmp_path):
    dem = tmp_path / "partial-radius.tif"
    make_dem(dem)
    # Every bearing has nearby cells, but the 12 km circle extends beyond
    # this DEM's approximately 10 km half-width.
    with pytest.raises(ValueError, match="full terrain window"):
        build_profile(str(dem), SITE, SOURCE, 12000, 10, 0, 150)


def test_profile_cache_reloads_replaced_file_and_rejects_corruption(tmp_path):
    profile = profile_from_dem(tmp_path)
    path = tmp_path / "test-site.json"
    path.write_text(json.dumps(profile))
    assert load_profile(SITE, tmp_path)["horizon"] == profile["horizon"]
    updated = {**profile, "horizon": [20] * 36, "source": SOURCE + "?revision=2"}
    replacement = tmp_path / "replacement.json"
    replacement.write_text(json.dumps(updated))
    replacement.replace(path)
    assert load_profile(SITE, tmp_path)["horizon"] == [20] * 36
    path.write_text("{broken JSON")
    with pytest.raises(HorizonError, match="could not read"):
        load_profile(SITE, tmp_path)


@pytest.mark.parametrize("field", [
    "azimuth_step", "latitude", "longitude", "observer_height_m",
    "datum_radius_m", "max_distance_m",
])
@pytest.mark.parametrize("invalid", ["2", True, 10 ** 1000], ids=["string", "bool", "oversized-integer"])
def test_profile_metadata_must_be_usable_numeric_values(tmp_path, field, invalid):
    profile = profile_from_dem(tmp_path)
    profile[field] = invalid
    with pytest.raises(HorizonError):
        validate_profile(profile)


@pytest.mark.parametrize("field", ["horizon", "site_elevation_m", "peak_distance_m"])
def test_profile_rejects_oversized_optional_numbers(tmp_path, field):
    profile = profile_from_dem(tmp_path)
    if field == "site_elevation_m":
        profile[field] = 10 ** 1000
    else:
        profile[field][0] = 10 ** 1000
    with pytest.raises(HorizonError):
        validate_profile(profile)


def test_profile_rejects_overflowing_observer_radius(tmp_path):
    profile = {**profile_from_dem(tmp_path), "datum_radius_m": 1e308, "site_elevation_m": 1e308}
    with pytest.raises(HorizonError, match="invalid site elevation"):
        validate_profile(profile)


@pytest.mark.parametrize("radius,units,message", [
    (6371000, "m", "lunar reference radius"),
    (1737400, "ft", "metres"),
])
def test_preprocessing_does_not_mislabel_other_datums_or_units(tmp_path, radius, units, message):
    dem = tmp_path/"wrong-coordinate-system.tif"
    make_dem(dem, radius=radius, units=units)
    with pytest.raises(ValueError, match=message):
        build_profile(str(dem), SITE, SOURCE, 2500, 10, 0, 150)
