"""Select checked-in detailed profiles, otherwise use the global LOLA DEM."""
from backend.calculations.sun_earth import validate_coordinates
from backend.landing_sites import load_landing_sites
from backend.terrain.global_dem import coordinate_profile
from backend.terrain.horizon import HorizonError, load_profile


def terrain_profile(latitude: float, longitude: float, site: dict | None = None) -> dict:
    validate_coordinates(latitude, longitude)
    if site is None:
        site = next((item for item in load_landing_sites()
                     if item["latitude"] == latitude and item["longitude"] == longitude), None)
    if site:
        detailed = load_profile(site)
        if detailed is not None:
            return detailed
    profile = coordinate_profile(latitude, longitude)
    return {**profile, "site_id": site["id"] if site else "coordinates"}


def observer_radius(profile: dict | None) -> float | None:
    if profile is None:
        return None
    try:
        return profile["datum_radius_m"] + profile["site_elevation_m"] + profile["observer_height_m"]
    except (KeyError, TypeError) as exc:
        raise HorizonError("Terrain profile is missing a valid observer elevation") from exc


def terrain_metadata(profile: dict | None) -> dict:
    return {"horizon_mode": "terrain" if profile else "flat", "terrain": None if profile is None else {
        key: value for key, value in profile.items() if key not in ("horizon", "peak_distance_m", "projection", "binning")
    }}
