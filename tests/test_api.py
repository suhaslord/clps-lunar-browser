import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.calculations.sun_earth import (
    SpiceCalculationError,
    parse_utc_time,
    validate_coordinates,
)


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_visibility_response_shape(monkeypatch):
    expected = {
        "site": None,
        "latitude": -89.5,
        "longitude": 135.0,
        "time": "2026-10-03T18:00:00Z",
        "sun": {"azimuth": 124.2, "elevation": 3.7, "visible": True},
        "earth": {"azimuth": 241.8, "elevation": 7.1, "visible": True},
    }
    monkeypatch.setattr("backend.app.calculate_visibility", lambda *_: expected)

    response = client.get(
        "/api/visibility?lat=-89.5&lon=135&time=2026-10-03T18:00:00Z"
    )
    assert response.status_code == 200
    assert response.json() == expected


def test_api_rejects_out_of_range_coordinates():
    response = client.get(
        "/api/visibility?lat=91&lon=0&time=2026-10-03T18:00:00Z"
    )
    assert response.status_code == 422


def test_api_rejects_invalid_timestamp():
    response = client.get("/api/visibility?lat=0&lon=0&time=not-a-time")
    assert response.status_code == 422
    assert "ISO 8601" in response.json()["detail"]


def test_missing_kernels_return_service_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("SPICE_KERNELS_DIR", str(tmp_path))

    response = client.get("/api/visibility?lat=0&lon=0&time=2026-10-03T18:00:00Z")
    assert response.status_code == 503
    assert "naif0012.tls" in response.json()["detail"]


def test_input_helpers():
    assert validate_coordinates(-89.5, 135) == (-89.5, 135)
    assert parse_utc_time("2026-10-03T18:00:00Z").isoformat() == (
        "2026-10-03T18:00:00+00:00"
    )
    with pytest.raises(ValueError, match="timezone"):
        parse_utc_time("2026-10-03T18:00:00")
    with pytest.raises(ValueError, match="lat"):
        validate_coordinates(91, 0)


def test_spice_calculation_error_returns_bad_gateway(monkeypatch):
    def fail_calculation(*_):
        raise SpiceCalculationError("SPICE failed")

    monkeypatch.setattr("backend.app.calculate_visibility", fail_calculation)
    response = client.get("/api/visibility?lat=0&lon=0&time=2026-10-03T18:00:00Z")

    assert response.status_code == 502
    assert response.json()["detail"] == "SPICE failed"


def test_visibility_window_response_shape(monkeypatch):
    expected = [
        {
            "time": "2026-10-03T18:00:00Z",
            "sun": {"azimuth": 134.3, "elevation": 0.7, "visible": True},
            "earth": {"azimuth": 226.8, "elevation": 4.2, "visible": True},
        }
    ]
    monkeypatch.setattr("backend.app.calculate_visibility_window", lambda *_: expected)

    response = client.get(
        "/api/visibility/window?lat=-89.5&lon=135&start=2026-10-03T18:00:00Z"
        "&end=2026-10-03T18:00:00Z&step_minutes=30"
    )

    assert response.status_code == 200
    assert response.json() == expected


def test_visibility_window_rejects_invalid_step():
    response = client.get(
        "/api/visibility/window?lat=0&lon=0&start=2026-10-03T00:00:00Z"
        "&end=2026-10-03T01:00:00Z&step_minutes=0"
    )

    assert response.status_code == 422


def test_sites_endpoint_lists_landing_sites():
    response = client.get("/api/sites")

    assert response.status_code == 200
    sites = response.json()
    assert [site["id"] for site in sites] == ["odysseus-im1", "athena-im2"]
    assert sites[0]["latitude"] == -80.13
    assert sites[0]["longitude"] == 1.44


def test_named_site_visibility_uses_site_coordinates(monkeypatch):
    expected = {
        "site": None,
        "latitude": -84.79,
        "longitude": 29.2,
        "time": "2026-10-03T18:00:00Z",
        "sun": {"azimuth": 140.0, "elevation": 1.0, "visible": True},
        "earth": {"azimuth": 220.0, "elevation": 5.0, "visible": True},
    }
    calls = []

    def fake_calculation(latitude, longitude, time):
        calls.append((latitude, longitude, time))
        return expected.copy()

    monkeypatch.setattr("backend.app.calculate_visibility", fake_calculation)
    response = client.get(
        "/api/sites/athena-im2/visibility?time=2026-10-03T18:00:00Z"
    )

    assert response.status_code == 200
    assert calls == [(-84.79, 29.2, "2026-10-03T18:00:00Z")]
    assert response.json()["site"] == "athena-im2"


def test_named_site_visibility_returns_404_for_unknown_site():
    response = client.get(
        "/api/sites/no-such-site/visibility?time=2026-10-03T18:00:00Z"
    )

    assert response.status_code == 404
