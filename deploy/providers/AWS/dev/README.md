# Dev-account Terraform root

This directory holds the Terraform stack for the **dev AWS account**. It deploys only the services that cannot reasonably run on a developer workstation:

- **Cognito** — user pool, hosted-UI domain, app client, seed admin/researcher users
- **SES** — verified sender identity and the three FLIP transactional email templates

Everything else (VPC, EC2, RDS, ALB, NLB, Route53, ACM, S3, IAM, CloudWatch) is intentionally **not** part of this stack; local development runs those services via Docker Compose in this repository's `deploy/` root compose files. The prod/stag stack at `deploy/providers/AWS/` is the source of truth for every non-dev environment.

The Cognito and SES resource definitions are shared with the prod stack via the modules under `deploy/providers/AWS/modules/{cognito,ses}/`, so any change to either service lands in both environments from the same code.

## Prerequisites

1. An AWS SSO profile for the FLIP dev AWS account configured via `aws configure sso`. The profile name must match the `AWS_PROFILE` value in your `.env.development`.
2. A Terraform state bucket reachable from the dev account. Either (a) a bucket in the dev account itself or (b) the shared state bucket, accessible from the dev profile. The state **key** is hard-coded to `flip/dev/terraform.tfstate`; only the **bucket** is passed at init time via `DEV_STATE_BUCKET` (or `STATE_BUCKET` as a fallback).
3. A populated `.env.development` at the repo root. This is the same file the local Docker Compose dev stack uses — no second env file to maintain.

### Variables read from `.env.development`

| Variable | Used for |
| --- | --- |
| `AWS_PROFILE` | dev SSO profile; also guarded against prod/stag account IDs |
| `AWS_REGION` | region for the dev Cognito + SES resources |
| `SES_VERIFIED_EMAIL` | SES sender identity; also defaults the seed admin email |
| `ADMIN_USER_PASSWORD` | initial password for the seed admin (and researcher, if set) |
| `DEV_STATE_BUCKET` (or `STATE_BUCKET`) | S3 bucket for `flip/dev/terraform.tfstate` |
| `flip_cognito_admin_email` (optional) | overrides the seed admin email if you want it distinct from `SES_VERIFIED_EMAIL` |
| `flip_cognito_researcher_email` (optional) | set to create a second seed user; leave unset to skip |

`.env.development.example` already declares most of these; add whatever's missing. The file is git-ignored.

## Usage

All commands can be run either from this directory directly, or via the parent `deploy/providers/AWS/Makefile` using the `dev-` prefix. The parent delegation skips the prod/stag profile guard so it won't fight with your dev `AWS_PROFILE`.

```bash
# From deploy/providers/AWS/
make dev-init      # one-time, or after backend config changes
make dev-plan      # preview
make dev-apply     # deploy
make dev-status    # terraform state list
make dev-destroy   # refused while prevent_destroy is set

# Equivalently, from deploy/providers/AWS/dev/
make init
make plan
make apply
make status
make destroy
```

## First-time setup: import the existing manual Cognito pool

The dev Cognito pool, domain, client and seed users already exist in the dev account because they were created manually before this stack existed. Running `make dev-apply` without importing those resources first would fail (Cognito pool names must be unique) or — worse — create parallel resources and leave the manual ones orphaned.

### 1. Collect the identifiers

From the AWS console (or CLI) in the dev account, note:

- **User pool ID** (format `<region>_XXXXXXXXX`, e.g. `eu-west-2_AbC123XyZ`)
- **App client ID** (26-char alphanumeric, e.g. `6aXXX...`)
- **Hosted-UI domain prefix** (the 8-char random string in `<prefix>.auth.<region>.amazoncognito.com`)

The seed user identifiers are their email addresses (because the pool uses `username_attributes = ["email"]`).

### 2. `make dev-init`

```bash
cd deploy/providers/AWS
make dev-init
```

This downloads the providers and wires up the S3 backend at key `flip/dev/terraform.tfstate`.

### 3. `terraform import` each resource

Run these from `deploy/providers/AWS/dev/` (direct `terraform` calls; no parent-Makefile wrapper for `import`):

```bash
cd deploy/providers/AWS/dev

# User pool
terraform import module.cognito.aws_cognito_user_pool.flip_user_pool <user_pool_id>

# Hosted-UI domain (import by the domain prefix string)
terraform import module.cognito.aws_cognito_user_pool_domain.main <domain_prefix>

# App client: import by "<user_pool_id>/<client_id>"
terraform import module.cognito.aws_cognito_user_pool_client.client <user_pool_id>/<client_id>

# Seed admin user: import by "<user_pool_id>/<username>"
terraform import module.cognito.aws_cognito_user.admin_user <user_pool_id>/<admin_email>

# Seed researcher user (skip if not present in the manual pool)
terraform import 'module.cognito.aws_cognito_user.researcher_user[0]' <user_pool_id>/<researcher_email>
```

The `random_string.cognito_domain` resource has no AWS analogue to import from — it just records the eight-character prefix Terraform generated. After importing `aws_cognito_user_pool_domain.main`, run a plan; Terraform will propose creating the `random_string` to match the imported domain value, which is a no-op at the AWS level. Accept it.

### 4. Import the SES resources

```bash
# Verified sender identity: import by the email address
terraform import module.ses.aws_ses_email_identity.flip_sender <sender_email>

# Transactional templates: import by template name
terraform import module.ses.aws_ses_template.flip_access_request flip-access-request
terraform import module.ses.aws_ses_template.flip_xnat_credentials flip-xnat-credentials
terraform import module.ses.aws_ses_template.flip_xnat_added_to_project flip-xnat-added-to-project
```

### 5. `make dev-plan` and close the loop

```bash
cd deploy/providers/AWS
make dev-plan
```

The plan output should show **no destructive changes**. Likely diffs, all safe to apply in-place:

- **In-place updates** (`~` prefix): expected if attributes drifted — for example, MFA mode if the manual pool predates the MFA commit. Accept with `make dev-apply`.
- **Destroy + recreate** (`-/+` prefix): an immutable attribute disagrees with the module. Investigate before applying; do NOT `apply` unless intentional.
- **Additions** (`+` prefix) of `random_string.cognito_domain`: expected once.

Once the plan is clean:

```bash
make dev-apply
```

## Day-to-day use

```bash
make dev-plan      # preview changes
make dev-apply     # deploy
make dev-status    # list resources under terraform management
make dev-destroy   # NB: prevent_destroy will refuse this
```

To force a destroy (e.g. to rebuild the dev pool from scratch), remove the `prevent_destroy` lifecycle blocks in the shared modules **on a throwaway branch**, or `terraform state rm` each resource and delete them manually in the console. Do not remove `prevent_destroy` on the main branch — it's the last line of defence for the prod pool, which uses the same module.

## Relationship to the prod/stag stack

- `deploy/providers/AWS/` — prod + stag (VPC, EC2, RDS, ALB, NLB, ACM, S3, IAM, and Cognito + SES via modules)
- `deploy/providers/AWS/dev/` — **this directory**, only Cognito + SES via the same modules
- `deploy/providers/AWS/modules/{cognito,ses}/` — single source of truth for both envs

A change to the Cognito config (token lifetimes, MFA mode, email templates) goes in the module and rolls out to both environments via each stack's own `apply`. A change that should land in only one environment goes in that stack's root (via module input variables).
