-- ============================================================================
-- 01_validate_ingest.sql
--
-- Run in Query Editor v2 after the first successful ingest. One query at a
-- time, in order. Each isolates a different failure mode.
-- ============================================================================

-- 1. Counts and nulls -------------------------------------------------------
SELECT
    COUNT(*)                                            AS n_rows,
    MIN(date)                                           AS first_month,
    MAX(date)                                           AS last_month,
    SUM(CASE WHEN unemployment_rate  IS NULL THEN 1 ELSE 0 END) AS null_unemp,
    SUM(CASE WHEN gdp_growth         IS NULL THEN 1 ELSE 0 END) AS null_gdp,
    SUM(CASE WHEN cpi_yoy            IS NULL THEN 1 ELSE 0 END) AS null_cpi,
    SUM(CASE WHEN revolving_credit   IS NULL THEN 1 ELSE 0 END) AS null_target
FROM credit_risk_prod.macro_conditions;


-- 2. Gap detection ----------------------------------------------------------
SELECT date AS gap_after, next_date, DATEDIFF(month, date, next_date) AS months
FROM (
    SELECT date, LEAD(date) OVER (ORDER BY date) AS next_date
    FROM credit_risk_prod.macro_conditions
)
WHERE next_date IS NOT NULL
  AND DATEDIFF(month, date, next_date) <> 1;


-- 3. Range -----------------------------------------------------------
SELECT
    SUM(CASE WHEN unemployment_rate NOT BETWEEN 2  AND 16   THEN 1 ELSE 0 END) AS bad_unemp,
    SUM(CASE WHEN fed_funds_rate    NOT BETWEEN 0  AND 22   THEN 1 ELSE 0 END) AS bad_ffr,
    SUM(CASE WHEN cpi_yoy           NOT BETWEEN -5 AND 16   THEN 1 ELSE 0 END) AS bad_cpi,
    SUM(CASE WHEN recession_flag    NOT IN (0, 1)           THEN 1 ELSE 0 END) AS bad_flag,
    SUM(CASE WHEN revolving_credit  <= 0                    THEN 1 ELSE 0 END) AS bad_target
FROM credit_risk_prod.macro_conditions;


-- 4. Recession coverage -----------------------------------------------------
SELECT
    SUM(recession_flag)                                  AS recession_months,
    COUNT(*) - SUM(recession_flag)                       AS expansion_months,
    ROUND(100.0 * SUM(recession_flag) / COUNT(*), 1)     AS pct_recession
FROM credit_risk_prod.macro_conditions;


-- 5. GDP growth sawtooth check ------------------------------------------
SELECT
    COUNT(DISTINCT gdp_growth)                                   AS distinct_growth_values,
    COUNT(*) / 3                                                 AS approx_n_quarters,
    SUM(CASE WHEN ROUND(gdp_growth, 6) = 0 THEN 1 ELSE 0 END)    AS zero_months
FROM credit_risk_prod.macro_conditions;


-- 6. The target, eyeballed --------------------------------------------------
SELECT
    date,
    ROUND(revolving_credit, 1) AS revolving_credit,
    ROUND(100.0 * (revolving_credit - LAG(revolving_credit) OVER (ORDER BY date))
              / NULLIF(LAG(revolving_credit) OVER (ORDER BY date), 0), 3) AS mom_pct
FROM credit_risk_prod.macro_conditions
ORDER BY date DESC
LIMIT 24;


-- 7. COPY check -------------------------
SELECT start_time, file_name, line_number, column_name, error_message
FROM   sys_load_error_detail
ORDER  BY start_time DESC
LIMIT  10;
