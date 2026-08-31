-- 02-model/sql/02_create_model.sql
--

-- ===========================================================================
-- 1. credit_growth_xgb -- fixed XGBoost, AUTO OFF.
-- ===========================================================================

CREATE MODEL ${SCHEMA}.credit_growth_xgb
FROM (
    SELECT target, unemployment_rate, fed_funds_rate, cpi_yoy, gdp_growth,
           consumer_sentiment, recession_flag, growth_lag1,
           d_unemployment, d_fed_funds, d_sentiment, real_rate
    FROM ${SCHEMA}.model_input
)
TARGET target
FUNCTION predict_credit_growth
IAM_ROLE '${REDSHIFT_IAM_ROLE}'
AUTO OFF
MODEL_TYPE XGBOOST
OBJECTIVE 'reg:squarederror'
PREPROCESSORS 'none'
HYPERPARAMETERS DEFAULT EXCEPT (NUM_ROUND '100')
SETTINGS (
    S3_BUCKET '${S3_BUCKET}',
    MAX_RUNTIME 2400
);


SHOW MODEL ${SCHEMA}.credit_growth_xgb;


