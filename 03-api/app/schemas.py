from typing import Optional

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    unemployment_rate: float = Field(..., ge=0, le=30, examples=[4.3])
    fed_funds_rate: float = Field(..., ge=-1, le=25, examples=[4.33])
    cpi_yoy: float = Field(..., ge=-20, le=50, examples=[2.94])
    gdp_growth: float = Field(..., ge=-30, le=30, examples=[4.38])
    consumer_sentiment: float = Field(..., ge=0, le=150, examples=[58.2])
    recession_flag: int = Field(0, ge=0, le=1)
    growth_lag1: float = Field(..., examples=[-0.17], description="Prior month's % change in revolving credit")
    d_unemployment: float = Field(0.0, description="Change in unemployment_rate vs. prior month")
    d_fed_funds: float = Field(0.0, description="Change in fed_funds_rate vs. prior month")
    d_sentiment: float = Field(0.0, description="Change in consumer_sentiment vs. prior month")
    real_rate: float = Field(..., examples=[1.39], description="fed_funds_rate - cpi_yoy")


class PredictResponse(BaseModel):
    predicted_pct_change: float = Field(
        ..., description="Predicted month-over-month % change in revolving credit."
    )
    inference_function: str
    latency_ms: float


class ForecastResponse(BaseModel):
    as_of_date: str
    predicted_pct_change: float
    revolving_credit_latest: Optional[float] = None
    cached: bool


class HealthResponse(BaseModel):
    status: str
    redshift: Optional[str] = None
