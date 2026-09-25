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


def make_dem(path, ridges=(), missing=False):
    crs = CRS.from_proj4(
        "+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +R=1737400 +units=m"
    )
    to_map = Transformer.from_crs(crs.geodetic_crs, crs, always_xy=True)
    x, y = to_map.transform(SITE["longitude"], SITE["latitude"])
    grid = np.zeros((201, 201), dtype="float32")
    transform = from_origin(x - 10050, y + 10050, 100, 100)

    for bearing, distance, height in ridges:
        lat0 = math.radians(SITE["latitude"])
        lon0 = math.radians(SITE["longitude"])
        az = math.radians(bearing)
        arc = distance / 1737400
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
