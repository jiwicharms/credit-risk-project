-- 02-model/sql/03_explain.sql


-- ===========================================================================
-- Immediate: predicted next-month % change under current conditions.
-- ===========================================================================
--

SELECT unemployment_rate, fed_funds_rate, cpi_yoy, gdp_growth,
       consumer_sentiment, recession_flag, growth_lag1,
       d_unemployment, d_fed_funds, d_sentiment, real_rate
FROM ${SCHEMA}.model_input
ORDER BY date DESC
LIMIT 1;
-- Copy this row values into the call below, keeping the ::double precision
-- and ::smallint casts.

SELECT ${SCHEMA}.predict_credit_growth(
    0.0::double precision,  -- unemployment_rate
    0.0::double precision,  -- fed_funds_rate
    0.0::double precision,  -- cpi_yoy
    0.0::double precision,  -- gdp_growth
    0.0::double precision,  -- consumer_sentiment
    0::smallint,             -- recession_flag
    0.0::double precision,  -- growth_lag1
    0.0::double precision,  -- d_unemployment
    0.0::double precision,  -- d_fed_funds
    0.0::double precision,  -- d_sentiment
    0.0::double precision   -- real_rate
) AS predicted_next_month_pct_change
FROM ${SCHEMA}.model_input
LIMIT 1;
