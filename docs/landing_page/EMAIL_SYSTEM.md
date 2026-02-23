# Landing Page Email System

## Executive Summary

The BuffettGPT landing page email system provides automated transactional emails for the waitlist signup and referral flows. It uses [Resend](https://resend.com) as the email delivery provider, integrated into the existing serverless Lambda architecture. All emails are fire-and-forget: delivery failures are logged but never block user-facing operations.

The system was deployed to the dev environment on 2026-02-21 and verified with 36 passing e2e tests, including real email delivery to `buffett.dev117@gmail.com`.

---

## Architecture

```
User signs up on WaitlistPage.jsx
        │
        ▼
  POST /waitlist/signup
        │
        ▼
┌──────────────────────────────┐
│   waitlist_handler Lambda    │
│                              │
│  1. Validate email           │
│  2. Check rate limit (5/hr)  │
│  3. Write to DynamoDB        │
│  4. Credit referrer (if any) │
│  5. Send email (fire & forget)│
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│   email_service.py           │
│                              │
│  - Fetches Resend API key    │
│    from Secrets Manager      │
│  - Lazy-initializes SDK      │
│  - Renders HTML templates    │
│  - Calls Resend Emails API   │
└──────────┬───────────────────┘
           │
           ▼
     Resend API → Inbox
```

### Key Design Decisions

- **Fire-and-forget**: Email calls are wrapped in `try/except` at the handler level. If Resend is down, the signup or referral credit still succeeds. Failures are logged as warnings.
- **Lazy initialization**: The Resend SDK is initialized on first use. The API key is fetched once from Secrets Manager and cached via `@lru_cache`.
- **JSON secret parsing**: The Resend secret is stored as JSON (`{"resend_dev_key": "re_xxx"}`). The service automatically detects JSON-wrapped secrets and extracts the API key value.
- **No custom domain (yet)**: Emails are sent from `onboarding@resend.dev` (Resend's shared sandbox sender). When a custom domain is purchased and verified in Resend, only the Terraform `resend_from_email` variable needs to change.

---

## Email Types

### 1. Welcome Email

**Trigger**: Successful waitlist signup (HTTP 201)

**Not sent on**: Duplicate signup (409), validation error (400), or rate limit (429)

**Content**:
- Confirmation that the user is on the waitlist
- Their unique referral code (e.g., `BUFF-A3X9KP`)
- Referral tier breakdown (1 = Early Access, 3 = 1 Month Free Plus, 5 = 3 Months Free Plus)
- CTA button linking to their referral URL

**Source**: `email_service.send_welcome_email(to, referral_code, referral_link)`

### 2. Tier Unlocked Email

**Trigger**: A referral pushes the referrer's count to a tier threshold (1, 3, or 5)

**Content**:
- Congratulations message with the unlocked tier name
- Green highlight box showing the reward description
- CTA to keep sharing

**Source**: `email_service.send_tier_unlocked_email(to, tier_name, tier_reward, referral_count, referral_code)`

### 3. Referral Success Email

**Trigger**: A referral is credited but no new tier is unlocked (e.g., count goes from 1 to 2)

**Content**:
- Notification that someone used their referral code
- Current referral count
- Progress toward the next tier (how many more referrals needed)
- CTA to share again

**Source**: `email_service.send_referral_success_email(to, referral_count, referral_code, current_tier, next_tier)`

---

## Referral Tiers

| Threshold | Tier Name | Reward | Status Promotion |
|-----------|-----------|--------|-----------------|
| 1 referral | Early Access | Skip the waitlist | `waitlisted` → `early_access` |
| 3 referrals | 1 Month Free Plus | 1 month free Plus subscription | None (manual fulfillment) |
| 5 referrals | 3 Months Free Plus | 3 months free Plus subscription | None (manual fulfillment) |

The automatic status promotion to `early_access` uses a DynamoDB conditional update (`SET status = :early_access WHERE status = :waitlisted`) to ensure atomicity and idempotency.

---

## Infrastructure

### Files

| File | Purpose |
|------|---------|
| `chat-api/backend/src/utils/email_service.py` | Core email utility (Resend SDK wrapper, templates, send logic) |
| `chat-api/backend/src/handlers/waitlist_handler.py` | Lambda handler that calls email functions |
| `chat-api/terraform/modules/email/main.tf` | Terraform module: references existing Resend secret |
| `chat-api/terraform/modules/email/iam.tf` | IAM policy granting `GetSecretValue` on the Resend secret |
| `chat-api/terraform/modules/email/variables.tf` | Module variables (`resend_secret_name`, `resend_from_email`) |
| `chat-api/terraform/modules/email/outputs.tf` | Outputs: secret ARN, from email, IAM policy ARN |
| `chat-api/backend/layer/requirements.txt` | Lambda layer dependencies (includes `resend>=2.0.0`) |

### AWS Resources

| Resource | Name / ARN |
|----------|-----------|
| Secrets Manager secret | `resend_dev_key` (manually created, JSON format) |
| IAM policy | `resend-secrets-access-dev` |
| Lambda env vars (waitlist_handler) | `RESEND_API_KEY_ARN`, `RESEND_FROM_EMAIL` |
| Lambda layer | `buffett-dev-dependencies` (includes `resend` SDK) |

### Terraform Wiring

The email module is instantiated in each environment's `main.tf`:

```hcl
module "email" {
  source             = "../../modules/email"
  environment        = local.environment
  common_tags        = local.common_tags
  resend_secret_name = "resend_dev_key"
  resend_from_email  = "onboarding@resend.dev"
}

resource "aws_iam_role_policy_attachment" "lambda_resend_secrets" {
  role       = module.core.lambda_role_name
  policy_arn = module.email.resend_secrets_policy_arn
}
```

The Resend env vars are injected via `lambda_function_env_vars`:

```hcl
waitlist_handler = {
  RESEND_API_KEY_ARN = module.email.resend_api_key_arn
  RESEND_FROM_EMAIL  = module.email.resend_from_email
}
```

---

## Testing

### Unit Tests (49 tests, moto-mocked)

The `TestEmailIntegration` class in `tests/test_waitlist_handler.py` covers:

| Test | What it verifies |
|------|-----------------|
| `test_welcome_email_sent_on_signup` | Welcome email called with correct args after 201 |
| `test_welcome_email_not_sent_on_duplicate` | No email on 409 (duplicate) |
| `test_welcome_email_not_sent_on_validation_error` | No email on 400 |
| `test_referral_email_sent_to_referrer` | Tier unlocked email sent at threshold |
| `test_referral_success_email_when_no_tier_unlocked` | Referral success email between tiers |
| `test_email_failure_does_not_block_signup` | Signup returns 201 even if email throws |
| `test_referral_email_failure_does_not_block_credit` | Referral credit applied even if email throws |

The unit tests pre-mock `utils.email_service` via `sys.modules` before importing the handler, avoiding any Secrets Manager calls during testing.

### E2E Tests (36 tests, live API)

The `TestEmailDelivery` class in `tests/e2e/test_waitlist_e2e.py`:

- Signs up `buffett.dev117@gmail.com` against the live dev API
- Verifies signup returns 201 with a valid referral code
- Fetches the Resend API key from Secrets Manager
- Queries the Resend API to confirm the welcome email was queued

---

## Domain Migration Checklist

When a custom domain is purchased and verified in Resend:

1. **Verify domain in Resend dashboard** (add DNS records: SPF, DKIM, DMARC)
2. **Update Terraform variable** in each environment's `main.tf`:
   ```hcl
   resend_from_email = "hello@yourdomain.com"
   ```
3. **Run `terraform plan` and `terraform apply`** to push the new sender address to Lambda
4. **No code changes required** -- the sender address is read from the `RESEND_FROM_EMAIL` env var

---

## Operational Notes

- **Rate limiting**: Signup rate is capped at 5 per IP per hour. Rate limit entries are stored in the same DynamoDB waitlist table with a `rate:{ip}` key and a 1-hour TTL.
- **Resend free tier**: 100 emails/day, 3,000/month. Sufficient for development. Upgrade to a paid plan before launch.
- **Monitoring**: Email send failures are logged as warnings in CloudWatch. No alerting is configured yet.
- **Secret rotation**: If the Resend API key is rotated, update the value in Secrets Manager (`resend_dev_key`). The Lambda will pick up the new key on next cold start (the `@lru_cache` persists only for the lifetime of the Lambda execution environment).
