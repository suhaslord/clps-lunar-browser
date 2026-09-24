from fastapi import FastAPI, Query

app = FastAPI(title="CLPS Lunar Browser API")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/visibility")
def visibility(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    time: str = Query(...),
):
    # placeholder response so frontend can start wiring things up
    # real SPICE calculations will replace these values
    return {
        "site": None,
        "latitude": lat,
        "longitude": lon,
        "time": time,
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
