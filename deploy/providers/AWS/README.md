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

# FLIP AWS Terraform/OpenTofu and Ansible Infrastructure

Terraform/OpenTofu and Ansible Infrastructure as Code to deploy the FLIP application stack to AWS.

This provider manages the **Central Hub** (always in AWS) and, optionally, one or more **Trust** instances. Trust services can be deployed in two ways:

| Deployment Model | Trust Location | Managed By |
| --- | --- | --- |
| **Cloud** | AWS EC2 (same account as Central Hub) | This provider (`deploy/providers/AWS/`) |
| **Hybrid / On-Premises** | Any Ubuntu host (home lab, hospital server, etc.) | [`deploy/providers/local/`](../local/README.md) + selected targets in this Makefile |

Both models use self-signed TLS certificates and an nginx-tls sidecar so that all Central Hub ↔ Trust communication is encrypted over HTTPS.

## Prerequisites

1. **AWS CLI configured** with SSO access (see [deploy README](../../README.md))
2. **Terraform >= 1.13.1** or OpenTofu installed
3. **Python 3.12+**
4. **UV environment manager** installed via [uv installation guide](https://docs.astral.sh/uv/guides/install-python/)
5. **GitHub CLI** installed via [GitHub CLI installation guide](https://cli.github.com/)
6. **SSH key pair** created at `~/.ssh/host-aws` (see [deploy README](../../README.md))
7. **Environment files** configured: (see [deploy README](../../README.md))
   - `.env.stag` (staging) or `.env.production` (production) in project root
   - Service-specific `.env` files (see Environment Configuration section)

### Required AWS Permissions

Your AWS IAM role/user needs the following permissions for provisioning infrastructure:

- **SSM**: `ssm:GetParameter` for fetching AMI IDs
- **EC2**: Full access (VPC, instances, security groups, key pairs, Elastic IPs)
- **RDS**: `rds:CreateDBSubnetGroup`, `rds:CreateDBParameterGroup`, `rds:CreateDBInstance`
- **CloudWatch Logs**: `logs:*`
- **Secrets Manager**: Full access for storing database credentials and API secrets
- **IAM**: Create and manage roles for EC2 instances
- **Application Load Balancer**: Create and manage ALBs
- **SES**: Manage email templates (optional for email functionality)

Managed policies that cover these requirements:

- `AmazonEC2FullAccess`
- `AmazonRDSFullAccess`
- `CloudWatchLogsFullAccess`
- `SecretsManagerReadWrite`
- `IAMFullAccess`
- `ElasticLoadBalancingFullAccess`
- `AmazonSESFullAccess` (optional)

**Note**: The deployed EC2 instances use minimal IAM permissions (SSM and CloudWatch only) following the principle of least privilege.

## Deployment Workflow

### Full Stack Deployment

The complete deployment process is automated via the `full-deploy` target:

```bash
cd deploy/providers/AWS
make full-deploy PROD=stag  # For staging
# OR
make full-deploy PROD=true  # For production
```

This command executes the following steps in order:

1. **`github-login`**: Authenticate with GitHub CLI
2. **`aws-login`**: Authenticate with AWS SSO
3. **`init`**: Initialize Terraform with environment-specific S3 backend
4. **`import-all`**: Import existing AWS resources to prevent replacement
5. **`plan`**: Generate and review Terraform execution plan
6. **`apply`**: Apply infrastructure changes
7. **`ssh-config`**: Update `~/.ssh/config` with EC2 instance IPs
8. **`ansible-init`**: Configure EC2 instances with Docker and CloudWatch
9. **`deploy-centralhub`**: Deploy Central Hub services via Docker Compose
10. **`deploy-trust`**: Deploy Trust services via Docker Compose
11. **`status`**: Run comprehensive health checks

### Manual Step-by-Step Deployment

For debugging or selective deployment, run individual steps:

```bash
# 1. Login to AWS
make aws-login

# 2. Initialize Terraform (creates/configures S3 backend)
make init

# 3. Import existing resources (prevents replacement errors)
make import-all

# 4. Plan changes
make plan

# 5. Apply infrastructure
make apply

# 6. Configure SSH access
make ssh-config

# 7. Setup EC2 instances with Ansible
make ansible-init

# 8. Deploy services
make deploy-centralhub
make deploy-trust

# 9. Check status
make status
```

### Deployment to Different Environments

**Staging:**

```bash
make full-deploy PROD=stag
```

**Production:**

```bash
make full-deploy PROD=true
```

The `PROD` variable determines which environment files are loaded:

- `PROD=stag` → Uses `.env.stag`, `flip-api/.env.stag`
- `PROD=true` → Uses `.env.production`, `flip-api/.env.production`

### Destroy Infrastructure

The destroy process preserves critical resources (Cognito, Secrets, S3) while safely removing infrastructure:

```bash
make destroy
```

**What gets destroyed:**

- Trust EC2 instance
- Central Hub EC2 instance
- Application Load Balancer
- RDS database (with skip-final-snapshot)
- VPC, subnets, security groups, NAT gateway
- IAM roles and policies
- Elastic IPs

**What gets preserved:**

- Cognito User Pool and users (authentication data)
- Secrets Manager secret (FLIP_API configuration)
- S3 bucket (application data)

### Status Checking

The deployment includes a comprehensive Python-based status checker:

```bash
make status
```

This validates:

- ✅ Terraform state and outputs
- ✅ VPC, subnets, and security group configurations
- ✅ EC2 instance health (Central Hub and Trust)
- ✅ RDS database connectivity
- ✅ Secrets Manager access
- ✅ S3 bucket accessibility
- ✅ Cognito User Pool configuration
- ✅ Docker services on EC2 instances
- ✅ HTTP endpoint availability
- ✅ SSH connectivity
- ✅ CloudWatch Logs configuration

## TLS Certificates (HTTPS)

All trust services are fronted by an **nginx-tls** sidecar that terminates HTTPS. The Central Hub verifies the trust's self-signed certificate using a CA cert stored in AWS Secrets Manager.

### Certificate lifecycle for cloud trusts

The `full-deploy` target handles this automatically:

1. First `apply` — provisions EC2 instances (CA cert placeholder in Secrets Manager)
2. `gen-trust-ec2-certs` — generates CA + server cert using the Trust EC2's public IP
3. Second `apply` — writes the real CA cert into Secrets Manager

To regenerate certificates after the initial deployment:

```bash
make regen-trust-certs
```

This regenerates certs, SCPs them to the Trust EC2, restarts nginx-tls, and updates Secrets Manager.

### Certificate lifecycle for on-premises trusts

Certificates are generated by the Ansible playbook during `make add-local-trust`. See the [local provider README](../local/README.md) for details.

## Hybrid Deployment: Adding an On-Premises Trust

To connect a local (on-premises) Trust host to the AWS Central Hub:

Recommended orchestration target (staging):

```bash
cd deploy/providers/AWS
make full-deploy-stag-hybrid LOCAL_TRUST_IP=<public-ip> [LOCAL_TRUST_SSH_KEY=~/.ssh/trust_key]
```

Or run provisioning directly:

```bash
cd deploy/providers/AWS

# Remote host (via SSH)
make add-local-trust LOCAL_TRUST_IP=<public-ip> LOCAL_TRUST_SSH_KEY=~/.ssh/trust_key

# Local machine (no SSH)
set -x ANSIBLE_BECOME_PASS (read -s -P 'Sudo password: ')
make add-local-trust LOCAL_TRUST_IP=<public-ip>
```

After provisioning, complete the manual steps printed by the target:

1. Configure router port forwarding (`TRUST_API_PORT/tcp` → trust host LAN IP)
2. Update the trust endpoint URL in the `FLIP_API` secret: `make set-local-trust-endpoint LOCAL_TRUST_IP=<public-ip>` <!-- pragma: allowlist secret -->
3. Start the trust stack on the host: `cd trust && env PROD=stag make up-local-trust-stag`
4. Verify (CA-validated): `make test-local-trust LOCAL_TRUST_IP=<public-ip>`
5. Optional handshake-only diagnostic: `make test-local-trust-insecure LOCAL_TRUST_IP=<public-ip>`
6. Restart `flip-api` on the Central Hub

Full details, including home network firewall configuration and troubleshooting, are in the [local provider README](../local/README.md).

## Troubleshooting

### Quick Diagnosis

First, run the automated status check script to identify issues:

```bash
make status
```

This will automatically diagnose:

- AWS resource health
- Network connectivity
- Application endpoint availability
- Docker container status
- System resource usage

Review the output for failed checks and follow the specific troubleshooting steps below.

## Architecture

### Services

The platform supports a cloud-only setup (Central Hub + Trust on AWS) or a hybrid setup (Central Hub on AWS + Trust on-premises). Both use HTTPS for inter-service communication.

1. **Central Hub EC2**: Hosts the main application services
   - flip-ui (Frontend)
   - flip-api (Backend API)
   - fl-api-net-1 (Federated Learning API for Network 1)
   - fl-api-net-2 (Federated Learning API for Network 2)
   - fl-server-net-1 (Federated Learning Server for Network 1)
   - fl-server-net-2 (Federated Learning Server for Network 2)

2. **Trust EC2** (cloud model): Hosts trust-related services (automatically provisioned)
   - nginx-tls (HTTPS termination)
   - trust-api
   - imaging-api
   - data-access-api
   - fl-client-net-1 (FL Client for Network 1)
   - fl-client-net-2 (FL Client for Network 2)
   - XNAT (medical imaging platform)
   - Orthanc (DICOM server)
   - OMOP database

3. **On-Premises Trust** (hybrid model, optional): Same trust services running on a local host
   - Provisioned via [`deploy/providers/local/`](../local/README.md)
   - Connected to the Central Hub over the internet via HTTPS

| Application Component |
| ---------------------- |
| **Central Hub Services** |
| FLIP API ✅ |
| FLIP UI ✅ |
| FL API ✅ |
| FL Server ✅ |
| **Trust Services** |
| Trust API ✅ |
| Imaging API ✅ |
| Data Access API ✅ |
| XNAT (medical imaging) ✅ |
| Orthanc (DICOM server) ✅ |

```sh
┌─────────────────┐
│    Internet      │
└────────┬────────┘
         │
    ┌────▼────┐
    │   ALB    │ (HTTPS, ACM cert)
    └────┬────┘
         │
    ┌────▼──────────────────────┐
    │  Central Hub EC2          │
    │  - flip-ui                │
    │  - flip-api               │
    │  - fl-api                 │
    │  - fl-server              │
    └──────┬───────────┬────────┘
           │           │
     HTTPS │           │ HTTPS
           │           │
    ┌──────▼─────┐  ┌──▼──────────────────────┐
    │ Trust EC2  │  │ On-Prem Trust (optional) │
    │ (AWS)      │  │ (home/hospital network)  │
    │            │  │                          │
    │ nginx-tls  │  │ nginx-tls                │
    │ trust-api  │  │ trust-api                │
    │ imaging-api│  │ imaging-api              │
    │ data-acc.. │  │ data-access-api          │
    │ XNAT       │  │ fl-client                │
    │ Orthanc    │  │                          │
    │ fl-client  │  │ (via router port fwd)    │
    └────────────┘  └──────────────────────────┘
```

![AWS architecture](docs/AWS.png "AWS architecture")

### Central Hub Infrastructure

- **VPC**: Custom VPC with public/private subnets
- **Central Hub EC2**: Single t3.small instance running Docker containers (UI, API, FL services)
- **Trust EC2**: Separate t3.small instance running Trust services via Docker Compose
  - Deployed using custom Terraform module (`modules/trust_ec2`)
  - Automatic Docker and Docker Compose installation via user_data
  - Automatic Docker network creation for inter-service communication
  - Optional Elastic IP for static addressing
- **ALB**: Application Load Balancer for traffic routing
- **RDS**: PostgreSQL 13.22 managed database
- **CloudWatch**: Logging and monitoring for both EC2 instances
- **Secrets Manager**: Secure storage for API secrets and database credentials
- **S3 Backend**: Remote state storage with environment-specific buckets

### Trust Infrastructure

Trust services can run on AWS EC2 or on-premises. Both models use the same Docker Compose stack with an nginx-tls sidecar for HTTPS termination.

**Cloud Trust (AWS EC2)** — deployed using the `trust_ec2` Terraform module:

- Automated Docker and Docker Compose installation
- Trust compose stack deployment via user_data script
- Automatic Docker network creation for inter-service communication
- TLS certificates generated via `gen-trust-ec2-certs` and SCPed to the instance
- Optional Elastic IP for static addressing

**On-Premises Trust** — provisioned via `make add-local-trust` and the Ansible playbook in [`deploy/providers/local/`](../local/README.md):

- Same Docker Compose stack, running on a local Ubuntu host
- TLS certificates generated by Ansible (`community.crypto`)
- UFW firewall restricts inbound traffic to the Central Hub IP only
- Requires home router port forwarding for external connectivity

### Port configuration

| Port | Service | Status | Purpose |
| ------ | --------- | --------- | --------- |
| **22** | SSH | 🟢 **OPEN** | Remote administration |
| **80** | HTTP | 🟢 **OPEN** | ALB traffic |
| **3000** | FLIP UI | 🟢 **OPEN** | Frontend application |
| **8000** | FLIP API | 🟢 **OPEN** | Backend API |
| **8001** | FL API | 🟢 **OPEN** | Federated learning API |
| **8002** | FL Server | 🟡 **CONDITIONAL** | gRPC (open to trust IPs only) |
| **8003** | FL Admin | 🟡 **CONDITIONAL** | Admin (open to trust IPs only) |
| **8020** | Trust API | 🟢 **OPEN** | HTTPS (nginx-tls → trust-api) |

---

## Email Templates

AWS Cognito email templates are now stored as separate HTML files in `email_templates/` directory instead of being embedded in `services.tf`. This ensures a single source of truth: both Terraform and Python testing scripts reference the same templates.

### Email Architecture

```sh
deploy/providers/AWS/
├── email_templates/
│   ├── invite.html                          # Temporary password invitation
│   ├── password_reset_code.html             # Password reset with verification code
│   └── password_reset_link.html             # Password reset with direct link
├── services.tf                              # Terraform config - loads templates via file()
├── test_email_templates.py                  # Python test utility - loads templates at startup
```

### How Templates Are Loaded

**Terraform** (services.tf):

```hcl
email_message = file("${path.module}/email_templates/invite.html")
```

- Uses `file()` function with relative path
- `${path.module}` ensures correct resolution during `terraform plan` and `terraform apply`

**Python** (test_email_templates.py):

```python
template_dir = Path(__file__).parent / "email_templates"
self.INVITE_TEMPLATE_HTML = (template_dir / "invite.html").read_text()
```

- Loads at `__init__` time
- Changes to template files are automatically picked up on next test run

### Template Placeholders

| Placeholder | Replaced By | Example |
| --- | --- | --- |
| `{username}` | Cognito username (email) | <john.smith@example.com> |
| `{####}` | 6-digit temporary password or verification code | 123456 |
| `{flip_alb_subdomain}` | ALB domain from Terraform var | flip-app.example.com |
| `{reset_link}` | Password reset link with token | <https://flip.../reset?token=xyz> |

### Quick Local Testing

```bash
cd deploy/providers/AWS

# Test all templates and generate HTML previews
python3 test_email_templates.py

# View in browser with local HTTP server
python3 test_email_templates.py --serve
# Open http://localhost:8000/flip_email_invite.html

# Test with custom data
python3 test_email_templates.py \
  --username "user@health.org" \
  --subdomain "flip-stag.example.com"
```

The validation script checks:

- ✓ HTML structure and syntax
- ✓ Placeholder substitution ({username}, {####}, etc.)
- ✓ FLIP branding colors (#61366e, #9452A8)
- ✓ Required text elements present
- ✓ Generate browser-viewable preview files

### Desktop Email Client Testing

After viewing local previews, test in actual email clients:

1. **Gmail Web**: Copy HTML from preview, paste as draft
2. **Outlook**: Upload HTML file as attachment
3. **Apple Mail**: Save as `.eml` and open
4. **Mobile**: Send test email to phone and verify rendering

Key verification points:

- [ ] Purple gradient header renders correctly
- [ ] Credentials displayed in monospace font
- [ ] "Sign In" / "Reset Password" buttons are clickable
- [ ] Links go to correct environment URL
- [ ] Text is readable in both light and dark modes
- [ ] Responsive on mobile (buttons 44px+ for tapping)

### AWS Cognito Integration Testing

After deploying to staging/production:

```bash
# Create test user (suppresses automatic email)
aws cognito-idp admin-create-user \
  --user-pool-id <pool-id> \
  --username testuser@example.com \
  --message-action SUPPRESS \
  --region eu-west-2

# Set temporary password (triggers invitation email)
aws cognito-idp admin-set-user-password \
  --user-pool-id <pool-id> \
  --username testuser@example.com \
  --temporary-password "TempPass@123456789" \
  --permanent false \
  --region eu-west-2

# Check your email for:
# - Subject: "Welcome to FLIP – Federated Learning and Interoperability Platform"
# - Purple gradient header, buttons, footer branding all render correctly
# - Temporary password visible in credentials box
# - "Sign In" link goes to correct environment

# Test password reset flow
# - Login as testuser with temporary password
# - Initiate password reset
# - Verify reset email received with verification code or reset link
# - Click reset link / enter code and verify it works

# Cleanup
aws cognito-idp admin-delete-user \
  --user-pool-id <pool-id> \
  --username testuser@example.com \
  --region eu-west-2
```

### Email Client Compatibility

| Client | Support | Notes |
|--------|---------|-------|
| Gmail Web | ✓ Full | CSS gradients supported |
| Outlook Web | ✓ Full | CSS gradients with fallback |
| Apple Mail | ✓ Full | Dark mode compatible |
| Outlook Desktop | ✓ Mostly | Table layout reliable |
| Thunderbird | ✓ Full | Standard HTML support |
| Yahoo Mail | ✓ Good | Limited CSS support |
| Other | ? | Test via Litmus/Email-on-Acid |

For professional testing across 70+ clients: [Litmus](https://www.litmus.com/) or [Email on Acid](https://www.emailonacid.com/)

### SES Prerequisites

Before testing Cognito emails:

1. **Verify SES Email** in AWS Console:
   - SES → Configuration → Identities
   - Check email shows "Verified" status
   - If expired: Delete identity, re-run `terraform apply`, confirm verification

2. **Sandbox Mode** (default):
   - Can only send to verified email addresses
   - Request production access in SES console (typically approved in 24 hours)

3. **Check Send Quota**:

   ```bash
   aws ses get-account-sending-enabled --region eu-west-2
   ```

### Troubleshooting Email Issues

| Issue | Solution |
|-------|----------|
| Email gradients don't render | Most clients support gradients; solid color fallback in template |
| Button not clickable in email | Some clients disable links for security; use email client settings |
| Text wraps awkwardly | Tables use responsive max-width: 600px (standard) |
| Colors wrong in dark mode | Test in both light/dark modes; colors contrast checked |
| Missing logo | Logo is commented placeholder in template (configure CDN URL if needed) |
| Email not delivered | Check SES verification status; verify recipient email is in whitelist |

### Making Template Changes

1. **Edit template file**: `email_templates/invite.html` (or other template)
2. **Test locally**: `python3 test_email_templates.py` (verify all 3 pass ✓)
3. **Review**: Check generated `email_previews/*.html` files
4. **Deploy**: Changes automatically used in next `terraform apply`

Both systems use exact same template content—no sync required!

### Pre-Deployment Checklist

Before merging email template changes:

- [ ] All tests pass: `python3 test_email_templates.py`
- [ ] Validation report shows ✓ PASS for all 3 templates
- [ ] HTML previews render correctly in 3+ email clients
- [ ] FLIP branding present (colors, text, footer)
- [ ] All placeholders substitute correctly
- [ ] Links are functional and go to correct environment
- [ ] Mobile responsive (tested on phone if possible)
