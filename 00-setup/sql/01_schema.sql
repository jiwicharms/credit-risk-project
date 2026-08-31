-- 00-setup/sql/01_schema.sql
--
-- Run via 00-setup/create_schema.sh, which substitutes ${SCHEMA} and
-- ${API_ROLE_NAME} from your environment.
--
-- Column order below MUST match the COLUMNS list in
-- 01-ingestion/src/ingest_fred.py. COPY maps CSV fields by position, so a
-- mismatch loads unemployment_rate into real_gdp and reports success. Nothing
-- downstream will flag it: the values are all plausible floats.

CREATE SCHEMA IF NOT EXISTS ${SCHEMA};

CREATE TABLE IF NOT EXISTS ${SCHEMA}.macro_conditions (
    date                    DATE             NOT NULL,
    unemployment_rate       DOUBLE PRECISION,
    real_gdp                DOUBLE PRECISION,
    gdp_growth              DOUBLE PRECISION,
    fed_funds_rate          DOUBLE PRECISION,
    cpi                     DOUBLE PRECISION,
    cpi_yoy                 DOUBLE PRECISION,
    consumer_sentiment      DOUBLE PRECISION,
    recession_flag          SMALLINT,
    revolving_credit        DOUBLE PRECISION,
    -- Nullable on purpose: neither series exists before 1991Q1, and forward
    -- fill cannot invent history backwards. See --credit-card in ingest_fred.py.
    cc_delinquency_rate     DOUBLE PRECISION,
    cc_chargeoff_rate       DOUBLE PRECISION
)
DISTSTYLE ALL   -- a few hundred rows; replicate to every node
SORTKEY (date);

-- Grants for whatever serves the API. Redshift refers to an IAM identity with
-- the IAMR: prefix. Skipping this produces a 503 whose message says permission
-- denied for schema — which reads like an IAM policy problem but is a database
-- grant problem, one layer further in.
CREATE USER IF NOT EXISTS "IAMR:${API_ROLE_NAME}" PASSWORD DISABLE;

GRANT USAGE ON SCHEMA ${SCHEMA} TO "IAMR:${API_ROLE_NAME}";
GRANT SELECT ON ALL TABLES IN SCHEMA ${SCHEMA} TO "IAMR:${API_ROLE_NAME}";
ALTER DEFAULT PRIVILEGES IN SCHEMA ${SCHEMA}
    GRANT SELECT ON TABLES TO "IAMR:${API_ROLE_NAME}";

-- Confirm the table exists with the expected shape. ordinal_position is the
-- thing to read: it is what COPY matches against.
SELECT ordinal_position, column_name, data_type
FROM information_schema.columns
WHERE table_schema = '${SCHEMA}' AND table_name = 'macro_conditions'
ORDER BY ordinal_position;
