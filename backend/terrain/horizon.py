import json
import math
import copy
import stat
import re
from functools import lru_cache
from pathlib import Path


PROFILE_DIR = Path(__file__).resolve().parent / "profiles"


class HorizonError(ValueError):
    pass


def _finite_number(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_profile(profile: dict, site: dict | None = None) -> dict:
    if not isinstance(profile, dict):
        raise HorizonError("horizon profile must be an object")
    try:
        # Downstream geometry uses these original values, so strings and
        # booleans must not pass validation through float coercion.
        for key in ("azimuth_step", "latitude", "longitude", "observer_height_m",
                    "datum_radius_m", "max_distance_m"):
            if not _finite_number(profile[key]):
                raise HorizonError("horizon profile is missing valid numeric metadata")
        step = float(profile["azimuth_step"])
        angles = profile["horizon"]
        latitude = float(profile["latitude"])
        longitude = float(profile["longitude"])
        height = float(profile["observer_height_m"])
        radius = float(profile["datum_radius_m"])
        distance = float(profile["max_distance_m"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise HorizonError("horizon profile is missing valid metadata") from exc

    count = 360 / step if math.isfinite(step) and step > 0 else 0.0
    if not (count.is_integer() and 1 <= count <= 3600):
        raise HorizonError("azimuth step must divide 360 degrees")
    if not isinstance(angles, list) or len(angles) != int(count):
        raise HorizonError("horizon profile has the wrong number of bins")
    if any(
        not _finite_number(angle)
        or not -90 <= angle <= 90
        for angle in angles
    ):
        raise HorizonError("horizon profile contains an invalid angle")
    elevation = profile.get("site_elevation_m")
    if "site_elevation_m" in profile and (
        not _finite_number(elevation)
        or not _finite_number(radius + elevation + height)
        or radius + elevation + height <= 0
    ):
        raise HorizonError("horizon profile has an invalid site elevation")
    peak_distances = profile.get("peak_distance_m")
    if peak_distances is not None and (
        not isinstance(peak_distances, list)
        or len(peak_distances) != int(count)
        or any(
            not _finite_number(value)
            or value <= 0
            or value > distance
            for value in peak_distances
        )
    ):
        raise HorizonError("horizon profile contains an invalid peak distance")
    minimum = profile.get("min_distance_m")
    if minimum is not None and (
        not _finite_number(minimum) or not 0 < minimum < distance
    ):
        raise HorizonError("horizon profile has an invalid minimum terrain distance")
    resolution = profile.get("pixel_resolution_m")
    if resolution is not None and (not _finite_number(resolution) or resolution <= 0):
        raise HorizonError("horizon profile has an invalid pixel resolution")
    if not all(math.isfinite(value) for value in (latitude, longitude, height, radius, distance)):
        raise HorizonError("horizon profile contains non-finite metadata")
    if not (
        -90 <= latitude <= 90
        and -180 <= longitude <= 180
        and height >= 0
        and radius > 0
        and 0 < distance < math.pi * radius / 2
    ):
        raise HorizonError("horizon profile contains invalid coordinates or distances")
    if abs(radius - 1737400) > 0.01:
        raise HorizonError("horizon profile must use the 1737400 m lunar datum")
    if profile.get("source_frame") != "MOON_ME_DE421":
        raise HorizonError("horizon profile has an unsupported lunar frame")
    if not isinstance(profile.get("source"), str) or not profile["source"].startswith("https://"):
        raise HorizonError("horizon profile needs a source URL")
    if not isinstance(profile.get("site_id"), str) or not profile["site_id"]:
        raise HorizonError("horizon profile needs a site ID")
    if "source_subset" in profile:
        subset = profile["source_subset"]
        if (not isinstance(subset, dict)
                or not isinstance(subset.get("source_etag"), str) or not subset["source_etag"]
                or not isinstance(subset.get("coverage"), str) or not subset["coverage"]
                or not isinstance(subset.get("retrieved_subset_sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", subset["retrieved_subset_sha256"]) is None):
            raise HorizonError("horizon profile has invalid source subset provenance")
    if site and (
        profile["site_id"] != site["id"]
        or abs(latitude - site["latitude"]) > 1e-8
        or abs(longitude - site["longitude"]) > 1e-8
    ):
        raise HorizonError("horizon profile does not match the landing site")
    return profile


@lru_cache(maxsize=16)
def _read_profile(path: Path, size: int, modified: int, changed: int) -> dict:
    try:
        with path.open(encoding="utf-8") as file:
            return validate_profile(json.load(file))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HorizonError(f"could not read horizon profile {path.name}: {exc}") from exc


def load_profile(site: dict, directory: Path | None = None) -> dict | None:
    directory = PROFILE_DIR if directory is None else directory
    path = directory / f"{site['id']}.json"
    try:
        identity = path.stat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise HorizonError(f"could not read horizon profile {path.name}: {exc}") from exc
    if not stat.S_ISREG(identity.st_mode):
        raise HorizonError(f"horizon profile {path.name} is not a regular file")
    profile = _read_profile(path, identity.st_size, identity.st_mtime_ns, identity.st_ctime_ns)
    return copy.deepcopy(validate_profile(profile, site))


def load_coordinate_profile(latitude: float, longitude: float, directory: Path | None = None) -> dict | None:
    directory = PROFILE_DIR if directory is None else directory
    matches = []
    try:
        paths = sorted(directory.glob("coordinate-*.json"))
        for path in paths:
            identity = path.stat()
            if not stat.S_ISREG(identity.st_mode):
                raise HorizonError(f"horizon profile {path.name} is not a regular file")
            profile = _read_profile(path, identity.st_size, identity.st_mtime_ns, identity.st_ctime_ns)
            # Exact coordinates: nearby positions must not inherit another observer's skyline.
            if profile["latitude"] == latitude and profile["longitude"] == longitude:
                matches.append(profile)
    except OSError as exc:
        raise HorizonError(f"could not read coordinate profiles: {exc}") from exc
    if len(matches) > 1:
        raise HorizonError("multiple detailed profiles match these coordinates")
    return copy.deepcopy(matches[0]) if matches else None


def horizon_at(profile: dict, azimuth: float) -> float:
    angles = profile["horizon"]
    position = (azimuth % 360) / profile["azimuth_step"]
    index = int(math.floor(position))
    fraction = position - index
    left = index % len(angles)
    return angles[left] * (1 - fraction) + angles[(left + 1) % len(angles)] * fraction


def apply_horizon(result: dict, profile: dict | None) -> dict:
    if profile is None:
        return result
    for name in ("sun", "earth"):
        body = result[name]
        boundary = horizon_at(profile, body["azimuth"])
        body["flat_visible"] = body["elevation"] > 0
        body["terrain_horizon"] = boundary
        body["visible"] = body["elevation"] > boundary
        body["terrain_clearance_deg"] = body["elevation"] - boundary
        body["visibility_validation"] = "unvalidated"
        ceiling = profile.get("distant_terrain_ceiling_deg")
        if ceiling is not None:
            body["distant_raster_may_block"] = body["elevation"] <= ceiling
    return result
