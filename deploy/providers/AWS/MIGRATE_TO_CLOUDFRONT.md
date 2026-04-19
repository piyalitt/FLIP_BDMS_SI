<!--
    Copyright (c) 2026 Guy's and St Thomas' NHS Foundation Trust & King's College London
    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at
        http://www.apache.org/licenses/LICENSE-2.0
    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
-->

# Migrating an Account to CloudFront UI Hosting

This guide covers migrating a FLIP AWS account (stag or prod) from the legacy EC2-ALB UI path to the S3 + CloudFront path. Prod was migrated on 2026-04-19; **stag migration is still pending** at the time of this document.

Once merged, `main` no longer supports the legacy EC2-ALB UI path — this document is the one-shot transition instructions. After running through it on stag, **delete the stag-specific section below** to keep the guide focused on future new accounts (if any).

## What changes

Before:

```text
users → stag.flip.aicentre.co.uk → ALB (HTTPS:443) → flip-ui container on EC2
trusts → stag.flip.aicentre.co.uk/api/...  → ALB (HTTPS:443, /api/* rule) → flip-api on EC2:8080
```

After:

```text
users  → stag.flip.aicentre.co.uk   → CloudFront → S3 (static UI bundle)
users  → stag.flip.aicentre.co.uk/api/... → CloudFront → ALB (HTTP:8080, api-listener) → flip-api
trusts → stag.flip.aicentre.co.uk/api/... → same as above (URL unchanged, CloudFront transparent)
```

The canonical subdomain is untouched from the user/trust perspective — only the traffic path behind it changes.

## Prerequisites

1. AWS SSO logged in against the target account's profile (e.g. `FlipDeveloperAccess-080369786334` for stag, `FlipDeveloperAccess-046651569599` for prod).
2. The merged `aicentre-iac` PR #169 has been applied, granting `acm:*` in `us-east-1` to `FlipDeveloperAccess`. Verify with:
   ```bash
   aws iam get-role-policy \
     --role-name AWSReservedSSO_FlipDeveloperAccess_<suffix> \
     --policy-name AwsSSOInlinePolicy \
     --profile <profile> \
     | jq '.PolicyDocument.Statement[] | select(.Sid == "ACMCertMgmt")'
   # Resource list must include arn:aws:acm:us-east-1:<account-id>:certificate/*
   ```
3. `.env.<env>` populated with:
   ```
   AWS_PROFILE=FlipDeveloperAccess-<account-id>      # must match the Makefile's guard
   FLIP_UI_BUCKET_NAME=flip-ui-<env>                  # globally unique; e.g. flip-ui-stag
   # Everything else (ALB_SUBDOMAIN, FLIP_TFSTATE_BUCKET_NAME, …) unchanged.
   ```
4. A known-good Terraform state for the account. Run `terraform state list | wc -l` — if the count is dramatically lower than prod's (~100+), the state is incomplete and Terraform will plan to *create* live resources (RDS, EC2, VPC, …) from scratch, which is catastrophic. Import the missing resources before proceeding.

## Migration sequence

> ⚠️ **Do not `make apply` if the plan shows > 10 resources to add or any destroys you don't understand.** A plan that wants to create dozens of resources means the TF state is misaligned with the account — stop and fix state first.

### 1. Initialise against the account's state

```bash
cd deploy/providers/AWS
make init PROD=stag   # or PROD=true for prod
```

### 2. Issue ACM certificates (two-phase)

CloudFront viewer cert lives in `us-east-1`; the ALB origin cert lives in `eu-west-2`. Both require DNS validation, so they're a separate first apply:

```bash
make plan-cloudfront-certs PROD=stag
make apply-cloudfront-certs PROD=stag
```

DNS validation typically completes in < 60 s; both certificates reach `ISSUED` before this returns.

### 3. Apply the main CloudFront stack

```bash
make plan PROD=stag
```

Review the plan. Expect **new** resources: CloudFront distribution, S3 UI bucket, OAC, S3 bucket policy, Route53 record for `api.<subdomain>`, additional ALB listener certificate, CloudFront logging bucket.

Also expect **destructive** changes:

- `module.alb.aws_lb_target_group["ec2-instance-ui"]` will be destroyed.
- `module.alb.aws_lb_target_group_attachment["ec2-instance-ui"]` will be destroyed.
- `module.ec2_security_group.aws_security_group_rule.ingress["443"]` will be destroyed.
- `module.alb.aws_lb_listener["https-listener"]` will update in-place (default action `forward → ec2-instance-ui` → `fixed_response 404`).
- `aws_route53_record.alb` will update in-place (alias swings from ALB to CloudFront).

If the plan looks right:

```bash
make apply PROD=stag
```

The moment `aws_route53_record.alb` applies, DNS begins propagating and users start hitting CloudFront. Route53 TTL is 60 s.

### 4. Populate S3 and invalidate CloudFront

```bash
make deploy-ui PROD=stag
```

Builds the UI from the working tree, regenerates `window.js` from `.env.stag` values, syncs to S3, creates a CloudFront `/*` invalidation. Takes 1–3 min.

> **Expected brief outage.** Between step 3 and step 4, `stag.flip.aicentre.co.uk/` returns CloudFront's default S3 404 response until step 4 completes (typically < 3 min). Tell users, or do steps 3 and 4 back-to-back.

### 5. Verify end-to-end

Open `https://stag.flip.aicentre.co.uk/` in a browser. Expect:

- UI loads, Cognito login works.
- Deep links like `/projects/<id>` return the SPA (CloudFront 403/404 → `/index.html` rewrite).
- `curl https://stag.flip.aicentre.co.uk/api/health` returns `{"status":"ok","message":"flip is running"}`.
- A trust host's poller logs show successful task polls against the canonical URL.

If any of these fail:

- Check CloudFront distribution status: `aws cloudfront get-distribution --id <id> --query 'Distribution.Status'` — should be `Deployed`.
- Check CloudFront access logs in `s3://flip-cf-logs-<subdomain>/standard-logs/` (delivery has ~5–15 min latency). Field `x-edge-result-type` + `x-edge-detailed-result-type` identify the root cause of 5xx responses.
- Rollback: there is no built-in rollback flag in `main`. To revert, you'd need to restore the ALB UI target group and flip the A-record manually via AWS console, then re-import state. Avoid this unless absolutely necessary — forward-fix is almost always faster.

## Known issue: CloudFront → ALB `/api/*` origin is HTTP on port 8080

Prod's `/api/*` CloudFront behavior currently uses **HTTP on port 8080** to reach the ALB `api-listener`, not HTTPS on 443. CloudFront-to-ALB TLS handshake consistently produced 502s despite the ALB serving TLS 1.2 cleanly to every other client. HTTP is acceptable interim state because the hop is on AWS's global network; traffic between users and CloudFront is still HTTPS.

Follow-up work (tracked in `cloudfront.tf` comment on `custom_origin_config`): inspect `x-edge-detailed-result-type` in the newly-enabled access logs, identify the handshake failure cause, restore `origin_protocol_policy = "https-only"` on port 443.

## Prod migration notes (for reference, remove after stag completes)

- Performed 2026-04-19 on account `046651569599`.
- Order: IAM policy update (aicentre-iac PR #169) → ACM certs → main apply → `deploy-ui` → DNS verified → Phase 2 cleanup (ALB UI target group etc.) + CloudFront access-logs apply.
- Total user-affecting window: ~3 min during the initial CloudFront population, then ~30 s during the A-record propagation. Trust polling remained green throughout.
- The CloudFront distribution ID is in `terraform output CloudfrontDistributionId`.
