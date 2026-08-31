"""API tests. Redshift is mocked at the client boundary. Beyond the usual
endpoint checks, this file specifically asserts the two things that would
otherwise fail only once deployed: every predict SQL string is schema-
qualified and every predict SQL string has a real FROM clause.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import _cache, app
from app.redshift import RedshiftQueryError

client = TestClient(app)

VALID_PAYLOAD = {
    "unemployment_rate": 4.3,
    "fed_funds_rate": 4.33,
    "cpi_yoy": 2.94,
    "gdp_growth": 4.38,
    "consumer_sentiment": 58.2,
    "recession_flag": 0,
    "growth_lag1": -0.17,
    "d_unemployment": 0.0,
    "d_fed_funds": 0.0,
    "d_sentiment": -3.5,
    "real_rate": 1.39,
}


@pytest.fixture(autouse=True)
def clear_cache():
    _cache["value"] = None
    _cache["expires"] = 0.0
    yield


def test_health_does_not_touch_redshift():
    with patch("app.main.client.run") as run:
        assert client.get("/health").json()["status"] == "ok"
        run.assert_not_called()


def test_predict_returns_model_output():
    with patch("app.main.client.run", return_value=[{"predicted_pct_change": 0.34}]):
        body = client.post("/predict", json=VALID_PAYLOAD).json()
    assert body["predicted_pct_change"] == pytest.approx(0.34)
    assert body["inference_function"] == "predict_credit_growth"


def test_predict_sql_is_schema_qualified():
    """Calling the function unqualified resolves against the session
    search_path and fails as 'does not exist' with no clue that schema is
    the issue -- this is the single most expensive bug from this session to
    rediscover, so it gets its own permanent test."""
    with patch("app.main.client.run", return_value=[{"predicted_pct_change": 0.1}]) as run:
        client.post("/predict", json=VALID_PAYLOAD)
    sql = run.call_args[0][0]
    assert "credit_risk_prod.predict_credit_growth(" in sql


def test_predict_sql_has_a_from_clause():
    """Redshift ML inference functions run on compute nodes; a bare SELECT
    with no FROM has nothing to distribute across them and fails with
    'must be applied on at least one user created table.'"""
    with patch("app.main.client.run", return_value=[{"predicted_pct_change": 0.1}]) as run:
        client.post("/predict", json=VALID_PAYLOAD)
    sql = run.call_args[0][0]
    assert "FROM credit_risk_prod.model_input" in sql


def test_predict_sends_all_eleven_features_in_order():
    with patch("app.main.client.run", return_value=[{"predicted_pct_change": 0.1}]) as run:
        client.post("/predict", json=VALID_PAYLOAD)
    params = run.call_args[0][1]
    assert list(params) == list(VALID_PAYLOAD)


def test_predict_rejects_out_of_range_input():
    with patch("app.main.client.run") as run:
        bad = {**VALID_PAYLOAD, "unemployment_rate": 400}
        assert client.post("/predict", json=bad).status_code == 422
        run.assert_not_called()


def test_predict_surfaces_warehouse_failure_as_503():
    with patch("app.main.client.run", side_effect=RedshiftQueryError("boom")):
        assert client.post("/predict", json=VALID_PAYLOAD).status_code == 503


def test_unexpected_boto_error_becomes_503_not_500():
    from botocore.exceptions import ClientError
    err = ClientError({"Error": {"Code": "AccessDeniedException"}}, "ExecuteStatement")
    with patch("app.main.client.run", side_effect=err):
        assert client.post("/predict", json=VALID_PAYLOAD).status_code == 503


def test_forecast_pulls_latest_row_and_is_schema_qualified():
    row = [{"as_of_date": "2025-09-01", "predicted_pct_change": 0.34}]
    with patch("app.main.client.run", return_value=row) as run:
        body = client.get("/forecast/latest").json()
    sql = run.call_args[0][0]
    assert "FROM credit_risk_prod.model_input" in sql
    assert "credit_risk_prod.predict_credit_growth(" in sql
    assert "ORDER BY date DESC" in sql
    assert body["predicted_pct_change"] == pytest.approx(0.34)


def test_forecast_is_cached_after_first_call():
    row = [{"as_of_date": "2025-09-01", "predicted_pct_change": 0.34}]
    with patch("app.main.client.run", return_value=row) as run:
        first = client.get("/forecast/latest").json()
        second = client.get("/forecast/latest").json()
    assert run.call_count == 1
    assert first["cached"] is False and second["cached"] is True


def test_forecast_404s_when_model_input_is_empty():
    with patch("app.main.client.run", return_value=[]):
        assert client.get("/forecast/latest").status_code == 404


def test_metrics_endpoint_exposes_redshift_histogram():
    assert "redshift_query_seconds" in client.get("/metrics").text
