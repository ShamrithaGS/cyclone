from __future__ import annotations

import logging
from fastapi import FastAPI, HTTPException, Query, status

from advisory_service import build_advisory_response
from forecast_service import (
    ForecastRequest,
    get_forecast_by_id,
    run_forecast_pipeline,
)

log = logging.getLogger("main_api")

app = FastAPI(
    title="Cyclone Advisory & Vulnerability Forecast API",
    description="Operational cyclone tracking, storm surge modeling, rainfall/slope hazard analysis, and advisory generation.",
    version="1.0.0",
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/forecast")
def get_forecast(
    cyclone_id: str = Query(default="demo", description="Event identifier (e.g. 'demo', 'test_2026', 'michaung')"),
    use_demo_infra: bool = Query(default=False, description="Evaluate against synthetic demo infrastructure"),
):
    """Retrieve cyclone vulnerability forecast by event ID or default track."""
    try:
        return get_forecast_by_id(cyclone_id=cyclone_id, use_demo_infra=use_demo_infra)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        log.exception("Unexpected error in GET /forecast: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal modeling error processing forecast request.",
        )


@app.post("/forecast")
def post_forecast(request: ForecastRequest):
    """Compute cyclone vulnerability forecast for a custom track (JSON points or CSV path)."""
    try:
        return run_forecast_pipeline(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        log.exception("Unexpected error in POST /forecast: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal modeling error processing forecast request.",
        )


@app.get("/advisory")
def advisory(cyclone_id: str = Query(default="demo")):
    return build_advisory_response(cyclone_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
