"""Global LOLA horizons from NASA's uncompressed, 64-pixel/degree TIFF.

Only the surrounding cells are mapped into memory. Latitude is planetocentric,
longitude is east-positive, and the TIFF spans -180..180 with north at row zero.
"""
import math
import os
import copy
from functools import lru_cache
from pathlib import Path
from threading import RLock

import numpy as np
import tifffile

from backend.calculations.sun_earth import validate_coordinates
from backend.terrain.horizon import HorizonError, validate_profile

SOURCE = "https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/ldem_64_uint.tif"
RADIUS_M = 1737400.0
SHAPE = (11520, 23040)
LOCK = RLock()


def dem_path() -> Path:
    return Path(os.environ.get("LUNAR_DEM_PATH", Path(__file__).parent / "data" / "ldem_64_uint.tif")).expanduser().resolve()


@lru_cache(maxsize=2)
def _open_dem(path: str, size: int, modified: int, changed: int, inode: int) -> np.ndarray:
    from backend.setup_kernels import file_hash
    from backend.setup_terrain import DEM_SHA256
    try:
        grid = tifffile.memmap(path, mode="r")
        if grid.shape != SHAPE or grid.dtype != np.dtype("uint16"):
            raise HorizonError("Global DEM must be NASA ldem_64_uint.tif (11520 × 23040 uint16)")
        if file_hash(Path(path)) != DEM_SHA256:
            raise HorizonError("Global DEM checksum is incorrect; run python -m backend.setup_terrain")
        identity = Path(path).stat()
        if (identity.st_size, identity.st_mtime_ns, identity.st_ctime_ns, identity.st_ino) != (size, modified, changed, inode):
            raise HorizonError("Global DEM changed during verification; retry the request")
    except HorizonError:
        raise
    except (OSError, ValueError, tifffile.TiffFileError) as exc:
        raise HorizonError(f"Could not open global LOLA DEM: {exc}") from exc
    return grid


def global_dem() -> tuple[np.ndarray, tuple]:
    path = dem_path()
    try:
        stat = path.stat()
    except OSError as exc:
        raise HorizonError("Global terrain data is missing; run python -m backend.setup_terrain, or use terrain=false for a flat horizon") from exc
    key = (str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)
    return _open_dem(*key), key


def sample_height(grid: np.ndarray, latitude: float, longitude: float) -> float:
    """Bilinear height, with a longitude-independent estimate at each pole."""
    validate_coordinates(latitude, longitude)
    rows, cols = grid.shape
    y = np.clip((90 - latitude) * rows / 180 - 0.5, 0, rows - 1)
    x = ((longitude + 180) * cols / 360 - 0.5) % cols
    y0, x0 = int(math.floor(y)), int(math.floor(x))
    y1, x1 = min(y0 + 1, rows - 1), (x0 + 1) % cols
    fy, fx = y - y0, x - x0
    values = np.array([grid[y0, x0], grid[y0, x1], grid[y1, x0], grid[y1, x1]], dtype=float)
    # NASA's offset encoding leaves zero/65535 outside valid lunar elevations.
    weights = np.array([(1-fy)*(1-fx), (1-fy)*fx, fy*(1-fx), fy*fx])
    used = weights > 0
    if np.any((values[used] == 0) | (values[used] == 65535)) or not np.all(np.isfinite(values[used])):
        raise HorizonError("Global DEM has missing elevation at the observer")
    height = float(np.dot(values[used], weights[used]) * 0.5 - 10000)
    polar_fraction = (90 - abs(latitude)) * rows / 90
    if polar_fraction < 1:
        # The TIFF has a ring of cell centres near each pole, not a pole sample.
        # Use that ring's mean at the unique pole and blend to the first-row
        # interpolation at its latitude. This keeps the polar cap continuous.
        ring = np.asarray(grid[0 if latitude > 0 else -1], dtype=float)
        if np.any((ring == 0) | (ring == 65535)) or not np.all(np.isfinite(ring)):
            raise HorizonError("Global DEM has missing elevation in the polar cap")
        pole_height = float(ring.mean() * 0.5 - 10000)
        height = pole_height * (1 - polar_fraction) + height * polar_fraction
    return height


def build_global_profile(grid: np.ndarray, latitude: float, longitude: float,
                         max_distance_m: float = 40000, azimuth_step: float = 0.5,
                         observer_height_m: float = 2) -> dict:
    """Maximum cell angle per overlapping azimuth bin, including curvature."""
    validate_coordinates(latitude, longitude)
    count = 360 / azimuth_step if math.isfinite(azimuth_step) and azimuth_step > 0 else 0.0
    if not count.is_integer() or not 1 <= count <= 3600:
        raise ValueError("azimuth step must divide 360 degrees")
    if not math.isfinite(max_distance_m) or not 0 < max_distance_m < math.pi * RADIUS_M / 2:
        raise ValueError("invalid terrain range")
    if not math.isfinite(observer_height_m) or observer_height_m < 0:
        raise ValueError("invalid observer height")
    rows, cols = grid.shape
    if cols != 2 * rows:
        raise HorizonError("Global DEM must cover the full lunar globe at equal angular spacing")
    pixel_m = math.pi * RADIUS_M / rows
    min_distance = 2 * pixel_m
    if max_distance_m <= min_distance:
        raise HorizonError("Terrain range must exceed two DEM pixels")
    site_height = sample_height(grid, latitude, longitude)
    lat0, lon0 = math.radians(latitude), math.radians(longitude)
    arc_limit = max_distance_m / RADIUS_M
    delta_lat = math.degrees(arc_limit)
    first = max(0, int(math.floor((90 - min(90, latitude + delta_lat)) * rows / 180)))
    last = min(rows, int(math.ceil((90 - max(-90, latitude - delta_lat)) * rows / 180)))
    if abs(latitude) + delta_lat >= 90:
        col_indices = np.arange(cols)
    else:
        delta_lon = math.degrees(math.asin(math.sin(arc_limit) / math.cos(lat0)))
        left = math.floor((longitude - delta_lon + 180) * cols / 360)
        right = math.ceil((longitude + delta_lon + 180) * cols / 360)
        col_indices = np.arange(left, right) % cols
    delta = np.radians((col_indices + 0.5) * 360 / cols - 180) - lon0
    cos_delta, sin_delta = np.cos(delta), np.sin(delta)
    horizon = np.full(int(count), -np.inf)
    peak_distance = np.zeros(int(count))
    # Bound temporary arrays even for requests at either pole.
    stripe_rows = max(1, 100000 // len(col_indices))
    for row_start in range(first, last, stripe_rows):
        row_indices = np.arange(row_start, min(last, row_start + stripe_rows))
        lat = np.radians(90 - (row_indices + 0.5) * 180 / rows)[:, None]
        sin_lat, cos_lat = np.sin(lat), np.cos(lat)
        cos_arc = np.clip(math.sin(lat0) * sin_lat + math.cos(lat0) * cos_lat * cos_delta, -1, 1)
        distance = RADIUS_M * np.arccos(cos_arc)
        inside = (distance >= min_distance) & (distance <= max_distance_m)
        if not np.any(inside):
            continue
        raw = np.asarray(grid[np.ix_(row_indices, col_indices)], dtype=float)
        if np.any(inside & ((raw == 0) | (raw == 65535) | ~np.isfinite(raw))):
            raise HorizonError("Global DEM has missing pixels within the terrain range")
        surface_radius = RADIUS_M + (raw[inside] * 0.5 - 10000)
        east = surface_radius * np.broadcast_to(cos_lat * sin_delta, inside.shape)[inside]
        north = surface_radius * (math.cos(lat0) * sin_lat - math.sin(lat0) * cos_lat * cos_delta)[inside]
        up = surface_radius * cos_arc[inside] - (RADIUS_M + site_height + observer_height_m)
        angles = np.degrees(np.arctan2(up, np.hypot(east, north)))
        azimuth = np.degrees(np.arctan2(east, north)) % 360
        ranges = distance[inside]
        # Cylindrical pixels narrow east/west toward the poles.
        half_diagonal = pixel_m / 2 * np.sqrt(1 + np.broadcast_to(cos_lat, inside.shape)[inside] ** 2)
        half_width = np.degrees(np.arctan2(half_diagonal, ranges))
        bins = np.floor(((azimuth + azimuth_step / 2) % 360) / azimuth_step).astype(int)
        offsets = math.ceil(float(half_width.max()) / azimuth_step) + 1
        for offset in range(-offsets, offsets + 1):
            candidate = (bins + offset) % int(count)
            gap = np.abs((azimuth - candidate * azimuth_step + 180) % 360 - 180)
            covered = gap <= half_width + azimuth_step / 2
            c, a, d = candidate[covered], angles[covered], ranges[covered]
            if len(c):
                np.maximum.at(horizon, c, a)
                # Record a range belonging to the actual maximum; later stripes may replace it.
                winners = a == horizon[c]
                peak_distance[c[winners]] = d[winners]
    if not np.all(np.isfinite(horizon)):
        raise HorizonError("Global DEM does not cover every azimuth bin")
    return validate_profile({
        "site_id": "coordinates", "latitude": latitude, "longitude": longitude,
        "source": SOURCE, "source_frame": "MOON_ME_DE421", "runtime_frame": "MOON_ME_DE440_ME421",
        "projection": "global simple cylindrical, pixel centres, east-positive longitude",
        "observer_elevation_method": "bilinear with longitude-independent polar-cap interpolation",
        "datum_radius_m": RADIUS_M, "site_elevation_m": site_height,
        "pixel_resolution_m": pixel_m, "pixels_per_degree": rows / 180,
        "max_distance_m": max_distance_m, "min_distance_m": min_distance,
        "azimuth_step": azimuth_step, "observer_height_m": observer_height_m,
        "binning": "maximum cell angle over each overlapping azimuth bin",
        "horizon": np.round(horizon, 4).tolist(), "peak_distance_m": np.round(peak_distance, 3).tolist(),
    })


@lru_cache(maxsize=64)
def _cached_profile(key: tuple, latitude: float, longitude: float) -> dict:
    return build_global_profile(_open_dem(*key), latitude, longitude)


def coordinate_profile(latitude: float, longitude: float) -> dict:
    validate_coordinates(latitude, longitude)
    # Serialize cold generation so simultaneous polar requests cannot multiply memory use.
    with LOCK:
        _, key = global_dem()
        return copy.deepcopy(_cached_profile(key, latitude, longitude))
