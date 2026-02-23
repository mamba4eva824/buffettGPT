# Buffett Landing Page — Pre-Launch Checklist

## Launch Blockers

- [ ] **Purchase + configure custom domain** — CloudFront currently uses `cloudfront_default_certificate = true` with no `aliases`. You need an ACM certificate, DNS records, and CloudFront alias configuration before the site is reachable at a real URL.
- [ ] **Wire email module into staging/prod Terraform** — `module "email"` only exists in `chat-api/terraform/environments/dev/main.tf`. Staging and prod have no `RESEND_API_KEY_ARN` or `RESEND_FROM_EMAIL` set, so all waitlist emails are silently dropped. Copy the email module block + IAM attachment to both environments.
- [ ] **Create Resend secret in staging/prod** — The `resend_dev_key` secret only exists in dev. You'll need environment-specific secrets once you have a verified sending domain.
- [ ] **Verify sending domain in Resend** — Currently sending from `onboarding@resend.dev` (sandbox). Add SPF, DKIM, and DMARC records for your custom domain, then update `resend_from_email` in Terraform.

## Content / UX Fixes

- [x] **Fix referral tier mismatch on frontend** — Updated both `WaitlistPage.jsx` and `TierProgress.jsx` to use threshold 5 (matching backend `REFERRAL_TIERS`).
- [x] **Update OG/meta tags in index.html** — Updated to "Buffett — Investment Research in Plain English" with new description. OG and Twitter cards updated.
- [x] **Add analytics** — GA4 added to `index.html` with Measurement ID `G-70S1T6DZHC`. Verified working in dev.

## CAN-SPAM / Email Compliance

- [x] **Add unsubscribe footer to welcome email** — All 3 email templates (`send_welcome_email`, `send_referral_success_email`, `send_tier_unlocked_email`) now include `_unsubscribe_footer()`.
- [x] **Build the unsubscribe route** — Backend handler `handle_unsubscribe` exists in `waitlist_handler.py`. API Gateway route `GET /waitlist/unsubscribe` is wired in `api-gateway/main.tf`. HMAC token verification + `email_opted_out` flag all functional (6 unit tests pass).
- [x] **Set `UNSUBSCRIBE_SECRET` env var** — Resolved via `JWT_SECRET_ARN` in `lambda_common_env_vars`, which is available to all Lambdas including waitlist_handler. The `_get_unsubscribe_secret()` function uses this as the primary source. No dev-fallback remains.
- [ ] **Add physical mailing address to email templates** — Placeholder address added to `_unsubscribe_footer()` in `email_service.py`. **TODO: Replace `"Buffett, 123 Main St, Suite 100, City, ST 00000"` with your real PO Box before launch.**

## Security / Infrastructure

- [x] **Restrict CORS on status endpoint** — `handle_status()` now returns `Access-Control-Allow-Origin: {FRONTEND_URL}` instead of `*`. Signup and OPTIONS still use `*` for broad access.
- [x] **Add email length validation** — Added `len(email) > 254` check before regex validation in `handle_signup()`. Returns 400 "Email too long".
- [x] **Enable CI tests** — Replaced disabled frontend test placeholder with `test-backend` job (Python `make test`) in both `deploy-staging.yml` and `deploy-prod.yml`. Infrastructure deployment now depends on tests passing.
- [x] **Use `npm ci` in CI** — Both staging and prod `build-frontend` jobs now use `npm ci` for reproducible builds.

## Performance / Scalability (Pre-Viral)

- [ ] **Replace DynamoDB Scan for queue position** — `_get_queue_position()` does a full table scan on every signup and every status check. Fine under 50K users (per the code comment), but a viral referral loop could blow past that quickly. Consider a counter attribute or GSI on `created_at`.
- [ ] **Verify Resend plan limits** — Free tier is 100 emails/day, 3K/month. If your launch gets traction (e.g., HN front page), you'll hit that within hours. Upgrade to a paid plan before launch day.

## Nice-to-Haves

- [ ] **Add email preview text** — Hidden snippet text that shows in inbox previews. Improves open rates.
- [ ] **Add plain-text email alternative** — HTML-only emails score lower with some spam filters.
- [ ] **Add `<link rel="canonical">` to index.html** — Prevents duplicate content if CloudFront URL and custom domain both resolve.
- [ ] **Add post-deploy smoke test to CI** — The workflows print a curl command but don't execute it. Add a health check step.
- [x] **Disable `VITE_ENABLE_DEBUG_LOGS` in staging** — Changed from `true` to `false` in `deploy-staging.yml`.

---

## Priority Summary

The **top 4** are genuine launch blockers (domain, email in prod, Resend domain verification, frontend tier mismatch). Everything else is important but can be addressed in a fast follow if you need to ship quickly.

## Key File References

| Area | File |
|------|------|
| Frontend waitlist page | `frontend/src/components/waitlist/WaitlistPage.jsx` |
| OG/meta tags | `frontend/index.html` |
| Waitlist handler (backend) | `chat-api/backend/src/handlers/waitlist_handler.py` |
| Email service | `chat-api/backend/src/utils/email_service.py` |
| Email Terraform module | `chat-api/terraform/modules/email/` |
| Dev environment config | `chat-api/terraform/environments/dev/main.tf` |
| Staging environment config | `chat-api/terraform/environments/staging/main.tf` |
| Prod environment config | `chat-api/terraform/environments/prod/main.tf` |
| CloudFront module | `chat-api/terraform/modules/cloudfront-static-site/main.tf` |
| Prod deploy workflow | `.github/workflows/deploy-prod.yml` |
| Staging deploy workflow | `.github/workflows/deploy-staging.yml` |
| Unit tests | `chat-api/backend/tests/test_waitlist_handler.py` |
| E2E tests | `chat-api/backend/tests/e2e/test_waitlist_e2e.py` |
