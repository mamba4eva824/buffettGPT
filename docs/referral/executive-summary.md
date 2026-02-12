# BuffettGPT Viral Waitlist & Referral System

**Status:** Implementation Complete | Deployment Pending
**Date:** February 2026
**Author:** Engineering

---

## Overview

BuffettGPT's pre-launch growth strategy centers on a viral waitlist with a tiered referral reward system, modeled after Robinhood's pre-launch campaign. Users sign up with an email, receive a unique branded referral code, and earn escalating rewards as they refer friends.

The system is designed as a zero-friction funnel: no login required to join, one-click sharing, and automatic reward tracking.

---

## Referral Ladder

| Tier | Referrals Required | Reward | Value |
|------|-------------------|--------|-------|
| 1 | 1 referral | Early Access | Skip the waitlist |
| 2 | 3 referrals | 1 Month Free Plus | $10 |
| 3 | 10 referrals | 3 Months Free Plus | $30 |

The tier system is intentionally simple. Tier 1 (Early Access) is achievable by anyone willing to share once, creating a low barrier to viral spread. Tiers 2 and 3 reward power referrers with tangible subscription value.

---

## User Experience

### Signup Flow

1. User lands on the waitlist page (via direct URL, `?ref=CODE` link, or `#waitlist` hash)
2. Enters email address, optionally enters a referral code
3. Receives a unique referral code (e.g., `BUFF-A3X9`) and queue position
4. Dashboard appears with sharing tools and tier progress

### Returning Visitors

Email and referral code are persisted in `localStorage`. Returning visitors see their dashboard immediately without re-entering credentials.

### Referral Sharing

The dashboard provides:
- **Referral code** with one-click copy
- **Referral link** (`https://buffettgpt.com/?ref=BUFF-XXXX`) with copy button
- **Social sharing** buttons for X (Twitter) and LinkedIn with pre-filled messages

### Referral Link Behavior

When someone clicks a referral link (`?ref=BUFF-XXXX`), the landing page auto-fills the referral code input. If they sign up, the referrer's count increments and their tier status updates automatically.

---

## Architecture

### Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Tailwind CSS, lazy-loaded route in main app |
| API | AWS API Gateway v2 (HTTP), public endpoints (no auth) |
| Compute | AWS Lambda (Python 3.11), 256 MB, 30s timeout |
| Database | DynamoDB (on-demand), KMS encryption at rest |
| Infrastructure | Terraform, deployed via GitHub Actions CI/CD |

### Data Model

**DynamoDB Table:** `buffett-chat-api-{env}-waitlist`

| Field | Type | Description |
|-------|------|-------------|
| `email` | String (PK) | User's email address |
| `referral_code` | String (GSI) | Unique code, e.g. `BUFF-A3X9` |
| `referred_by_code` | String | Code of the person who referred them |
| `referral_count` | Number | How many people used this user's code |
| `status` | String | `waitlisted`, `early_access`, or `converted` |
| `created_at` | String | ISO timestamp, used for queue position |
| `ip_address` | String | For fraud detection |
| `ttl` | Number | TTL for rate-limit entries |

**Global Secondary Index:** `referral-code-index` on `referral_code` for O(1) referral lookups.

### API Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/waitlist/signup` | None | Register email, generate referral code |
| GET | `/waitlist/status` | Email + Code | Fetch position, referral count, tier progress |

Both endpoints include CORS preflight (OPTIONS) routes.

---

## Security & Fraud Prevention

| Control | Implementation |
|---------|---------------|
| Rate limiting | 5 signups per IP per hour (DynamoDB TTL entries) |
| Email validation | Regex format check + disposable domain blocklist (15 providers) |
| Self-referral prevention | Referral code lookup verifies different email |
| Duplicate prevention | Conditional put (`attribute_not_exists(email)`), returns 409 with existing code |
| IP tracking | Stored per signup for post-hoc fraud analysis |
| Lightweight auth | Status endpoint requires both email AND referral code |
| Data isolation | No way to enumerate other users' data |

---

## What's Implemented

### Backend (Complete)

- [x] Lambda handler with signup and status endpoints
- [x] Referral code generation (`BUFF-` + 4 alphanumeric chars, collision-resistant)
- [x] Referral credit logic with atomic DynamoDB updates
- [x] Auto-promotion to `early_access` at 1 referral
- [x] Rate limiting (IP-based, 5/hr)
- [x] Disposable email blocking
- [x] Self-referral prevention
- [x] Duplicate email handling (409 with code recovery)
- [x] Queue position calculation
- [x] Tier progress computation (current tier, next tier, referrals needed)

### Infrastructure (Complete)

- [x] DynamoDB table with GSI and TTL (`waitlist.tf`)
- [x] Table outputs exposed for cross-module reference
- [x] Lambda function config (256 MB, 30s timeout)
- [x] API Gateway integration with 4 routes
- [x] Feature flag (`enable_waitlist_routes`) for staged rollout
- [x] Dev environment wired (`WAITLIST_TABLE` env var, routes enabled)
- [x] Build script includes `waitlist_handler`
- [x] Existing CI/CD pipeline covers deployment (no custom steps needed)

### Frontend (Complete)

- [x] API client (`waitlistApi.js`) with signup and status methods
- [x] Landing page with hero section, email form, feature cards, tier preview
- [x] Referral dashboard with position badge, code/link copy, social sharing
- [x] TierProgress visual component (animated progress bar, milestone markers)
- [x] `localStorage` persistence for returning visitors
- [x] URL param detection (`?ref=CODE` auto-fills referral input)
- [x] Lazy-loaded via `React.lazy()` for zero impact on main app bundle
- [x] Feature flag (`VITE_ENABLE_WAITLIST`) for activation control
- [x] Dark mode support (warm/sand/rust palette)

---

## What's Remaining

### Must-Have Before Launch

| Item | Priority | Effort | Notes |
|------|----------|--------|-------|
| Deploy to dev | High | 15 min | `git push origin dev` triggers CI/CD |
| Set `VITE_ENABLE_WAITLIST=true` in env | High | 5 min | Add to `.env` files or CI/CD build args |
| Manual E2E smoke test | High | 30 min | Verify signup, referral credit, status, sharing |
| Update `FRONTEND_URL` in handler | High | 10 min | Currently defaults to `localhost:3000`; needs CloudFront URL via Terraform env var |

### Should-Have Before Launch

| Item | Priority | Effort | Notes |
|------|----------|--------|-------|
| Backend unit tests | Medium | 2-3 hrs | `test_waitlist_handler.py` with moto mocking |
| Post-deploy smoke test script | Medium | 30 min | Curl-based endpoint verification |
| Staging/prod environment wiring | Medium | 30 min | Add `WAITLIST_TABLE` + `enable_waitlist_routes` to staging/prod `main.tf` |

### Nice-to-Have (Post-Launch)

| Item | Priority | Effort | Notes |
|------|----------|--------|-------|
| Email notifications | Low | 1-2 days | SES integration for signup confirmation + referral alerts |
| Admin dashboard | Low | 1 day | View signups, referral leaderboard, manual promotions |
| Analytics events | Low | 2-3 hrs | Track signup, share, referral conversion rates |
| Expanded disposable email list | Low | 1 hr | Use external service or extended blocklist |
| Pre-computed queue positions | Low | 3-4 hrs | DynamoDB Streams + counter for O(1) position lookups at scale |
| Frontend component tests | Low | 2-3 hrs | Vitest + React Testing Library |
| Referral code length scaling | Low | 1 hr | 4 chars = 614K combinations; extend to 5-6 if approaching capacity |

---

## Scalability Considerations

**Current capacity:** The DynamoDB scan-based queue position calculation is acceptable for up to ~50,000 waitlist entries. Beyond that:

1. **Position calculation** becomes expensive. Mitigation: pre-compute positions via DynamoDB Streams or scheduled batch job.
2. **Referral code space** (4 alphanumeric chars = 614,656 combinations) is sufficient for early growth. The handler already has a fallback to 6-char codes if collisions occur at 10 retries.
3. **Rate limit entries** auto-clean via TTL, so no table bloat from rate limiting.

---

## File Reference

```
Backend
  chat-api/backend/src/handlers/waitlist_handler.py

Infrastructure
  chat-api/terraform/modules/dynamodb/waitlist.tf
  chat-api/terraform/modules/dynamodb/outputs.tf
  chat-api/terraform/modules/lambda/main.tf
  chat-api/terraform/modules/api-gateway/main.tf
  chat-api/terraform/modules/api-gateway/variables.tf
  chat-api/terraform/environments/dev/main.tf
  chat-api/backend/scripts/build_lambdas.sh

Frontend
  frontend/src/api/waitlistApi.js
  frontend/src/components/waitlist/WaitlistPage.jsx
  frontend/src/components/waitlist/TierProgress.jsx
  frontend/src/App.jsx
```
