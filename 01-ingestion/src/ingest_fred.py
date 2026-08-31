"""
ingest_fred.py

Ingests macroeconomic and consumer credit series from FRED into AWS.

    FRED API  ->  local CSV  ->  S3 (raw landing)  ->  Redshift (COPY)

"""

import argparse
import logging
import os
import sys
import time
from functools import reduce

import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest_fred")

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# FRED series id -> warehouse column name.
SERIES = {
    "UNRATE": "unemployment_rate",
    "GDPC1": "real_gdp",
    "FEDFUNDS": "fed_funds_rate",
    "CPIAUCSL": "cpi",
    "UMCSENT": "consumer_sentiment",
    "USREC": "recession_flag",
    "REVOLSL": "revolving_credit",
    "DRCCLACBS": "cc_delinquency_rate",
    "CORCCACBS": "cc_chargeoff_rate",
}

QUARTERLY = {"real_gdp", "cc_delinquency_rate", "cc_chargeoff_rate",
             "consumer_sentiment"}
CREDIT_CARD_COLS = ["cc_delinquency_rate", "cc_chargeoff_rate"]

FETCH_START = "1960-01-01"

REVOLSL_BREAKS = ["1971-01-01", "1976-10-01", "1977-01-01"]
TRAINING_START = "1977-02-01"

LOCAL_CSV = "data/processed/macro_credit_conditions.csv"
S3_KEY = "fred/macro_credit_conditions.csv"
TABLE = "macro_conditions"

COLUMNS = [
    "date", "unemployment_rate", "real_gdp", "gdp_growth", "fed_funds_rate",
    "cpi", "cpi_yoy", "consumer_sentiment", "recession_flag",
    "revolving_credit", "cc_delinquency_rate", "cc_chargeoff_rate",
]


# ============================================================ fetch

def fetch_series(series_id: str, api_key: str, start: str = FETCH_START,
                 vintage: str = "", retries: int = 3) -> pd.DataFrame:
    col = SERIES[series_id]
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
    }
    if vintage:
        params["realtime_start"] = vintage
        params["realtime_end"] = vintage

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(FRED_BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            break
        except requests.RequestException as e:
            if attempt == retries:
                raise
            wait = 2 ** attempt
            log.warning("  %s failed (%s), retrying in %ds", series_id, e, wait)
            time.sleep(wait)

    obs = resp.json().get("observations", [])
    if not obs:
        raise ValueError(f"{series_id} returned no observations")

    df = pd.DataFrame(obs)[["date", "value"]]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    before = len(df)
    df = df.rename(columns={"value": col}).dropna(subset=[col])

    skipped = before - len(df)
    log.info("  %-10s %-22s %5d obs  (%s to %s)%s", series_id, col, len(df),
             df["date"].min().date(), df["date"].max().date(),
             f"  [{skipped} missing]" if skipped else "")
    return df


# ============================================================ transform

def build_dataset(frames: dict, start: str = TRAINING_START,
                  credit_card_policy: str = "include") -> pd.DataFrame:
    """Merge series onto a monthly grain and derive the computed columns."""
    gdp = frames["real_gdp"].sort_values("date").copy()
    gdp["gdp_growth"] = ((1.0 + gdp["real_gdp"].pct_change()) ** 4 - 1.0) * 100.0
    frames["real_gdp"] = gdp

    merged = reduce(
        lambda a, b: pd.merge(a, b, on="date", how="outer"),
        [f.sort_values("date") for f in frames.values()],
    ).sort_values("date").reset_index(drop=True)

    merged = merged.set_index("date").resample("MS").first()

    for col in QUARTERLY | {"gdp_growth"}:
        if col in merged.columns:
            merged[col] = merged[col].ffill()

    merged["cpi_yoy"] = merged["cpi"].pct_change(periods=12) * 100.0

    merged = merged.reset_index()

    required = ["revolving_credit", "cpi_yoy", "unemployment_rate",
                "consumer_sentiment", "gdp_growth", "fed_funds_rate"]
    merged = merged.dropna(subset=required)

    merged["recession_flag"] = merged["recession_flag"].fillna(0).astype(int)

    gaps = merged["date"].diff().dt.days
    if (gaps > 40).any():
        first_hole = merged.loc[gaps > 40, "date"].min()
        before = len(merged)
        merged = merged[merged["date"] < first_hole]
        log.warning("Truncating at %s — %d rows dropped after a break in the "
                    "monthly sequence (%s missing). Publication gap, not a "
                    "pipeline error.",
                    merged["date"].max().date(), before - len(merged),
                    first_hole.date())

    if start:
        cutoff = pd.Timestamp(start)
        kept = merged["date"] >= cutoff
        if not kept.all():
            broken = [b for b in REVOLSL_BREAKS if pd.Timestamp(b) < cutoff]
            log.info("Starting at %s — %d earlier rows dropped, covering %d "
                     "REVOLSL definitional break(s). Pass --start 1968-01-01 "
                     "to keep them.", start, (~kept).sum(), len(broken))
            merged = merged[kept]




    n_null = merged[CREDIT_CARD_COLS].isna().any(axis=1).sum()
    if n_null:
        first_complete = merged.loc[
            merged[CREDIT_CARD_COLS].notna().all(axis=1), "date"].min()
        if credit_card_policy == "exclude":
            merged = merged.drop(columns=CREDIT_CARD_COLS)
            log.info("Dropped %s — null in %d of %d rows before %s.",
                     ", ".join(CREDIT_CARD_COLS), n_null, len(merged),
                     first_complete.date())
        elif credit_card_policy == "complete":
            merged = merged[merged["date"] >= first_complete]
            log.info("Restricted to %s onward — %d rows dropped so %s are "
                     "complete.", first_complete.date(), n_null,
                     " and ".join(CREDIT_CARD_COLS))
        else:
            log.warning(
                "%d of %d rows have null %s (before %s). Kept, and they will "
                "load as NULL. Exclude them from CREATE MODEL or use "
                "--credit-card complete before training.",
                n_null, len(merged), "/".join(CREDIT_CARD_COLS),
                first_complete.date())

    merged["date"] = merged["date"].dt.strftime("%Y-%m-%d")
    columns = [c for c in COLUMNS if c in merged.columns]
    out = merged[columns].copy()

    log.info("Built dataset: %d rows x %d cols (%s to %s)",
             len(out), len(out.columns), out["date"].iloc[0], out["date"].iloc[-1])
    return out


def validate(df: pd.DataFrame) -> None:
    """Fail loudly before anything reaches AWS."""
    problems = []


    minimum = 550
    if len(df) < minimum:
        problems.append(f"only {len(df)} rows — expected at least {minimum}")
    if df["date"].duplicated().any():
        problems.append("duplicate dates")
    if not df["recession_flag"].isin([0, 1]).all():
        problems.append("recession_flag outside {0,1}")
    if (df["revolving_credit"] <= 0).any():
        problems.append("non-positive revolving_credit")
    if df["unemployment_rate"].max() > 30 or df["unemployment_rate"].min() < 0:
        problems.append("unemployment_rate out of plausible range")

    gaps = pd.to_datetime(df["date"]).diff().dt.days.dropna()
    if (gaps > 40).any():
        problems.append(f"{(gaps > 40).sum()} gaps larger than one month")


    if df["gdp_growth"].nunique() < 4:
        problems.append("gdp_growth is nearly constant — derived after the fill?")


    always_complete = [c for c in df.columns if c not in CREDIT_CARD_COLS]
    nulls = df[always_complete].isna().sum()
    if nulls.any():
        problems.append(f"nulls in required columns: {nulls[nulls > 0].to_dict()}")

    for col in CREDIT_CARD_COLS:
        if col in df.columns and df[col].isna().any():
            span = df.loc[df[col].isna(), "date"]
            log.info("NOTE: %s null for %d rows (%s to %s) — expected, the "
                     "series does not exist before 1991.",
                     col, df[col].isna().sum(), span.min(), span.max())

    if problems:
        for p in problems:
            log.error("VALIDATION: %s", p)
        raise ValueError("dataset failed validation — not uploading")

    log.info("Validation passed: %d rows, no gaps, ranges plausible", len(df))


# ============================================================ ml-ready export

def write_ml_ready(df: pd.DataFrame, out_dir: str, test_fraction: float = 0.2,
                   headerless: bool = True) -> None:

    frame = df.copy()

    frame["pct_change_next_month"] = (
        frame["revolving_credit"].shift(-1) / frame["revolving_credit"] - 1.0
    ) * 100.0

    before = len(frame)
    frame = frame.drop(columns=["date"]).dropna()
    if before - len(frame):
        log.info("  dropped %d incomplete rows (pre-1991 credit-card nulls and "
                 "the final month, which has no t+1)", before - len(frame))

    features = [c for c in frame.columns if c != "pct_change_next_month"]
    frame = frame[["pct_change_next_month"] + features]

    split = int(len(frame) * (1.0 - test_fraction))
    train, test = frame.iloc[:split], frame.iloc[split:]

    os.makedirs(out_dir, exist_ok=True)
    kwargs = {"index": False, "header": not headerless}
    train.to_csv(os.path.join(out_dir, "train.csv"), **kwargs)
    test.to_csv(os.path.join(out_dir, "test.csv"), **kwargs)

    log.info("  train %d rows, test %d rows, feature_dim=%d",
             len(train), len(test), len(features))
    log.info("  wrote %s/train.csv and test.csv (target in column 0, %s)",
             out_dir, "no header" if headerless else "with header")

    # The extrapolation trap, checked rather than assumed.
    tr, te = train["pct_change_next_month"], test["pct_change_next_month"]
    if te.min() < tr.min() or te.max() > tr.max():
        log.warning("  test target range [%.2f, %.2f] extends beyond train "
                    "[%.2f, %.2f] — extrapolation needed at the tails",
                    te.min(), te.max(), tr.min(), tr.max())
    else:
        log.info("  test target range sits inside train range — no "
                 "extrapolation required")

    train_rec = int(train.get("recession_flag", pd.Series(dtype=int)).sum())
    test_rec = int(test.get("recession_flag", pd.Series(dtype=int)).sum())
    log.info("  recession months: %d train, %d test", train_rec, test_rec)
    if test_rec < 5:
        log.warning("  only %d recession months in test — RQ2's regime "
                    "comparison rests on a very small sample there", test_rec)


# ============================================================ load

def upload_to_s3(path: str, bucket: str, key: str) -> str:
    import boto3
    s3 = boto3.client("s3")
    s3.upload_file(path, bucket, key, ExtraArgs={"ServerSideEncryption": "AES256"})
    uri = f"s3://{bucket}/{key}"
    log.info("Uploaded %s", uri)
    return uri


def copy_to_redshift(s3_uri: str, workgroup: str, database: str,
                     schema: str, iam_role: str) -> None:
    import boto3
    rs = boto3.client("redshift-data")


    statements = [
        f"TRUNCATE TABLE {schema}.{TABLE};",
        f"""COPY {schema}.{TABLE}
            FROM '{s3_uri}'
            IAM_ROLE '{iam_role}'
            CSV IGNOREHEADER 1
            DATEFORMAT 'YYYY-MM-DD'
            BLANKSASNULL EMPTYASNULL
            REGION '{os.getenv("AWS_REGION", "us-east-1")}';""",
    ]

    for sql in statements:
        label = sql.strip().split()[0]
        sid = rs.execute_statement(
            WorkgroupName=workgroup, Database=database, Sql=sql
        )["Id"]

        while True:
            desc = rs.describe_statement(Id=sid)
            if desc["Status"] == "FINISHED":
                break
            if desc["Status"] in ("FAILED", "ABORTED"):
                log.error("%s failed: %s", label, desc.get("Error"))
             
                log.error("Run in Query Editor v2 for detail:")
                log.error("  SELECT * FROM sys_load_error_detail "
                          "ORDER BY start_time DESC LIMIT 5;")
                raise RuntimeError(f"{label} failed")
            time.sleep(0.5)
        log.info("%s ok", label)

    sid = rs.execute_statement(
        WorkgroupName=workgroup, Database=database,
        Sql=f"SELECT COUNT(*), MIN(date), MAX(date) FROM {schema}.{TABLE};",
    )["Id"]
    while rs.describe_statement(Id=sid)["Status"] not in ("FINISHED", "FAILED", "ABORTED"):
        time.sleep(0.3)
    rec = rs.get_statement_result(Id=sid)["Records"][0]
    log.info("Loaded: %s rows, %s to %s",
             rec[0]["longValue"], rec[1]["stringValue"], rec[2]["stringValue"])


# ============================================================ main

def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest FRED series into Redshift")
    ap.add_argument("--local-only", action="store_true",
                    help="fetch and transform only; touch no AWS resource")
    ap.add_argument("--skip-fetch", action="store_true",
                    help="reuse the existing CSV instead of calling FRED")
    ap.add_argument("--csv", default=LOCAL_CSV)
    ap.add_argument("--start", default=TRAINING_START,
                    help="first month to keep. Default cuts REVOLSL's pre-1977 "
                         "definitional breaks; pass 1968-01-01 for full history.")
    ap.add_argument("--credit-card", choices=["include", "exclude", "complete"],
                    default="include",
                    help="how to handle cc_* nulls before 1991")
    ap.add_argument("--vintage", default=os.getenv("FRED_VINTAGE", ""),
                    help="pin FRED to a YYYY-MM-DD vintage for reproducibility")
    ap.add_argument("--ml-ready", action="store_true",
                    help="also write SageMaker train/test CSVs")
    ap.add_argument("--ml-dir", default="data/ml")
    args = ap.parse_args()

    if args.skip_fetch:
        if not os.path.exists(args.csv):
            log.error("%s not found", args.csv)
            return 1
        df = pd.read_csv(args.csv)
        log.info("Loaded %d rows from %s", len(df), args.csv)
    else:
        api_key = os.getenv("FRED_API_KEY")
        if not api_key:
            log.error("FRED_API_KEY not set. Free key: "
                      "https://fredaccount.stlouisfed.org/apikeys")
            return 1

        if args.vintage:
            log.info("Fetching %d series from FRED, pinned to the %s vintage...",
                     len(SERIES), args.vintage)
        else:
            log.info("Fetching %d series from FRED (latest revision — set "
                     "FRED_VINTAGE to make this reproducible)...", len(SERIES))

        frames = {}
        for sid in SERIES:
            frames[SERIES[sid]] = fetch_series(sid, api_key, vintage=args.vintage)
            time.sleep(0.15)  # courtesy pacing; FRED allows 120 req/min

        df = build_dataset(frames, start=args.start,
                           credit_card_policy=args.credit_card)
        os.makedirs(os.path.dirname(args.csv), exist_ok=True)
        df.to_csv(args.csv, index=False)
        log.info("Wrote %s", args.csv)

    validate(df)

    if args.ml_ready:
        log.info("Writing SageMaker-ready splits...")
        write_ml_ready(df, args.ml_dir)

    if args.local_only:
        log.info("--local-only: stopping before AWS")
        print()
        print(df.head(3).to_string(index=False))
        print("...")
        print(df.tail(3).to_string(index=False))
        return 0

    bucket = os.getenv("S3_BUCKET")
    workgroup = os.getenv("REDSHIFT_WORKGROUP", "credit-risk-wg")
    database = os.getenv("REDSHIFT_DATABASE", "dev")
    schema = os.getenv("REDSHIFT_SCHEMA", "credit_risk_prod")
    iam_role = os.getenv("REDSHIFT_IAM_ROLE", "default")

    if not bucket:
        log.error("S3_BUCKET not set")
        return 1

    uri = upload_to_s3(args.csv, bucket, S3_KEY)
    copy_to_redshift(uri, workgroup, database, schema, iam_role)
    log.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
