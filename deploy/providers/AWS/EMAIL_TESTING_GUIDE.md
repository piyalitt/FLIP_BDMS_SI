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

# FLIP Email Template Testing Guide

This guide provides local testing procedures for FLIP AWS Cognito email templates without requiring AWS infrastructure or Cognito setup.

## Quick Start

### 1. Test Email Templates Locally (5 minutes)

```bash
cd deploy/providers/AWS

# Test all templates and generate HTML previews
python3 test_email_templates.py

# Output: email_previews/ directory with 3 HTML files
```

### 2. View Email Previews

#### Option A: Open directly in browser
```bash
# View in your default browser
open email_previews/flip_email_invite.html           # macOS
xdg-open email_previews/flip_email_invite.html       # Linux
start email_previews/flip_email_invite.html          # Windows
```

#### Option B: Start local HTTP server
```bash
python3 test_email_templates.py --serve

# Open in browser (auto-served):
# http://localhost:8000/flip_email_invite.html
# http://localhost:8000/flip_email_password_reset_code.html
# http://localhost:8000/flip_email_password_reset_link.html
```

#### Option C: View with custom test data
```bash
python3 test_email_templates.py \
  --username "alice.johnson@nhs.uk" \
  --subdomain "flip-prod.healthcare.org" \
  --output-dir "./custom_previews" \
  --serve --port 8888
```

### 3. Validate Placeholder Substitution

The test script automatically validates:
- ✓ Username placeholder substitution: `{username}` → test email
- ✓ Verification code display: `{####}` → `789456`
- ✓ Subdomain substitution: `{flip_alb_subdomain}` → custom environment
- ✓ Reset link placeholder: `{reset_link}` → full URL
- ✓ HTML structure and inline CSS
- ✓ FLIP branding colors and styling

**Example output:**
```
======================================================================
                FLIP EMAIL TEMPLATE VALIDATION REPORT
======================================================================

✓ PASS | Temporary Password Invitation
  Size: 8.2 KB
  Warnings:
    ⚠ Images present without alt text (logo placeholder comment)

✓ PASS | Password Reset (Code)
  Size: 7.9 KB

✓ PASS | Password Reset (Link)
  Size: 8.1 KB

======================================================================
Total templates tested: 3
Passed: 3/3
======================================================================
```

---

## Advanced Testing

### 4. Test in Multiple Email Clients

#### A. Gmail Web Client
1. Open generated HTML file in browser
2. Select all content and copy
3. Go to Gmail draft
4. Paste as HTML (right-click → Paste)
5. Check: Colors render correctly, buttons work, no layout breaking

#### B. Outlook Online
1. Upload HTML file as attachment to draft
2. Download and double-click to open in Outlook Web Access
3. Check: Colors, fonts, button styling

#### C. Apple Mail (Desktop/Mobile)
1. Save HTML as `.eml` file
2. Open with Mail app
3. Check: Gradient backgrounds, monospace font display

#### D. Automated Testing (Litmus/Email-on-Acid)
For professional testing across 70+ email clients:

1. Go to [Litmus](https://www.litmus.com/) or [Email on Acid](https://www.emailonacid.com/)
2. Upload generated HTML file
3. Review rendering screenshots across clients
4. Check for:
   - Gradient support (most clients support it)
   - CSS property compatibility
   - Table layout rendering
   - Image fallback behavior

### 5. Test Responsive Design

Email templates use responsive table layouts compatible with:
- ✓ Desktop clients (Gmail, Outlook, Apple Mail)
- ✓ Web clients (Gmail, Outlook.com, etc.)
- ✓ Mobile clients (iOS Mail, Android Gmail, etc.)
- ✓ Dark mode (Apple Mail, Outlook.com, Gmail)

**Manual mobile testing:**
1. Send test email to your phone
2. Open on iOS Mail / Android Gmail
3. Verify:
   - Text is readable (font sizes adjust)
   - Button is tappable (minimum 44px height)
   - Links are clickable
   - Colors are visible in dark mode

### 6. Test Placeholder Edge Cases

```bash
# Test with long username
python3 test_email_templates.py \
  --username "very.long.email.address.with.many.parts@healthcare-organization.co.uk"

# Test with different environment name
python3 test_email_templates.py \
  --subdomain "flip-production-v2.service.nhs.uk"

# Test with special characters in subdomain
python3 test_email_templates.py \
  --subdomain "flip-staging-us-west-2.example.com"
```

---

## Integration Testing with AWS Cognito

### 7. Manual Cognito Testing in AWS Console (Development Only)

After deploying to staging/production, test actual email delivery:

```bash
# Prerequisites: AWS CLI configured with credentials for staging account

# 1. Get the Cognito User Pool ID
cd deploy/providers/AWS
USER_POOL_ID=$(terraform output -raw cognito_user_pool_id)
echo "User Pool ID: $USER_POOL_ID"

# 2. Create a test user (suppresses automatic email)
aws cognito-idp admin-create-user \
  --user-pool-id "$USER_POOL_ID" \
  --username testuser@example.com \
  --message-action SUPPRESS \
  --region eu-west-2

# 3. Set a temporary password (triggers invitation email)
aws cognito-idp admin-set-user-password \
  --user-pool-id "$USER_POOL_ID" \
  --username testuser@example.com \
  --temporary-password "TempPass@123456789" \
  --permanent false \
  --region eu-west-2

# 4. Check your email for the invitation with HTML template rendering
# Verify:
# - Email subject: "Welcome to FLIP – Federated Learning and Interoperability Platform"
# - Purple gradient header renders correctly
# - Temporary password is displayed in monospace font
# - "Sign In to FLIP" button is clickable and links to correct environment
# - Footer branding is visible

# 5. Test password reset email flow
# - Login as testuser with temporary password
# - Initiate password reset
# - Check for password reset email delivery
# - Verify verification code is displayed clearly
# - Verify security warning section renders
# - Test"Reset Password" link

# 6. Cleanup test user
aws cognito-idp admin-delete-user \
  --user-pool-id "$USER_POOL_ID" \
  --username testuser@example.com \
  --region eu-west-2
```

### 8. SES Email Verification (Prerequisites)

Before testing with real Cognito emails:

1. **Verify SES Email in AWS Console**
   ```
   AWS Console → SES → Configuration → Identities
   - Check email shows "Verified" status
   - If expired: Delete identity, re-run terraform apply, confirm verification
   ```

2. **Sandbox Mode Restrictions**
   - By default, SES is in sandbox mode (can only send to verified emails)
   - To send to any email: Request production access in SES console
   - Production request typically approved within 24 hours

3. **Check SES Send Quota**
   ```bash
   aws ses get-account-sending-enabled --region eu-west-2
   ```

---

## Troubleshooting

### Issue: Email template validation fails

**Solution:** Check the error message in validation report and ensure:
- All required colors are present (`#61366e`, `#9452A8`)
- Required brand text exists ("FLIP", "The FLIP Team")
- HTML structure is valid (unclosed tags)

### Issue: Gradients not rendering in email client

**Root cause:** Some email clients don't support CSS gradients

**Workaround:** Background remains solid color as fallback

```css
/* Current implementation (with fallback) */
background: linear-gradient(135deg, #61366e 0%, #9452A8 100%);
background: #61366e; /* Fallback for unsupported clients */
```

### Issue: Button not clickable on mobile

**Solution:** Buttons use 44px minimum height for mobile accessibility

If test shows button isn't clickable:
1. Check email client (some clients disable links for security)
2. Test with specific client settings
3. Verify link URLs are fully formed

### Issue: SMS fallback truncated

**Solution:** SMS messages limited to 160 characters

Current SMS fallbacks:
- Invite: "You've been invited to FLIP..." (140 chars) ✓
- Password reset: "Your FLIP password reset code is..." (60 chars) ✓

---

## Acceptance Checklist

After local testing, verify:

- [ ] All 3 email templates generate without errors
- [ ] HTML files are valid and render in browser
- [ ] Placeholder substitution works correctly:
  - [ ] Username replaces `{username}`
  - [ ] Verification code replaces `{####}`
  - [ ] Subdomain replaces `{flip_alb_subdomain}`
  - [ ] Reset link replaces `{reset_link}`
- [ ] FLIP branding is visible:
  - [ ] Purple gradient header (#61366e → #9452A8)
  - [ ] "FLIP" logo/text in header
  - [ ] "The FLIP Team" footer
- [ ] Styling is professional:
  - [ ] Text is readable (font sizes, contrast)
  - [ ] Credentials displayed in monospace font
  - [ ] Call-to-action buttons are visible and styled
  - [ ] Colors are consistent with flip-ui
- [ ] Email clients compatibility tested:
  - [ ] Gmail (web and mobile)
  - [ ] Outlook (web and desktop)
  - [ ] Apple Mail
  - [ ] At least one additional client

- [ ] Responsive design verified:
  - [ ] Mobile viewport renders correctly
  - [ ] Buttons are tappable on mobile (44px+ height)
  - [ ] Text wraps correctly on small screens
- [ ] Cognito integration tested (if deploying):
  - [ ] Real Cognito email sent and received
  - [ ] Email renders correctly in recipient's client
  - [ ] Links in email are functional
  - [ ] Verification code is correct and usable

---

## References

- [AWS Cognito Email Customization](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/userguide/user-pool-email.html)
- [Email HTML Best Practices](https://www.mailgun.com/blog/email/html-email-best-practices/)
- [Email Client CSS Support](https://www.campaignmonitor.com/css/)
- [FLIP UI Branding](../../flip-ui/tailwind.config.js)
- [Cognito Placeholder Variables](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/userguide/user-pool-email-customization.html)

---

## Support

For issues or questions about email template testing:
1. Check the troubleshooting section above
2. Review test validation output for specific errors
3. Consult email client documentation for rendering issues
4. Open an issue on FLIP GitHub repository
