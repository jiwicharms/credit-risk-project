# 00-setup

Pipeline creation.

## First run

```bash
cp .env.example .env      # then add your FRED_API_KEY
source 00-setup/env.sh
./00-setup/provision.sh
source 00-setup/env.sh
./00-setup/create_schema.sh
./00-setup/verify.sh
```

## File info

| File | Purpose |
|---|---|
| `env.sh` | Loads `.env`, derives the bucket name and role ARN from your AWS account, and fails early on anything missing. |
| `cloudformation.yaml` | |
| `provision.sh` | |
| `create_schema.sh` | Creates the schema, `macro_conditions`, and the API grants |
| `verify.sh` | Checks each layer separately and names the fix for whatever failed |
| `teardown.sh` | Deletes everything. Run when you're done. |

## API Key & S3

`FRED_API_KEY`, free from [fredaccount.stlouisfed.org/apikeys](https://fredaccount.stlouisfed.org/apikeys).

Everything else has a default or is derived. The bucket name is
`${PROJECT_NAME}-${ACCOUNT_ID}-${REGION}`, which is globally unique without
anyone inventing one — so two people can run this repo without colliding.

