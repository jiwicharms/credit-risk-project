#!/usr/bin/env bash
# 00-setup/verify.sh — confirm every prerequisite before running the pipeline.
#
#   source 00-setup/env.sh
#   ./00-setup/verify.sh
#
# The failures in this stack cascade: a missing trust relationship surfaces as
# a COPY that loads zero rows, and a missing grant surfaces as an API 503 with
# no detail. Each check below reports its own layer.

set -uo pipefail
pass=0; fail=0
ok()   { printf "  [ ok ] %-22s %s\n" "$1" "${2:-}"; pass=$((pass+1)); }
bad()  { printf "  [FAIL] %-22s %s\n" "$1" "${2:-}"; fail=$((fail+1)); }
warn() { printf "  [warn] %-22s %s\n" "$1" "${2:-}"; }

echo ""
[ -n "${AWS_ACCOUNT_ID:-}" ] && ok "environment" "account ${AWS_ACCOUNT_ID}" \
  || { bad "environment" "source 00-setup/env.sh first"; exit 1; }

[ -n "${FRED_API_KEY:-}" ] && ok "fred key" "set" || bad "fred key" "empty in .env"

if aws s3api head-bucket --bucket "$S3_BUCKET" 2>/dev/null; then
  ok "s3 bucket" "$S3_BUCKET"
else
  bad "s3 bucket" "$S3_BUCKET unreachable — run ./00-setup/provision.sh"
fi

# The trust policy, not just the permissions. This is the piece that makes
# COPY fail with a role-assumption error rather than an access-denied one.
trust="$(aws iam get-role --role-name "$REDSHIFT_ROLE_NAME" \
  --query 'Role.AssumeRolePolicyDocument' --output json 2>/dev/null)"
if [ -z "$trust" ]; then
  bad "redshift role" "$REDSHIFT_ROLE_NAME not found"
elif echo "$trust" | grep -q redshift; then
  ok "redshift role" "$REDSHIFT_ROLE_NAME trusts redshift"
else
  bad "redshift role" "does not trust redshift.amazonaws.com — COPY will fail"
fi

sid="$(aws redshift-data execute-statement \
  --workgroup-name "$REDSHIFT_WORKGROUP" --database "$REDSHIFT_DATABASE" \
  --sql "SELECT 1" --query Id --output text 2>/dev/null)"
if [ -z "$sid" ]; then
  bad "redshift data api" "cannot submit — check the workgroup name and region"
else
  for _ in $(seq 1 30); do
    st="$(aws redshift-data describe-statement --id "$sid" --query Status --output text)"
    [ "$st" = "FINISHED" ] && { ok "redshift data api" "reachable"; break; }
    [ "$st" = "FAILED" ] && { bad "redshift data api" "query failed"; break; }
    sleep 1
  done
fi

sid="$(aws redshift-data execute-statement \
  --workgroup-name "$REDSHIFT_WORKGROUP" --database "$REDSHIFT_DATABASE" \
  --sql "SELECT COUNT(*) FROM information_schema.tables
         WHERE table_schema='${REDSHIFT_SCHEMA}' AND table_name='macro_conditions'" \
  --query Id --output text 2>/dev/null)"
if [ -n "$sid" ]; then
  for _ in $(seq 1 30); do
    st="$(aws redshift-data describe-statement --id "$sid" --query Status --output text)"
    [ "$st" = "FINISHED" ] || { sleep 1; continue; }
    n="$(aws redshift-data get-statement-result --id "$sid" \
         --query 'Records[0][0].longValue' --output text)"
    [ "$n" = "1" ] && ok "macro_conditions" "exists in ${REDSHIFT_SCHEMA}" \
      || warn "macro_conditions" "missing — run ./00-setup/create_schema.sh"
    break
  done
fi

echo ""
echo "  ${pass} passed, ${fail} failed"
echo ""
[ "$fail" -eq 0 ] || exit 1
echo "  Ready. Next: python3 01-ingestion/src/ingest_fred.py --local-only"
