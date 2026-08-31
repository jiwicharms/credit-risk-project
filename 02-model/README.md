# 02-model

Builds `model_input` from `macro_conditions` and trains `credit_growth_xgb`,
which answers both research questions on its own.

## Run in order

```bash
source 00-setup/env.sh
```

Then in Query Editor v2 (or via a runner that substitutes `${SCHEMA}`,
`${REDSHIFT_IAM_ROLE}`, `${S3_BUCKET}` from your environment):

1. **`sql/01_model_input.sql`** — creates the view, then three validation
   queries. Run all three and check the first returns `0` before continuing
   — that query is the only thing that actually distinguishes a lead target
   from a lag; row count and spread look identical either way.

2. **`sql/02_create_model.sql`** — one `CREATE MODEL` statement,
   `credit_growth_xgb` (fixed XGBoost, `AUTO OFF`). Returns as soon as the
   training data is exported to S3, then trains 20-40 min in the background.
   Poll with `SHOW MODEL credit_risk_prod.credit_growth_xgb;` until
   `Model State` reads `READY`.

3. **`sql/03_explain.sql`** — run once the model is `READY`. Produces the
   next-month prediction for the Immediate question, and `explain_model()`
   plus a correlation-by-regime breakdown for the Predictive question.

## One model, not two

An earlier version of this stage also trained a second model
(`credit_growth_auto`, via SageMaker Autopilot) with explicit
regime-interaction features, specifically to answer whether predictors
matter differently in expansions versus recessions. That turned out to be
unnecessary:

- `EXPLAIN_MODEL` supports `AUTO OFF` XGBoost models directly, so feature
  importance for "greatest predictors" doesn't need Autopilot at all.
- The correlation-by-regime query splits the sample by `recession_flag` and
  measures each predictor's association with the target within each
  subsample directly — it answers "does it differ" without needing an
  interaction term or a second model.

If you find a copy of the old two-model version, check whether
`credit_growth_auto` was ever created before discarding it:

```sql
SHOW MODEL credit_risk_prod.credit_growth_auto;
```

If it returns a real model rather than "not found," drop it — Autopilot
bills for training time whether or not the result gets used:

```sql
DROP MODEL credit_risk_prod.credit_growth_auto;
```

## SageMaker Clarify is closed to new customers

`EXPLAIN_MODEL` calls SageMaker Clarify under the hood, and AWS closed
Clarify to new customers in 2026 as part of a broader service consolidation.
A workgroup provisioned fresh gets `ValidationException: SageMaker Clarify
processing is in maintenance mode`. This is permanent -- retrying or waiting
does not help.

`03_explain.sql` works around it without any new AWS access: it calls the
already-working `predict_credit_growth()` repeatedly, holding one feature at
its sample mean (or, for the binary `recession_flag`, toggling 0 vs 1) and
measuring how much the prediction shifts on average. A large shift means the
model relies on that feature heavily; a small one means it barely matters.
Run separately within each regime, the same measure gives a model-based
answer to "does it differ" -- using the trained model's actual behavior,
not just correlation.

This is a legitimate sensitivity measure but not identical to what Clarify
would have produced: Clarify uses Shapley values, which account for feature
interactions; holding one feature at a time does not. Report it as
single-feature sensitivity, not as SHAP importance, and note in the writeup
that Clarify was unavailable and why.

## Three things Redshift ML required that the docs do not make obvious

Found by running `02_create_model.sql` against a live workgroup, not by
reading ahead:

- **`FUNCTION` cannot be schema-qualified.** `CREATE MODEL ${SCHEMA}.name` and
  `FROM ${SCHEMA}.table` both accept a dot; `FUNCTION` does not, and fails
  with a syntax error pointing at the dot. `predict_credit_growth` is
  created unqualified — check where it actually landed before calling it:
  `SELECT routine_schema, routine_name FROM information_schema.routines
  WHERE routine_name = 'predict_credit_growth';`

- **`MODEL_TYPE XGBOOST` rejects `PROBLEM_TYPE`.** XGBoost infers regression
  vs. classification from `OBJECTIVE` instead. `PROBLEM_TYPE` is only
  relevant for `AUTO ON` (Autopilot) models.

- **`AUTO OFF` requires `PREPROCESSORS` explicitly** — there is no default.
  `PREPROCESSORS 'none'` here is a required declaration, not a placeholder:
  every feature is already hand-derived in `model_input`, so there is
  nothing left for Redshift ML to transform.

## Why the view has more than the raw columns

**Immediate** ("next month") is answered by the target column: `LEAD`, not
`LAG`. Row *t* pairs this month's conditions with the change into *next*
month.

**Predictive** ("does it differ by regime") no longer needs the
`*_x_recession` interaction columns from an earlier draft of this view —
correlation-by-regime answers it directly. They stay in `model_input` since
they cost nothing to compute and remain available if a future model wants
them, but `credit_growth_xgb` does not train on them.

Momentum (`growth_lag1`) and first differences (`d_unemployment`, etc.) are
included because the target is a rate of change while the raw features are
mostly levels.
