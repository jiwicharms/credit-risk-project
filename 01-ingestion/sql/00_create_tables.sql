-- ============================================================================
-- 00_create_tables.sql
--
-- Run this once in Query Editor v2 before the first ingest.
-- Connect to: workgroup credit-risk-wg, database dev.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS credit_risk_dev;
CREATE SCHEMA IF NOT EXISTS credit_risk_prod;


-- ---------------------------------------------------------------- prod table
DROP TABLE IF EXISTS credit_risk_prod.macro_conditions;

CREATE TABLE credit_risk_prod.macro_conditions (
    date                DATE            NOT NULL,
    unemployment_rate   DOUBLE PRECISION,   -- UNRATE,     monthly,   percent
    real_gdp            DOUBLE PRECISION,   -- GDPC1,      quarterly, billions chained 2017$
    gdp_growth          DOUBLE PRECISION,   -- derived,    annualized percent
    fed_funds_rate      DOUBLE PRECISION,   -- FEDFUNDS,   monthly,   percent
    cpi                 DOUBLE PRECISION,   -- CPIAUCSL,   monthly,   index 1982-84=100
    cpi_yoy             DOUBLE PRECISION,   -- derived,    percent
    consumer_sentiment  DOUBLE PRECISION,   -- UMCSENT,    monthly,   index
    recession_flag      SMALLINT,           -- USREC,      monthly,   0/1
    revolving_credit    DOUBLE PRECISION,   -- REVOLSL,    monthly,   billions $  <- TARGET SOURCE
    cc_delinquency_rate DOUBLE PRECISION,   -- DRCCLACBS,  quarterly, percent
    cc_chargeoff_rate   DOUBLE PRECISION    -- CORCCACBS,  quarterly, percent
)
DISTSTYLE ALL
SORTKEY (date);

-- ---------------------------------------------------------------- dev table
DROP TABLE IF EXISTS credit_risk_dev.macro_conditions;

CREATE TABLE credit_risk_dev.macro_conditions (LIKE credit_risk_prod.macro_conditions);


-- ---------------------------------------------------------------- verify
SELECT table_schema, table_name
FROM   information_schema.tables
WHERE  table_schema IN ('credit_risk_dev', 'credit_risk_prod')
ORDER  BY table_schema;

