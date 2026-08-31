#!/usr/bin/env bash
# 00-setup/teardown.sh — delete every AWS resource this project created.
#
#   source 00-setup/env.sh
#   ./00-setup/teardown.sh
#
# Run this when you are done. An idle Redshift Serverless workgroup is free,
# but leaving one provisioned after a heavy session is the usual way a course
# project produces an unexpected bill.

set -euo pipefail

: "${AWS_REGION:?source 00-setup/env.sh first}"
PROJECT="${PROJECT_NAME:-credit-risk}"
STACK="${PROJECT}-stack"

echo "This deletes the bucket, IAM role, namespace and workgroup for ${STACK}."
printf "Type the project name to confirm [%s]: " "$PROJECT"
read -r confirm
[ "$confirm" = "$PROJECT" ] || { echo "aborted"; exit 1; }

# CloudFormation cannot delete a non-empty versioned bucket, and the resulting
# DELETE_FAILED is easy to misread as a permissions problem.
BUCKET="$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='S3Bucket'].OutputValue" \
  --output text 2>/dev/null || true)"

if [ -n "$BUCKET" ] && [ "$BUCKET" != "None" ]; then
  echo "Emptying s3://${BUCKET} (including old versions)..."
  aws s3 rm "s3://${BUCKET}" --recursive --region "$AWS_REGION" >/dev/null 2>&1 || true
  python3 - "$BUCKET" <<'PY' || true
import sys, boto3
boto3.resource("s3").Bucket(sys.argv[1]).object_versions.delete()
PY
fi

aws cloudformation delete-stack --stack-name "$STACK" --region "$AWS_REGION"
echo "Waiting for deletion..."
aws cloudformation wait stack-delete-complete --stack-name "$STACK" --region "$AWS_REGION"
echo "Done — no further charges from this stack."
