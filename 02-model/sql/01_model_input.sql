-- 02-model/sql/01_model_input.sql


CREATE OR REPLACE VIEW ${SCHEMA}.model_input AS
WITH base AS (
    SELECT date, revolving_credit, unemployment_rate, fed_funds_rate,
           cpi_yoy, gdp_growth, consumer_sentiment, recession_flag
    FROM ${SCHEMA}.macro_conditions
),
derived AS (
    SELECT *,
           (LEAD(revolving_credit) OVER (ORDER BY date)
                / NULLIF(revolving_credit, 0) - 1) * 100 AS target,

           (revolving_credit / NULLIF(LAG(revolving_credit) OVER (ORDER BY date), 0) - 1) * 100
               AS growth_lag1,

           unemployment_rate  - LAG(unemployment_rate)  OVER (ORDER BY date) AS d_unemployment,
           fed_funds_rate     - LAG(fed_funds_rate)     OVER (ORDER BY date) AS d_fed_funds,
           consumer_sentiment - LAG(consumer_sentiment) OVER (ORDER BY date) AS d_sentiment,

           fed_funds_rate - cpi_yoy AS real_rate
    FROM base
)
SELECT date, target,
       unemployment_rate, fed_funds_rate, cpi_yoy, gdp_growth,
       consumer_sentiment, recession_flag,
       growth_lag1, d_unemployment, d_fed_funds, d_sentiment, real_rate,

       -- Regime interactions for the predictive question.
       unemployment_rate  * recession_flag AS unemp_x_recession,
       consumer_sentiment * recession_flag AS sentiment_x_recession,
       gdp_growth         * recession_flag AS gdp_x_recession,
       real_rate          * recession_flag AS real_rate_x_recession
FROM derived
WHERE target IS NOT NULL        -- final month has no t+1
  AND growth_lag1 IS NOT NULL;  -- first month has no t-1


-- ===========================================================================
-- Validation -- run every time before CREATE MODEL, not just once.
-- ===========================================================================

SELECT COUNT(*) AS rows_where_target_is_not_forward
FROM (
    SELECT m.target,
           (LEAD(c.revolving_credit) OVER (ORDER BY c.date)
                / c.revolving_credit - 1) * 100 AS expected
    FROM ${SCHEMA}.model_input m
    JOIN ${SCHEMA}.macro_conditions c USING (date)
)
WHERE target IS NOT NULL AND expected IS NOT NULL
  AND ABS(target - expected) > 1e-9;


SELECT COUNT(*)                                          AS total_rows,
       MIN(date)                                         AS first_month,
       MAX(date)                                         AS last_month,
       SUM(CASE WHEN recession_flag = 1 THEN 1 ELSE 0 END) AS recession_months
FROM ${SCHEMA}.model_input;




SELECT SUM(CASE WHEN target             IS NULL THEN 1 ELSE 0 END) AS null_target,
       SUM(CASE WHEN growth_lag1        IS NULL THEN 1 ELSE 0 END) AS null_lag1,
       SUM(CASE WHEN d_unemployment     IS NULL THEN 1 ELSE 0 END) AS null_d_unemployment,
       SUM(CASE WHEN real_rate          IS NULL THEN 1 ELSE 0 END) AS null_real_rate
FROM ${SCHEMA}.model_input;
