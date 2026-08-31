#!/usr/bin/env bash
# 00-setup/provision.sh — create every AWS resource this project needs.
#
#   source 00-setup/env.sh
#   ./00-setup/provision.sh
#
# Idempotent: re-running an unchanged stack reports no updates and exits 0.
# Takes 3-6 minutes, nearly all of it Redshift Serverless.

set -euo pipefail

: "${AWS_ACCOUNT_ID:?source 00-setup/env.sh first}"
: "${AWS_REGION:?source 00-setup/env.sh first}"

PROJECT="${PROJECT_NAME:-credit-risk}"
STACK="${PROJECT}-stack"
TEMPLATE="$(cd "$(dirname "$0")" && pwd)/cloudformation.yaml"

echo "Deploying ${STACK} to account ${AWS_ACCOUNT_ID} (${AWS_REGION})"

# Redshift Serverless needs subnets in three distinct AZs. Take one per AZ
# from the default VPC so the cloner never has to look any of this up.
SUBNETS="$(aws ec2 describe-subnets \
  --filters Name=default-for-az,Values=true \
  --query 'Subnets[].SubnetId' --output text --region "$AWS_REGION" | tr '\t' ',')"

if [ -z "$SUBNETS" ]; then
  echo "No default VPC in ${AWS_REGION}. Create one with:" >&2
  echo "    aws ec2 create-default-vpc --region ${AWS_REGION}" >&2
  exit 1
fi
echo "  subnets: ${SUBNETS}"

# Reuse the existing password on updates rather than rotating it every run.
if aws cloudformation describe-stacks --stack-name "$STACK" \
     --region "$AWS_REGION" >/dev/null 2>&1; then
  PASSWORD_ARG="ParameterKey=AdminPassword,UsePreviousValue=true"
  echo "  stack exists — updating"
else
  # Letters and digits only: Redshift rejects several punctuation characters,
  # and finding that out halfway through stack creation is a slow lesson.
  PASSWORD="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)Aa1"
  PASSWORD_ARG="ParameterKey=AdminPassword,ParameterValue=${PASSWORD}"
  echo "  creating"
fi

set +e
aws cloudformation deploy \
  --stack-name "$STACK" \
  --template-file "$TEMPLATE" \
  --region "$AWS_REGION" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
      "ParameterKey=ProjectName,ParameterValue=${PROJECT}" \
      "ParameterKey=SubnetIds,ParameterValue=\"${SUBNETS}\"" \
      "ParameterKey=RedshiftRoleName,ParameterValue=${REDSHIFT_ROLE_NAME}" \
      "$PASSWORD_ARG"
status=$?
set -e

if [ $status -ne 0 ]; then
  echo ""
  echo "Deploy failed. Most recent failure reason:" >&2
  aws cloudformation describe-stack-events --stack-name "$STACK" \
    --region "$AWS_REGION" \
    --query 'StackEvents[?contains(ResourceStatus,`FAILED`)].[LogicalResourceId,ResourceStatusReason]' \
    --output text 2>/dev/null | head -3 >&2
  echo "" >&2
  echo "If a resource 'already exists', you provisioned it by hand before." >&2
  echo "Either delete it, or set PROJECT_NAME in .env to a different prefix." >&2
  exit 1
fi

echo ""
aws cloudformation describe-stacks --stack-name "$STACK" --region "$AWS_REGION" \
  --query 'Stacks[0].Outputs[].[OutputKey,OutputValue]' --output text \
  | while IFS=$'\t' read -r k v; do printf "  %-20s %s\n" "$k" "$v"; done

echo ""
echo "Next:"
echo "  source 00-setup/env.sh          # picks up the new resources"
echo "  ./00-setup/create_schema.sh     # schema, table, grants"
echo "  ./00-setup/verify.sh            # confirm everything is reachable"
