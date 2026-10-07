import json
import math
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
    if not all(math.isfinite(value) for value in (latitude, longitude, height, radius, distance)):
        raise HorizonError("horizon profile contains non-finite metadata")
    if not (
        -90 <= latitude <= 90
        and -180 <= longitude <= 180
        and height >= 0
        and radius > 0
        and distance > 0
    ):
        raise HorizonError("horizon profile contains invalid coordinates or distances")
    if profile.get("source_frame") != "MOON_ME_DE421":
        raise HorizonError("horizon profile has an unsupported lunar frame")
    if not isinstance(profile.get("source"), str) or not profile["source"].startswith("https://"):
        raise HorizonError("horizon profile needs a source URL")
    if not isinstance(profile.get("site_id"), str) or not profile["site_id"]:
        raise HorizonError("horizon profile needs a site ID")
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
    except (OSError, json.JSONDecodeError) as exc:
        raise HorizonError(f"could not read horizon profile {path.name}: {exc}") from exc


def load_profile(site: dict, directory: Path = PROFILE_DIR) -> dict | None:
    path = directory / f"{site['id']}.json"
    if not path.is_file():
        return None
    try:
        stat = path.stat()
    except OSError as exc:
        raise HorizonError(f"could not read horizon profile {path.name}: {exc}") from exc
    return validate_profile(_read_profile(path, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns), site)


def horizon_at(profile: dict, azimuth: float) -> float:
    angles = profile["horizon"]
    position = (azimuth % 360) / profile["azimuth_step"]
    left = int(math.floor(position))
    fraction = position - left
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
    return result
