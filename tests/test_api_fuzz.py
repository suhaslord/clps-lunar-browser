"""Seeded malformed-query testing through the actual ASGI request stack."""
import random
import string

from fastapi.testclient import TestClient

from backend.app import app


client = TestClient(app)
START = "2026-10-03T00:00:00Z"
END = "2026-10-03T01:00:00Z"


def test_1200_invalid_coordinate_queries_never_become_server_errors():
    rng = random.Random(318)
    for i in range(300):
        field = "lat" if i % 2 else "lon"
        limit = 90 if field == "lat" else 180
        value = rng.choice(["nan", "inf", "-inf", "1e9999", "9"*500,
                            str(limit+rng.random()*1000), str(-limit-rng.random()*1000),
                            "x"+"".join(rng.choices(string.printable, k=rng.randrange(1, 40)))])
        params = {"lat": 0, "lon": 0, "time": START, "start": START, "end": END,
                  "terrain": False, field: value}
        for route in ["visibility", "visibility/window", "summary", "horizon"]:
            response = client.get("/api/"+route, params=params)
            assert response.status_code == 422, (route, params, response.status_code, response.text)


def test_1200_invalid_timestamp_queries_are_validation_errors():
    rng = random.Random(55)
    values = ["", "2026-02-30T00:00:00Z", "2026-10-03T24:00:00Z", "2026-10-03",
              "2026-10-03T00:00:00", "2026-10-03T23:59:60Z", "2026-10-03T00:00:00+99:00",
              "0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"]
    for i in range(200):
        value = rng.choice(values) if i % 2 else "invalid"+"".join(rng.choices(string.printable, k=rng.randrange(1, 100)))
        for base in ["/api", "/api/sites/athena-im2"]:
            for route in ["visibility", "visibility/window", "summary"]:
                params = {"lat": 0, "lon": 0, "time": value, "start": value, "end": END, "terrain": False}
                response = client.get(base+"/"+route, params=params)
                assert response.status_code == 422, (route, value, response.status_code, response.text)


def test_400_invalid_steps_are_rejected_before_calculation():
    rng = random.Random(183)
    values = ["0", "-1", "1.5", "nan", "inf", "1e12", "9"*500, "true", "", "word"]
    for _ in range(100):
        params = {"lat": 0, "lon": 0, "start": START, "end": END,
                  "step_minutes": rng.choice(values), "terrain": False}
        for base in ["/api", "/api/sites/odysseus-im1"]:
            for route in ["visibility/window", "summary"]:
                response = client.get(base+"/"+route, params=params)
                assert response.status_code == 422, (route, response.status_code, response.text)
