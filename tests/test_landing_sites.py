import json

import pytest

from backend.landing_sites import get_landing_site, load_landing_sites


def test_landing_sites_load_with_unique_ids_and_valid_coordinates():
    sites = load_landing_sites()
    site_ids = [site["id"] for site in sites]

    assert len(sites) == 2
    assert len(site_ids) == len(set(site_ids))
    for site in sites:
        assert -90 <= site["latitude"] <= 90
        assert -180 <= site["longitude"] <= 180
        assert site["source"].startswith("https://")


def test_landing_site_lookup():
    site = get_landing_site("athena-im2")

    assert site["mission"] == "IM-2 Athena"
    assert site["latitude"] == -84.79
    assert site["longitude"] == 29.20
    with pytest.raises(KeyError):
        get_landing_site("no-such-site")


@pytest.mark.parametrize(
    "sites, message",
    [
        (
            [
                {
                    "id": "dup",
                    "name": "One",
                    "latitude": 0,
                    "longitude": 0,
                    "source": "https://a",
                },
                {
                    "id": "dup",
                    "name": "Two",
                    "latitude": 0,
                    "longitude": 0,
                    "source": "https://b",
                },
            ],
            "duplicate",
        ),
        (
            [
                {
                    "id": "bad-coords",
                    "name": "Bad",
                    "latitude": 91,
                    "longitude": 0,
                    "source": "https://a",
                }
            ],
            "invalid coordinates",
        ),
    ],
)
def test_loader_rejects_duplicate_ids_and_invalid_coordinates(tmp_path, sites, message):
    path = tmp_path / "landing_sites.json"
    path.write_text(json.dumps(sites), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_landing_sites(path)
