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

# Migrating from Direct SSH to SSM Session Manager

This guide is for operators who have existing deployments using direct SSH access (port 22 open) and are migrating to the new **AWS Systems Manager Session Manager** tunnel-based access.

## What's Changing

| Aspect | Before | After |
|--------|--------|-------|
| **Access method** | Direct SSH to public IP | SSM tunnel via AWS IAM |
| **Port 22** | Open in security group | Closed (no SSH ingress) |
| **Credentials** | SSH private keys (~/.ssh/id_rsa) | AWS CLI credentials |
| **Connection** | `ssh -i key.pem ubuntu@<ip>` | `ssh flip` (via config) |
| **Audit trail** | No centralized logging | CloudTrail logs all sessions |
| **Key management** | Manual key rotation | AWS manages credentials |

## Migration Steps

### 1. Install AWS Session Manager Plugin (One-Time Setup)

Before migrating, ensure the SSM plugin is installed locally:

**macOS:**
```bash
brew install session-manager-plugin
session-manager-plugin --version  # Should show version >= 1.2.319.0
```

**Linux (Ubuntu/Debian):**
```bash
curl "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb" -o "session-manager-plugin.deb"
sudo dpkg -i session-manager-plugin.deb
session-manager-plugin --version  # Verify installation
```

### 2. Verify AWS CLI Authentication

Ensure your AWS CLI is authenticated and can reach the correct AWS account:

```bash
# Set your AWS profile and region
export AWS_PROFILE=<your-profile>  # e.g., FlipDeveloperAccess-046651569599
export AWS_REGION=eu-west-2        # Must match deployment region

# Verify authentication
aws sts get-caller-identity

# You should see output with your Account ID, ARN, and UserId
```

### 3. Generate New SSH Config

Navigate to the AWS deployment directory and regenerate your SSH config with SSM ProxyCommand:

```bash
cd deploy/providers/AWS
make ssh-config
```

**What this does:**
- Reads EC2 instance IDs from Terraform state
- Generates new `Host flip` and `Host flip-trust` blocks in `~/.ssh/config`
- Backs up old config to `~/.ssh/config.backup.TIMESTAMP`
- Adds SSM ProxyCommand to transparently tunnel through SSM

### 4. Test New SSH Access

Verify the new SSM-based SSH works before removing old infrastructure:

```bash
# Test direct SSM session first (diagnostic)
aws ssm start-session --target $(terraform output -raw Ec2InstanceId)
# You should see a shell prompt. If this fails, stop and debug IAM permissions.

# Test SSH via config (what you'll use going forward)
ssh flip  # Should connect to Central Hub

ssh flip-trust  # Should connect to Trust instance (if deployed)

# On each host, verify you're connected correctly
uname -a  # Shows system info
docker ps  # Shows running containers
exit  # Disconnect
```

### 5. Update Your Scripts & CI/CD

If you have scripts that use direct SSH (e.g., `ssh ubuntu@<public-ip>`), update them:

**Before:**
```bash
ssh -i ~/.ssh/id_rsa -o StrictHostKeyChecking=no ubuntu@${CENTRAL_HUB_IP} "docker ps"
```

**After:**
```bash
ssh flip "docker ps"  # Uses config; no need for -i or IP
```

**For CI/CD:**
- Ensure CI/CD runners have AWS CLI credentials configured (IAM role or assumed role)
- Install session-manager-plugin in CI/CD environment
- Regenerate SSH config: Call `make ssh-config` before deploying
- Use SSH aliases (`ssh flip`) instead of IP addresses

### 6. Remove Old SSH Infrastructure (Optional)

Once you've verified SSM access works, you can clean up old SSH setup:

```bash
# View old known hosts
cat ~/.ssh/known_hosts | grep -E "(central|trust|flip)"

# Remove old entries (optional; they won't be used anymore)
ssh-keygen -R flip  # Remove old host key
ssh-keygen -R flip-trust

# Or delete and regenerate
rm ~/.ssh/known_hosts
touch ~/.ssh/known_hosts

# Verify only new entries exist
cat ~/.ssh/config | grep -A 3 "Host flip"
```

### 7. Update Team Documentation

Notify your team of the migration:

1. **Send migration guide** to all operators with deployment access
2. **Update runbooks** to replace direct SSH commands with `ssh flip` / `ssh flip-trust`
3. **Highlight benefits**: No SSH keys to manage, centralized audit trail, more secure
4. **Provide troubleshooting contact** for any connectivity issues during transition

## Troubleshooting Migration Issues

### Issue: SSH config shows old IP addresses

**Cause:** Old config wasn't regenerated after infrastructure change

**Fix:**
```bash
cd deploy/providers/AWS
make ssh-config  # Regenerates from current Terraform state
cat ~/.ssh/config | grep -A 3 "Host flip"  # Should show instance IDs, not IPs
```

### Issue: `ssh flip` hangs or times out

**Cause:** SSM plugin not installed or AWS credentials not available

**Diagnostics:**
```bash
# Check plugin installed
session-manager-plugin --version

# Check AWS credentials
aws sts get-caller-identity

# Test SSM directly
aws ssm start-session --target $(terraform output -raw Ec2InstanceId)
```

**Fix:** See [Prerequisites](README.md#prerequisites) section of AWS README

### Issue: "AccessDeniedException" when connecting

**Cause:** EC2 instance IAM role doesn't have SSM permissions

**Fix:**
- Verify EC2 instance has IAM role attached (check AWS console: EC2 > Instances > Details > IAM role)
- If missing, run `make destroy && make apply` to recreate with correct role
- Or manually add SSM permissions to existing role (not recommended)

### Issue: `~/.ssh/config` backup files piling up

**Cause:** `make ssh-config` creates timestamped backups on each run

**Cleanup:**
```bash
# Optional: Remove old backups (keep last 3)
ls -la ~/.ssh/config* | head -5
rm ~/.ssh/config.backup.*  # Or keep specific ones

# New backups will still be created on next run
```

## Rollback Plan (If Needed)

If you need to temporarily revert to direct SSH before old infrastructure is torn down:

```bash
# Restore old SSH config
cp ~/.ssh/config.backup.TIMESTAMP ~/.ssh/config

# Verify old IPs are present
grep "Host central-hub-old" ~/.ssh/config

# Connect using old method
ssh -i ~/.ssh/id_rsa ubuntu@<old-public-ip>
```

However, **we recommend staying on SSM** for security reasons. If you encounter issues during migration, contact the DevOps team before reverting.

## Benefits of SSM-Based Access

### Security
- ✅ No permanent SSH keys needed — temporary AWS credentials expire automatically
- ✅ Centralized audit trail via CloudTrail — all sessions logged and auditable
- ✅ Port 22 is closed — no direct SSH attack surface
- ✅ IAM role-based access control — fine-grained permissions per operator

### Operational
- ✅ No SSH key rotation burden — AWS manages credential lifecycle
- ✅ No bastion host needed — SSM tunnel is transparent
- ✅ Works from any network — no IP allowlist needed
- ✅ Better for CI/CD — uses IAM roles instead of stored SSH keys

### Compliance
- ✅ Audit trail for regulatory requirements (SOC 2, HIPAA, etc.)
- ✅ No shared SSH keys — each user's access tracked separately
- ✅ Session recordings available (if configured in SSM)

## Support & Questions

If you encounter issues during migration:

1. **Check [Troubleshooting](README.md#troubleshooting-ssm-access) section** in AWS README
2. **Run diagnostics:**
   ```bash
   make -C deploy/providers/AWS check-ssm-ready  # Pre-deployment verification
   ```
3. **Test connectivity:**
   ```bash
   make -C deploy/providers/AWS status  # Health checks including SSH
   ```
4. **Contact DevOps team** with error output if unresolved

---

**Last Updated:** April 2026  
**Related Docs:** [AWS README - Remote Access](README.md#remote-access-via-ssm-session-manager)
