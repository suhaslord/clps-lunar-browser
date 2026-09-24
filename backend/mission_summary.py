from datetime import timedelta

from backend.calculations.sun_earth import parse_utc_time


def summarize_window(
    site_id: str, samples: list[dict], start: str, end: str, step_minutes: int
) -> dict:
    start_time = parse_utc_time(start)
    end_time = parse_utc_time(end)
    if end_time <= start_time:
        raise ValueError("summary end must be after start")

    keys = ("sunlight", "earth_visible", "both", "darkness", "comm_blackout")
    windows = {key: [] for key in keys}
    opened = {key: None for key in keys}
    totals = {key: 0.0 for key in keys}
    step = timedelta(minutes=step_minutes)

    for sample in samples:
        time = parse_utc_time(sample["time"])
        if time >= end_time:
            break
        until = min(time + step, end_time)
        sun = sample["sun"]["visible"]
        earth = sample["earth"]["visible"]
        states = {
            "sunlight": sun,
            "earth_visible": earth,
            "both": sun and earth,
            "darkness": not sun,
            "comm_blackout": not earth,
        }
        for key, active in states.items():
            if active:
                totals[key] += (until - time).total_seconds()
                if opened[key] is None:
                    opened[key] = time
            elif opened[key] is not None:
                windows[key].append((opened[key], time))
                opened[key] = None

    for key in keys:
        if opened[key] is not None:
            windows[key].append((opened[key], end_time))

    def output_window(pair):
        return {
            "start": pair[0].isoformat().replace("+00:00", "Z"),
            "end": pair[1].isoformat().replace("+00:00", "Z"),
        }

    def longest(key):
        lengths = ((right - left).total_seconds() / 60 for left, right in windows[key])
        return max(lengths, default=0)

    duration = (end_time - start_time).total_seconds()
    return {
        "site": site_id,
        "start": start_time.isoformat().replace("+00:00", "Z"),
        "end": end_time.isoformat().replace("+00:00", "Z"),
        "step_minutes": step_minutes,
        "sunlight_percent": round(100 * totals["sunlight"] / duration, 1),
        "earth_visible_percent": round(100 * totals["earth_visible"] / duration, 1),
        "both_available_percent": round(100 * totals["both"] / duration, 1),
        "longest_darkness_minutes": longest("darkness"),
        "longest_comm_blackout_minutes": longest("comm_blackout"),
        "windows": {
            key: [output_window(pair) for pair in windows[key]]
            for key in ("sunlight", "earth_visible", "both")
        },
    }
