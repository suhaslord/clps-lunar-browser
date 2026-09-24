import json
import math
from functools import lru_cache
from pathlib import Path


PROFILE_DIR = Path(__file__).resolve().parent / "profiles"


class HorizonError(ValueError):
    pass


def validate_profile(profile: dict, site: dict | None = None) -> dict:
    if not isinstance(profile, dict):
        raise HorizonError("horizon profile must be an object")
    try:
        step = float(profile["azimuth_step"])
        angles = profile["horizon"]
        latitude = float(profile["latitude"])
        longitude = float(profile["longitude"])
        height = float(profile["observer_height_m"])
        radius = float(profile["datum_radius_m"])
        distance = float(profile["max_distance_m"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HorizonError("horizon profile is missing valid metadata") from exc

    count = 360 / step if math.isfinite(step) and step > 0 else 0
    if not (count.is_integer() and 1 <= count <= 3600):
        raise HorizonError("azimuth step must divide 360 degrees")
    if not isinstance(angles, list) or len(angles) != int(count):
        raise HorizonError("horizon profile has the wrong number of bins")
    if any(
        isinstance(angle, bool)
        or not isinstance(angle, (int, float))
        or not math.isfinite(angle)
        or not -90 <= angle <= 90
        for angle in angles
    ):
        raise HorizonError("horizon profile contains an invalid angle")
    peak_distances = profile.get("peak_distance_m")
    if peak_distances is not None and (
        not isinstance(peak_distances, list)
        or len(peak_distances) != int(count)
        or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
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
def _read_profile(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as file:
            return validate_profile(json.load(file))
    except (OSError, json.JSONDecodeError) as exc:
        raise HorizonError(f"could not read horizon profile {path.name}: {exc}") from exc


def load_profile(site: dict, directory: Path = PROFILE_DIR) -> dict | None:
    path = directory / f"{site['id']}.json"
    if not path.is_file():
        return None
    return validate_profile(_read_profile(path), site)


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
