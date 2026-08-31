from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException
from prometheus_client import Histogram
from prometheus_fastapi_instrumentator import Instrumentator

from .config import settings
from .redshift import RedshiftQueryError, client
from .schemas import ForecastResponse, HealthResponse, PredictRequest, PredictResponse

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("credit-risk-api")

app = FastAPI(
    title="Credit Risk Analytics API",
    description="Macroeconomic predictors of U.S. consumer revolving credit (FRED REVOLSL).",
    version="3.0.0",
)

REDSHIFT_SECONDS = Histogram(
    "redshift_query_seconds",
    "Wall time of a Redshift Data API round trip.",
    ["endpoint"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

_cache: dict[str, Any] = {"value": None, "expires": 0.0}
_cache_lock = Lock()


def _fq(name: str) -> str:
    return f"{settings.redshift_schema}.{name}"


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/health/ready", response_model=HealthResponse, tags=["ops"])
def ready() -> HealthResponse:
    try:
        client.ping()
        return HealthResponse(status="ok", redshift="reachable")
    except Exception as exc:  # noqa: BLE001
        log.warning("readiness check failed: %s", exc)
        return HealthResponse(status="degraded", redshift=str(exc))


@app.post("/predict", response_model=PredictResponse, tags=["inference"])
def predict(payload: PredictRequest) -> PredictResponse:
    sql = f"""
        SELECT {_fq(settings.ml_predict_function)}(
            :unemployment_rate::double precision,
            :fed_funds_rate::double precision,
            :cpi_yoy::double precision,
            :gdp_growth::double precision,
            :consumer_sentiment::double precision,
            :recession_flag::smallint,
            :growth_lag1::double precision,
            :d_unemployment::double precision,
            :d_fed_funds::double precision,
            :d_sentiment::double precision,
            :real_rate::double precision
        ) AS predicted_pct_change
        FROM {_fq('model_input')}
        LIMIT 1
    """

    started = time.monotonic()
    try:
        rows = client.run(sql, payload.model_dump())
    except RedshiftQueryError as exc:
        raise HTTPException(status_code=503, detail=f"inference failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("unexpected error during redshift inference")
        raise HTTPException(status_code=503, detail=f"warehouse error: {exc}") from exc
    elapsed = time.monotonic() - started
    REDSHIFT_SECONDS.labels(endpoint="predict").observe(elapsed)

    if not rows or rows[0]["predicted_pct_change"] is None:
        raise HTTPException(status_code=502, detail="model returned no prediction")

    return PredictResponse(
        predicted_pct_change=float(rows[0]["predicted_pct_change"]),
        inference_function=settings.ml_predict_function,
        latency_ms=round(elapsed * 1000, 1),
    )


@app.get("/forecast/latest", response_model=ForecastResponse, tags=["inference"])
def latest_forecast() -> ForecastResponse:
    now = time.monotonic()
    with _cache_lock:
        if _cache["value"] is not None and now < _cache["expires"]:
            cached = dict(_cache["value"])
            cached["cached"] = True
            return ForecastResponse(**cached)

    sql = f"""
        WITH latest AS (
            SELECT date, unemployment_rate, fed_funds_rate, cpi_yoy, gdp_growth,
                   consumer_sentiment, recession_flag, growth_lag1,
                   d_unemployment, d_fed_funds, d_sentiment, real_rate
            FROM {_fq('model_input')}
            ORDER BY date DESC
            LIMIT 1
        )
        SELECT TO_CHAR(date, 'YYYY-MM-DD') AS as_of_date,
               {_fq(settings.ml_predict_function)}(
                   unemployment_rate::double precision,
                   fed_funds_rate::double precision,
                   cpi_yoy::double precision,
                   gdp_growth::double precision,
                   consumer_sentiment::double precision,
                   recession_flag::smallint,
                   growth_lag1::double precision,
                   d_unemployment::double precision,
                   d_fed_funds::double precision,
                   d_sentiment::double precision,
                   real_rate::double precision
               ) AS predicted_pct_change
        FROM latest
    """

    started = time.monotonic()
    try:
        rows = client.run(sql)
    except RedshiftQueryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        log.exception("unexpected error computing forecast")
        raise HTTPException(status_code=503, detail=f"warehouse error: {exc}") from exc
    REDSHIFT_SECONDS.labels(endpoint="forecast").observe(time.monotonic() - started)

    if not rows:
        raise HTTPException(status_code=404, detail="no rows in model_input")

    record = {
        "as_of_date": rows[0]["as_of_date"],
        "predicted_pct_change": float(rows[0]["predicted_pct_change"]),
        "revolving_credit_latest": None,
        "cached": False,
    }

    with _cache_lock:
        _cache["value"] = record
        _cache["expires"] = time.monotonic() + settings.forecast_cache_seconds

    return ForecastResponse(**record)
