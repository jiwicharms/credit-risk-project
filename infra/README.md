# One-time setup for the CI/CD workflow

The workflow in `.github/workflows/ci-cd.yml` needs three things that are
not part of the code: a dedicated IAM user for GitHub to authenticate as,
two repo secrets, two repo variables, and one file that must be committed
rather than gitignored. None of this repeats automatically -- do it once.

## 1. A dedicated IAM user for CI

Do not reuse your own AWS credentials here. A separate user means the blast
radius of a leaked GitHub secret is "can deploy this one app," not "has your
account."

```bash
aws iam create-user --user-name github-actions-credit-risk-api

aws iam attach-user-policy --user-name github-actions-credit-risk-api \
  --policy-arn arn:aws:iam::aws:policy/AdministratorAccess-AWSElasticBeanstalk
```

That managed policy name is current as of 2026 -- AWS retired the older
`AWSElasticBeanstalkFullAccess` in favor of it. `eb deploy` touches EC2,
Auto Scaling, the load balancer, S3, and CloudWatch Logs under the hood, so
a hand-rolled narrow policy risks silently missing one of those and failing
mid-deploy with a confusing error -- the AWS-maintained policy is the safer
choice specifically because it is maintained *by* the team that knows what
EB actually needs internally.

```bash
aws iam create-access-key --user-name github-actions-credit-risk-api
```

Copy the `AccessKeyId` and `SecretAccessKey` from the output. This is the
only time the secret key is shown -- if you lose it, delete the key and
create a new one rather than trying to recover it.

## 2. Add them as GitHub secrets

Repo -> Settings -> Secrets and variables -> Actions -> **Secrets** tab:

| Name | Value |
|---|---|
| `AWS_ACCESS_KEY_ID` | from step 1 |
| `AWS_SECRET_ACCESS_KEY` | from step 1 |

## 3. Add two repo variables

Same page, **Variables** tab (not Secrets -- these are not sensitive, and
variables show up in workflow logs for easier debugging, which secrets
deliberately do not):

| Name | Value |
|---|---|
| `AWS_REGION` | `us-east-1` (or your actual region) |
| `EB_URL` | `http://credit-risk-prod.eba-mymkedgx.us-east-1.elasticbeanstalk.com` -- your real CNAME from `eb status` |

## 4. Commit .elasticbeanstalk/config.yml

`eb deploy` in the workflow has no application or environment name
hardcoded anywhere -- it reads both from this file, the same way your local
`eb deploy` already does. If it is gitignored, the workflow has nothing to
deploy to and fails immediately with a clear error, not a wrong deploy.

```bash
cd 03-api
git check-ignore -v .elasticbeanstalk/config.yml
```

If that prints a match, remove the blanket `.elasticbeanstalk/` rule from
`.gitignore` and replace it with:

```
.elasticbeanstalk/
!.elasticbeanstalk/config.yml
```

This file contains an application name, an environment name, and a region
-- no credentials, safe to commit.

```bash
git add .elasticbeanstalk/config.yml
git commit -m "Commit EB config so CI can deploy non-interactively"
```

## What "continuous" actually means here

**Continuous integration** is the `test` and `build` jobs -- they run on
every push and every pull request, main or any other branch. A broken
change gets caught in the PR, before it reaches main, not after.

**Continuous deployment** is the `deploy` job -- it only runs after both of
those pass, and only for a genuine push to `main`. Merge a PR and the new
version reaches the live Elastic Beanstalk environment with no manual
`eb deploy` from a laptop. The smoke test at the end of that job checks the
container actually came up healthy after the deploy, not just that AWS
accepted the new version -- those are different things, and this project
has already hit the gap between them once, with the missing `MODEL` grant.

## What this deliberately does not do

Long-lived access keys in GitHub secrets are the pragmatic choice for a
course deliverable, not the production-grade one. The stronger version uses
GitHub's OIDC provider so GitHub authenticates to AWS by proving its
identity per-run, with no stored key at all -- `aws-actions/configure-aws-credentials`
supports this via `role-to-assume` instead of access keys. That requires a
one-time IAM OIDC identity provider and a trust policy scoped to this repo,
which is real setup on its own and is not part of this stage. Worth doing
before this ever handles anything beyond a course project.
