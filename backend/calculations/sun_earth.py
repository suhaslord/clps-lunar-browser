from datetime import datetime, timezone
import math

import numpy as np
import spiceypy
from spiceypy.utils.exceptions import SpiceyError

from backend.spice_kernels import SPICE_LOCK, load_spice_kernels


MOON_FRAME = "MOON_ME"


class SpiceCalculationError(RuntimeError):
    pass


def validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("lat must be between -90 and 90 degrees")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("lon must be between -180 and 180 degrees")
    return latitude, longitude


def parse_utc_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("time must be an ISO 8601 timestamp with a timezone") from exc

    if parsed.tzinfo is None:
        raise ValueError("time must include a timezone, for example 2026-10-03T18:00:00Z")
    return parsed.astimezone(timezone.utc)


def _local_angles(vector: np.ndarray, latitude: float, longitude: float) -> tuple[float, float]:
    distance = float(np.linalg.norm(vector))
    if not math.isfinite(distance) or distance == 0:
        raise SpiceCalculationError("SPICE returned an invalid position vector")

    lat = math.radians(latitude)
    lon = math.radians(longitude)
    direction = vector / distance

    # Azimuth is measured clockwise from north in the local east/north/up basis.
    east = np.array([-math.sin(lon), math.cos(lon), 0.0])
    north = np.array(
        [-math.sin(lat) * math.cos(lon), -math.sin(lat) * math.sin(lon), math.cos(lat)]
    )
    up = np.array(
        [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]
    )

    elevation = math.degrees(math.asin(float(np.clip(np.dot(direction, up), -1.0, 1.0))))
    azimuth = math.degrees(
        math.atan2(float(np.dot(direction, east)), float(np.dot(direction, north)))
    ) % 360
    return azimuth, elevation


def calculate_visibility(latitude: float, longitude: float, utc_time: str) -> dict:
    latitude, longitude = validate_coordinates(latitude, longitude)
    time = parse_utc_time(utc_time)
    output_time = time.isoformat().replace("+00:00", "Z")

    with SPICE_LOCK:
        load_spice_kernels()
        try:
            et = spiceypy.utc2et(output_time)
            _, radii = spiceypy.bodvrd("MOON", "RADII", 3)
            equatorial_radius = float(radii[0])
            flattening = (equatorial_radius - float(radii[2])) / equatorial_radius
            site_fixed = spiceypy.georec(
                math.radians(longitude), math.radians(latitude), 0.0, equatorial_radius, flattening
            )

            # SPICE rotates the surface point between the lunar fixed frame and inertial J2000.
            fixed_to_j2000 = spiceypy.pxform(MOON_FRAME, "J2000", et)
            j2000_to_fixed = spiceypy.pxform("J2000", MOON_FRAME, et)
            site_j2000 = fixed_to_j2000 @ site_fixed

            bodies = {}
            for name, target in (("sun", "SUN"), ("earth", "EARTH")):
                moon_to_body, _ = spiceypy.spkpos(target, et, "J2000", "NONE", "MOON")
                body_from_site_fixed = j2000_to_fixed @ (moon_to_body - site_j2000)
                azimuth, elevation = _local_angles(body_from_site_fixed, latitude, longitude)
                bodies[name] = {
                    "azimuth": round(azimuth, 4),
                    "elevation": round(elevation, 4),
                    "visible": elevation > 0,
                }
        except SpiceyError as exc:
            raise SpiceCalculationError(f"SPICE could not calculate the Sun/Earth position: {exc}") from exc

    return {
        "site": None,
        "latitude": latitude,
        "longitude": longitude,
        "time": output_time,
        "sun": bodies["sun"],
        "earth": bodies["earth"],
    }
