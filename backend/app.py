from fastapi import FastAPI, HTTPException, Query

from backend.calculations.sun_earth import (
    SpiceCalculationError,
    calculate_visibility,
    calculate_visibility_window,
    parse_utc_time,
)
from backend.landing_sites import get_landing_site, load_landing_sites
from backend.mission_summary import summarize_window
from backend.spice_kernels import KernelError
from backend.terrain.horizon import HorizonError, apply_horizon, load_profile

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
        return apply_horizon(result, load_profile(site))
    except HorizonError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KernelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SpiceCalculationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _site_window(site: dict, start: str, end: str, step_minutes: int) -> list[dict]:
    profile = load_profile(site)
    samples = calculate_visibility_window(
        site["latitude"], site["longitude"], start, end, step_minutes
    )
    return [apply_horizon(sample, profile) for sample in samples]


@app.get("/api/sites/{site_id}/visibility/window")
def site_visibility_window(
    site_id: str,
    start: str = Query(...),
    end: str = Query(...),
    step_minutes: int = Query(30, ge=1),
):
    try:
        site = get_landing_site(site_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="landing site not found") from exc
    try:
        return _site_window(site, start, end, step_minutes)
    except HorizonError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KernelError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SpiceCalculationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/sites/{site_id}/summary")
def site_summary(
    site_id: str,
    start: str = Query(...),
    end: str = Query(...),
    step_minutes: int = Query(30, ge=1),
):
    try:
        site = get_landing_site(site_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="landing site not found") from exc
    try:
        if parse_utc_time(end) <= parse_utc_time(start):
            raise ValueError("summary end must be after start")
        samples = _site_window(site, start, end, step_minutes)
        return summarize_window(site_id, samples, start, end, step_minutes)
    except HorizonError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
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
