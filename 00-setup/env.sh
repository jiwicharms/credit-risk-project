#!/usr/bin/env bash
# 00-setup/env.sh — load configuration for every stage.
#
#   source 00-setup/env.sh
#
# Must be sourced, not executed: a subshell's exports die with it.
# Works under both bash and zsh (macOS defaults to zsh).
#
# Derives S3_BUCKET and REDSHIFT_IAM_ROLE from the caller's own AWS account,
# so nothing account-specific is ever committed.

# `return` succeeds only when this file is being sourced. Portable across
# bash and zsh, unlike a BASH_SOURCE comparison -- zsh does not define
# BASH_SOURCE at all, which silently breaks any path logic built on it.
(return 0 2>/dev/null) || {
  echo "Run 'source 00-setup/env.sh', not './00-setup/env.sh'." >&2
  exit 1
}

# Walk up from the working directory looking for the repo root, identified by
# the presence of 00-setup/env.sh. Deriving the location from the script path
# would need BASH_SOURCE (bash) or ${(%):-%x} (zsh); searching upward needs
# neither and additionally lets you source this from a subdirectory.
_root="$PWD"
while [ "$_root" != "/" ] && [ ! -f "$_root/00-setup/env.sh" ]; do
  _root="$(dirname "$_root")"
done

if [ ! -f "$_root/00-setup/env.sh" ]; then
  echo "Could not find the repo root (no 00-setup/env.sh above $PWD)." >&2
  echo "cd to the project directory first." >&2
  unset _root
  return 1
fi

if [ ! -f "$_root/.env" ]; then
  echo "No .env found at $_root/.env. Create one with:" >&2
  echo "    cp .env.example .env" >&2
  echo "Then add your FRED_API_KEY." >&2
  unset _root
  return 1
fi

# set -a exports every assignment; set +a stops. Avoids a python-dotenv
# dependency and keeps .env readable by bash, zsh and the scripts alike.
set -a
# shellcheck disable=SC1091
. "$_root/.env"
set +a

PROJECT_NAME="${PROJECT_NAME:-credit-risk}"
AWS_REGION="${AWS_REGION:-us-east-1}"
REDSHIFT_DATABASE="${REDSHIFT_DATABASE:-dev}"
REDSHIFT_SCHEMA="${REDSHIFT_SCHEMA:-credit_risk_prod}"
REDSHIFT_WORKGROUP="${REDSHIFT_WORKGROUP:-${PROJECT_NAME}-wg}"
REDSHIFT_NAMESPACE="${REDSHIFT_NAMESPACE:-${PROJECT_NAME}-ns}"
REDSHIFT_ROLE_NAME="${REDSHIFT_ROLE_NAME:-RedshiftCreditRiskRole}"
export PROJECT_NAME AWS_REGION REDSHIFT_DATABASE REDSHIFT_SCHEMA \
       REDSHIFT_WORKGROUP REDSHIFT_NAMESPACE REDSHIFT_ROLE_NAME PROJECT_ROOT

PROJECT_ROOT="$_root"
export PROJECT_ROOT
unset _root

if [ -z "${FRED_API_KEY:-}" ]; then
  echo "FRED_API_KEY is empty in .env." >&2
  echo "Free key: https://fredaccount.stlouisfed.org/apikeys" >&2
  return 1
fi

if ! AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text 2>/dev/null)"; then
  echo "No usable AWS credentials. Run 'aws configure'." >&2
  return 1
fi
export AWS_ACCOUNT_ID

# Both derived, never committed. The bucket name is account-scoped because S3
# names are globally unique -- this way no cloner has to invent one, and two
# people can run this repo without colliding.
export S3_BUCKET="${S3_BUCKET:-${PROJECT_NAME}-${AWS_ACCOUNT_ID}-${AWS_REGION}}"
export REDSHIFT_IAM_ROLE="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${REDSHIFT_ROLE_NAME}"

echo "account   ${AWS_ACCOUNT_ID}  (${AWS_REGION})"
echo "bucket    ${S3_BUCKET}"
echo "redshift  ${REDSHIFT_SCHEMA} in ${REDSHIFT_WORKGROUP}/${REDSHIFT_DATABASE}"
