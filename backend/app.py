from fastapi import FastAPI, HTTPException, Query

from backend.calculations.sun_earth import SpiceCalculationError, calculate_visibility
from backend.spice_kernels import KernelError

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
    try:
        return calculate_visibility(lat, lon, time)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KernelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SpiceCalculationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
