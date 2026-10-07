"""Select checked-in detailed profiles, otherwise use the global LOLA DEM."""
from backend.calculations.sun_earth import validate_coordinates
from backend.landing_sites import load_landing_sites
import math

from backend.terrain.global_dem import coordinate_profile, distant_terrain_ceiling, outer_profile
from backend.terrain.horizon import HorizonError, load_profile, load_coordinate_profile, validate_profile


def terrain_profile(latitude: float, longitude: float, site: dict | None = None) -> dict:
    validate_coordinates(latitude, longitude)
    if site is None:
        site = next((item for item in load_landing_sites()
                     if item["latitude"] == latitude and item["longitude"] == longitude), None)
    if site:
        detailed = load_profile(site)
        if detailed is None and site.get("terrain_profile_required"):
            raise HorizonError(f"Detailed terrain profile for {site['id']} is missing")
    else:
        detailed = load_coordinate_profile(latitude, longitude)
    if detailed is not None:
        observer_radius(detailed)
        profile = detailed
        if detailed["max_distance_m"] < 300000:
            outer = outer_profile(detailed)
            distances, skyline = [], []
            detailed_ranges = detailed.get("peak_distance_m", [detailed["max_distance_m"]]*len(detailed["horizon"]))
            for i, angle in enumerate(detailed["horizon"]):
                use_outer = outer["horizon"][i] > angle
                skyline.append(outer["horizon"][i] if use_outer else angle)
                distances.append(outer["peak_distance_m"][i] if use_outer else detailed_ranges[i])
            profile = {**detailed, "horizon": skyline, "peak_distance_m": distances,
                       "max_distance_m": outer["max_distance_m"],
                       "detailed_max_distance_m": detailed["max_distance_m"],
                       "outer_terrain": {key: outer[key] for key in
                                         ("source", "pixel_resolution_m", "min_distance_m", "max_distance_m")}}
    else:
        profile = coordinate_profile(latitude, longitude)
    profile["site_id"] = site["id"] if site else profile["site_id"]
    ceiling = distant_terrain_ceiling(profile)
    profile["distant_terrain_ceiling_deg"] = ceiling
    profile["distant_raster_bounded"] = ceiling + 0.0001 < min(profile["horizon"])
    coordinate_rounding = None
    if site and site.get("coordinate_precision_degrees"):
        half_increment = profile["datum_radius_m"] * math.radians(site["coordinate_precision_degrees"] / 2)
        coordinate_rounding = {"assumption": "rounded to nearest catalog increment; not measured position error",
                               "north_south_m": half_increment,
                               "east_west_m": half_increment * math.cos(math.radians(latitude))}
    profile["accuracy"] = {
        "status": "unvalidated", "survey_grade": False,
        "horizontal_error_m": None, "vertical_error_m": None, "horizon_error_deg": None,
        "independent_control_points": 0,
        "coordinate_rounding": coordinate_rounding,
        "limits": ["terrain smaller than source cells may be unresolved",
                   "terrain inside min_distance_m is omitted",
                   "observer height is assumed, not measured",
                   "raster ceiling bounds represented distant cell heights only",
                   "source, registration and skyline errors have no validated absolute bound"],
    }
    return validate_profile(profile)


def observer_radius(profile: dict | None) -> float | None:
    if profile is None:
        return None
    try:
        return profile["datum_radius_m"] + profile["site_elevation_m"] + profile["observer_height_m"]
    except (KeyError, TypeError) as exc:
        raise HorizonError("Terrain profile is missing a valid observer elevation") from exc


def terrain_metadata(profile: dict | None) -> dict:
    if profile is None:
        return {"horizon_mode": "flat", "terrain": None}
    details = {key: value for key, value in profile.items() if key not in
               ("horizon", "peak_distance_m", "projection", "binning", "source_subset")}
    if "source_subset" in profile:
        details["source_subset"] = {key: profile["source_subset"][key] for key in
                                    ("source_etag", "retrieved_subset_sha256", "coverage")}
    return {"horizon_mode": "terrain", "terrain": details}
