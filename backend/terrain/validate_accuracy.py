"""Compare independent lunar control measurements with the selected terrain model.

Passing observed points does not certify unsampled terrain or reference independence.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

from backend.calculations.sun_earth import validate_coordinates
from backend.landing_sites import load_landing_sites
from backend.terrain.global_dem import RADIUS_M, global_dem, sample_height
from backend.terrain.horizon import load_coordinate_profile, load_profile


def _number(value, name):
    try:
        valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def selected_height(latitude, longitude):
    site = next((site for site in load_landing_sites() if
                 site["latitude"] == latitude and site["longitude"] == longitude), None)
    profile = load_profile(site) if site else load_coordinate_profile(latitude, longitude)
    if profile:
        return profile["site_elevation_m"]
    grid, _ = global_dem()
    return sample_height(grid, latitude, longitude)


def compare_control_points(points, height_sampler, horizontal_tolerance_m, vertical_tolerance_m):
    horizontal_limit = _number(horizontal_tolerance_m, "horizontal tolerance")
    vertical_limit = _number(vertical_tolerance_m, "vertical tolerance")
    if horizontal_limit <= 0 or vertical_limit <= 0:
        raise ValueError("tolerances must be positive")
    if not isinstance(points, list) or len(points) < 3:
        raise ValueError("provide at least three independently matched control points")
    seen, measurements = set(), []
    for point in points:
        if not isinstance(point, dict):
            raise ValueError("each control point must be an object")
        feature = point.get("feature_id")
        if not isinstance(feature, str) or not feature or feature in seen:
            raise ValueError("control point feature IDs must be unique nonempty strings")
        seen.add(feature)
        values = {key: _number(point.get(key), key) for key in
                  ("model_latitude", "model_longitude", "reference_latitude", "reference_longitude", "reference_elevation_m")}
        validate_coordinates(values["model_latitude"], values["model_longitude"])
        validate_coordinates(values["reference_latitude"], values["reference_longitude"])
        reference_height = values["reference_elevation_m"]
        model_height = _number(height_sampler(values["model_latitude"], values["model_longitude"]), "model height")
        if not (-RADIUS_M < reference_height < RADIUS_M and -RADIUS_M < model_height < RADIUS_M):
            raise ValueError("control elevation must be a plausible lunar datum height")
        def vector(lat, lon):
            lat, lon = math.radians(lat), math.radians(lon)
            return np.array([math.cos(lat)*math.cos(lon), math.cos(lat)*math.sin(lon), math.sin(lat)])
        model = vector(values["model_latitude"], values["model_longitude"])
        reference = vector(values["reference_latitude"], values["reference_longitude"])
        horizontal = RADIUS_M * math.atan2(float(np.linalg.norm(np.cross(model, reference))), float(model @ reference))
        vertical = model_height - reference_height
        measurements.append({"feature_id": feature, **values, "model_elevation_m": model_height,
                             "horizontal_residual_m": horizontal, "vertical_residual_m": vertical,
                             "within_tolerances": horizontal <= horizontal_limit and abs(vertical) <= vertical_limit})
    horizontal = np.array([p["horizontal_residual_m"] for p in measurements])
    vertical = np.array([p["vertical_residual_m"] for p in measurements])
    return {
        "status": "observed_control_comparison", "survey_grade": False,
        "scope": "supplied matched features only; no bound for unsampled terrain or skylines",
        "reference_independence": "must be verified externally; cannot be inferred from residuals",
        "control_point_count": len(measurements),
        "horizontal_tolerance_m": horizontal_limit, "vertical_tolerance_m": vertical_limit,
        "all_observed_points_within_tolerances": all(p["within_tolerances"] for p in measurements),
        "horizontal_rmse_m": float(np.sqrt(np.mean(horizontal**2))),
        "horizontal_p95_m": float(np.percentile(horizontal, 95)),
        "horizontal_max_observed_m": float(horizontal.max()),
        "vertical_bias_m": float(vertical.mean()),
        "vertical_rmse_m": float(np.sqrt(np.mean(vertical**2))),
        "vertical_p95_absolute_m": float(np.percentile(np.abs(vertical), 95)),
        "vertical_max_absolute_observed_m": float(np.abs(vertical).max()),
        "measurements": measurements,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--horizontal-tolerance-m", type=float, required=True)
    parser.add_argument("--vertical-tolerance-m", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.reference.read_text(encoding="utf-8"))
    if not isinstance(source, dict) or source.get("source_frame") != "MOON_ME_DE421" or source.get("datum_radius_m") != RADIUS_M:
        parser.error("references must declare MOON_ME_DE421 and the 1737400 m datum")
    if not isinstance(source.get("source"), str) or not source["source"].startswith("https://"):
        parser.error("references must include an HTTPS provenance source")
    report = compare_control_points(source.get("points"), selected_height,
                                    args.horizontal_tolerance_m, args.vertical_tolerance_m)
    report["reference_source"] = source["source"]
    report["source_frame"] = source["source_frame"]
    report["datum_radius_m"] = RADIUS_M
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Compared {report['control_point_count']} observed points; survey certification remains unestablished")


if __name__ == "__main__":
    main()
