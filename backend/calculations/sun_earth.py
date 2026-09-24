"""Sun/Earth geometry for a lunar surface site.

This is just the shared starting point. The actual SPICE frame setup
and local horizon conversion still need to be added.
"""


def calculate_visibility(latitude: float, longitude: float, utc_time: str) -> dict:
    return {
        "latitude": latitude,
        "longitude": longitude,
        "time": utc_time,
        "sun": {
            "azimuth": None,
            "elevation": None,
            "visible": None,
        },
        "earth": {
            "azimuth": None,
            "elevation": None,
            "visible": None,
        },
    }
