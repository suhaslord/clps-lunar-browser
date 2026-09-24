from fastapi import FastAPI, HTTPException, Query

from backend.calculations.sun_earth import (
    SpiceCalculationError,
    calculate_visibility,
    calculate_visibility_window,
)
from backend.landing_sites import get_landing_site, load_landing_sites
from backend.spice_kernels import KernelError

app = FastAPI(title="CLPS Lunar Browser API")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/sites")
def landing_sites():
    return load_landing_sites()


@app.get("/api/sites/{site_id}/visibility")
def site_visibility(site_id: str, time: str = Query(...)):
    try:
        site = get_landing_site(site_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="landing site not found") from exc

    try:
        result = calculate_visibility(site["latitude"], site["longitude"], time)
        result["site"] = site_id
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KernelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SpiceCalculationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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


@app.get("/api/visibility/window")
def visibility_window(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    start: str = Query(...),
    end: str = Query(...),
    step_minutes: int = Query(30, ge=1),
):
    try:
        return calculate_visibility_window(lat, lon, start, end, step_minutes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KernelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SpiceCalculationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
