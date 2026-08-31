#!/usr/bin/env bash
# 00-setup/create_schema.sh — create the schema, table and grants.
#
#   source 00-setup/env.sh
#   ./00-setup/create_schema.sh
#
# Runs sql/01_schema.sql through the Redshift Data API, one statement at a
# time, substituting ${SCHEMA} and ${API_ROLE_NAME} from the environment.

set -euo pipefail

: "${REDSHIFT_WORKGROUP:?source 00-setup/env.sh first}"
: "${REDSHIFT_DATABASE:?source 00-setup/env.sh first}"
: "${REDSHIFT_SCHEMA:?source 00-setup/env.sh first}"

API_ROLE_NAME="${API_ROLE_NAME:-aws-elasticbeanstalk-ec2-role}"
SQL_FILE="$(cd "$(dirname "$0")" && pwd)/sql/01_schema.sql"

echo "Creating ${REDSHIFT_SCHEMA} in ${REDSHIFT_WORKGROUP}/${REDSHIFT_DATABASE}"

run_statement() {
  local sql="$1" label sid status
  label="$(echo "$sql" | grep -vE '^\s*--' | grep -v '^\s*$' | head -1 | cut -c1-60)"

  sid="$(aws redshift-data execute-statement \
    --workgroup-name "$REDSHIFT_WORKGROUP" \
    --database "$REDSHIFT_DATABASE" \
    --region "$AWS_REGION" \
    --sql "$sql" --query Id --output text)"

  while true; do
    status="$(aws redshift-data describe-statement --id "$sid" \
      --region "$AWS_REGION" --query Status --output text)"
    case "$status" in
      FINISHED) echo "  ok    ${label}"; return 0 ;;
      FAILED|ABORTED)
        echo "  FAIL  ${label}" >&2
        aws redshift-data describe-statement --id "$sid" --region "$AWS_REGION" \
          --query Error --output text >&2
        return 1 ;;
    esac
    sleep 1
  done
}

# Split on semicolons at end of line. The DDL contains no semicolons inside
# string literals, so this is safe here — do not reuse it for the COPY files,
# which have S3 URIs and ARNs in quotes.
statement=""
while IFS= read -r line; do
  expanded="${line//\$\{SCHEMA\}/$REDSHIFT_SCHEMA}"
  expanded="${expanded//\$\{API_ROLE_NAME\}/$API_ROLE_NAME}"
  statement+="${expanded}"$'\n'
  if [[ "$expanded" =~ \;[[:space:]]*$ ]]; then
    if echo "$statement" | grep -qvE '^\s*(--.*)?$'; then
      run_statement "$statement" || exit 1
    fi
    statement=""
  fi
done < "$SQL_FILE"

echo ""
echo "Schema ready. Next: ./00-setup/verify.sh"
