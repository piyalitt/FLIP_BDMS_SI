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

# Email Template Testing Checklist

Quick reference for local email template testing.

## Quick Test (5 min)

```bash
cd deploy/providers/AWS
python3 test_email_templates.py --serve
# Opens http://localhost:8000 with 3 email preview files
```

**Verify:**
- [ ] Script runs without errors
- [ ] 3 HTML preview files generated
- [ ] All templates render in browser
- [ ] Placeholder values substituted (username, verification code, URLs)

---

## Desktop Client Testing (15 min)

### Gmail
- [ ] Open html file in browser
- [ ] Purple gradient header visible
- [ ] Credentials box with left border accent
- [ ] "Sign In" button styled and linked
- [ ] Footer branding visible

### Outlook
- [ ] Open html file in browser
- [ ] Gradients render (or solid color fallback)
- [ ] Monospace fonts visible for credentials
- [ ] Button is clickable

### Apple Mail
- [ ] Dark mode compatible (readable)
- [ ] Colors visible in light and dark mode
- [ ] Spacing and alignment correct
- [ ] Links functional

---

## Mobile Testing (10 min)

- [ ] Send preview to mobile device
- [ ] Text readable on small screen
- [ ] Button tappable (44px+ height)
- [ ] Links clickable
- [ ] Dark mode readable

---

## AWS Integration Test (20 min)

Prerequisites: AWS credentials configured, Cognito user pool deployed

```bash
# Create test user
aws cognito-idp admin-create-user \
  --user-pool-id <pool-id> \
  --username testuser@example.com \
  --message-action SUPPRESS

# Set temporary password (triggers email)
aws cognito-idp admin-set-user-password \
  --user-pool-id <pool-id> \
  --username testuser@example.com \
  --temporary-password "TempPass@123456789" \
  --permanent false
```

**Verify:**
- [ ] Email received within 5 minutes
- [ ] Subject line correct: "Welcome to FLIP – Federated Learning and Interoperability Platform"
- [ ] HTML renders correctly in email client
- [ ] Temporary password visible and correct
- [ ] "Sign In" link works and goes to correct environment
- [ ] Username appears in greeting

```bash
# Test password reset
# 1. Login with temporary password
# 2. Initiate password reset
# 3. Check for reset email
```

**Verify:**
- [ ] Reset email received
- [ ] Subject: "Password Reset Request – FLIP"
- [ ] Verification code (or reset link) visible and correct
- [ ] Security warning section visible
- [ ] "Reset Password" button works

---

## Email Client Compatibility Matrix

| Client | Support | Test URL |
|--------|---------|----------|
| Gmail Web | ✓ Full | https://mail.google.com |
| Gmail Mobile | ✓ Full | Mobile app |
| Outlook Web | ✓ Full | https://outlook.live.com |
| Outlook Desktop | ✓ Mostly | Windows/Mac app |
| Apple Mail | ✓ Full | macOS/iOS |
| Thunderbird | ✓ Full | thunderbird.net |
| Yahoo Mail | ✓ Good | yahoo.com |
| Others | ? | Litmus/Email-on-Acid |

---

## Placeholder Testing

Test with different values:

```bash
# Long email address
python3 test_email_templates.py \
  --username "very.long.name@healthcare-organization.co.uk"

# Complex subdomain
python3 test_email_templates.py \
  --subdomain "flip-staging-us-west-2.service.nhs.uk"

# Special characters
python3 test_email_templates.py \
  --username "user+test@example.co.uk"
```

**Verify:** Text doesn't break layout, remains readable

---

## Before Merging

- [ ] All tests pass: `python3 test_email_templates.py`
- [ ] Validation report shows ✓ PASS for all 3 templates
- [ ] HTML previews render correctly in 3+ email clients
- [ ] Documentation updated (this file, EMAIL_TESTING_GUIDE.md)
- [ ] Commits signed: `git commit -s`
- [ ] Branch up to date with develop
- [ ] No linting/formatting issues

---

## Post-Deployment Verification

After deploying to staging/production:

1. **First 24 hours**
   - [ ] Send test invitation via Cognito console
   - [ ] Verify email delivery and rendering
   - [ ] Test password reset flow

2. **Weekly smoke test**
   - [ ] Create test user and verify invitation email
   - [ ] Test password reset email
   - [ ] Spot-check rendering in latest Gmail, Outlook, Apple Mail

3. **Monthly review**
   - [ ] Check SES bounce/complaint rates
   - [ ] Review email client compatibility reports (if using Litmus)
   - [ ] Update templates if client compatibility changes

---

## Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| Gradients don't render | Email client doesn't support CSS gradients | Use `background: #color` fallback (already in template) |
| Button not clickable | Email client security settings | Buttons use standard `<a>` tags, should work on all clients |
| Text wraps awkwardly | Table width too wide | Responsive layout uses max-width: 600px (standard) |
| Colors too dark/light | Dark mode rendering | Test in both light and dark mode |
| Logo not showing | CDN URL not set | Inline HTML with no external dependencies needed |

---

## Resources

- **Testing Guide:** [EMAIL_TESTING_GUIDE.md](./EMAIL_TESTING_GUIDE.md)
- **Test Script:** [test_email_templates.py](./test_email_templates.py)
- **Terraform Config:** [services.tf](./services.tf)
- **Cognito Docs:** https://docs.aws.amazon.com/cognito-user-identity-pools/latest/userguide/user-pool-email-customization.html
- **Email Best Practices:** https://www.mailgun.com/blog/email/html-email-best-practices/

---

**Last Updated:** 2026-03-23  
**Status:** ✓ Actively maintained
