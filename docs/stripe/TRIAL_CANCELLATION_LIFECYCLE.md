# Trial Cancellation Lifecycle — Executive Report

> **Date:** 2026-03-03
> **Status:** Implemented & Tested
> **Scope:** Referral trial expiration, billing transition, payment failure, and cancellation flows

---

## Overview

When a user activates a referral trial (via the waitlist referral system), they enter a `trialing/plus` state with a 30- or 90-day free trial on the Plus tier. This document covers every state transition that can occur after trial activation, the webhook events that trigger them, and the DynamoDB mutations that result.

---

## State Machine

```
                         checkout.session.completed
                         (referral_trial_days > 0)
                                   │
                                   ▼
                        ┌─────────────────────┐
                        │  TRIALING / PLUS     │
                        │  token_limit: 2M     │
                        └──────┬──────┬────────┘
                               │      │
          subscription.updated │      │ subscription.deleted
          (status=active)      │      │ (immediate cancel)
                               │      │
                               ▼      ▼
                  ┌────────────────┐  ┌──────────────────┐
                  │ ACTIVE / PLUS  │  │ CANCELED / FREE   │
                  │ token_limit: 2M│  │ token_limit: 100K │
                  └───┬────┬───────┘  │ sub_id: removed   │
                      │    │          └──────────────────┘
                      │    │                    ▲
   invoice.           │    │ subscription.      │
   payment_failed     │    │ updated            │
                      │    │ (cancel_at_         │
                      ▼    │  period_end=true)   │
         ┌──────────────┐  │                    │
         │ PAST_DUE /   │  ▼                    │
         │ FREE         │ ┌─────────────────┐   │
         │ token_limit:  │ │ ACTIVE / PLUS   │   │
         │ 100K         │ │ cancel_at_period │   │
         └──────┬───────┘ │ _end=true       │   │
                │         └────────┬────────┘   │
  invoice.      │                  │            │
  payment_      │    subscription. │            │
  succeeded     │    deleted       │            │
                ▼                  ▼            │
  ┌──────────────┐    ┌──────────────────┐     │
  │ ACTIVE / PLUS│    │ CANCELED / FREE   │─────┘
  │ token_limit: │    │ token_limit: 100K │
  │ 2M (restored)│    │ sub_id: removed   │
  └──────────────┘    └──────────────────┘
```

---

## Lifecycle Paths

### Path 1: Trial Expires → Billing Begins (Happy Path)

| Step | Stripe Event | Handler | State Change |
|------|-------------|---------|-------------|
| 1 | `checkout.session.completed` | `handle_checkout_completed` | `free` → `trialing/plus`, token_limit=2M |
| 2 | `customer.subscription.updated` (status=active) | `handle_subscription_updated` | `trialing` → `active`, tier stays `plus` |

**DynamoDB mutations (Step 2):**
- `users`: `subscription_status=active`, `subscription_tier=plus` (via `_sync_subscription_tier`)
- `token-usage`: `subscription_tier=plus`, `token_limit=2000000` (preserved)

**Key behavior:** Token usage counts are preserved across the trialing→active transition. The billing period does not reset.

---

### Path 2: Payment Fails After Trial

| Step | Stripe Event | Handler | State Change |
|------|-------------|---------|-------------|
| 1 | `checkout.session.completed` | `handle_checkout_completed` | `free` → `trialing/plus` |
| 2 | `invoice.payment_failed` | `handle_invoice_failed` | `trialing/plus` → `past_due/free`, token_limit=100K |

**DynamoDB mutations (Step 2):**
- `users`: `subscription_tier=free` (via `_sync_subscription_tier`), `subscription_status=past_due`, `payment_failed_at` set
- `token-usage`: `subscription_tier=free`, `token_limit=100000`

**Key behavior:** There is no grace period. Payment failure immediately downgrades the user to the free tier and reduces their token limit to 100K.

**Recovery path:** If Stripe retries and `invoice.payment_succeeded` fires, the handler restores `subscription_tier=plus`, `subscription_status=active`, and `token_limit=2000000`.

---

### Path 3: Cancel at Period End

| Step | Stripe Event | Handler | State Change |
|------|-------------|---------|-------------|
| 1 | `checkout.session.completed` | `handle_checkout_completed` | `free` → `trialing/plus` |
| 2 | `customer.subscription.updated` (status=active, cancel_at_period_end=true) | `handle_subscription_updated` | `cancel_at_period_end=true`, tier stays `plus` |
| 3 | `customer.subscription.deleted` (at period end) | `handle_subscription_deleted` | `plus` → `free`, status=`canceled`, sub_id removed |

**DynamoDB mutations (Step 2):**
- `users`: `subscription_status=active`, `cancel_at_period_end=true`
- No tier change (user retains Plus until period ends)

**DynamoDB mutations (Step 3):**
- `users`: `subscription_tier=free` (via `_sync_subscription_tier`), `subscription_status=canceled`, `subscription_canceled_at` set, `stripe_subscription_id` REMOVED
- `token-usage`: `subscription_tier=free`, `token_limit=100000`

**Key behavior:** The user retains full Plus access until the billing period ends. Only when Stripe fires `subscription.deleted` does the downgrade occur.

---

### Path 4: Immediate Cancellation During Trial

| Step | Stripe Event | Handler | State Change |
|------|-------------|---------|-------------|
| 1 | `checkout.session.completed` | `handle_checkout_completed` | `free` → `trialing/plus` |
| 2 | `customer.subscription.deleted` | `handle_subscription_deleted` | `plus` → `free`, status=`canceled` |

**DynamoDB mutations (Step 2):**
- `users`: `subscription_tier=free`, `subscription_status=canceled`, `subscription_canceled_at` set, `stripe_subscription_id` REMOVED
- `token-usage`: `subscription_tier=free`, `token_limit=100000`

**Key behavior:** Immediate downgrade. No intermediate `subscription.updated` event — Stripe fires `subscription.deleted` directly.

---

## Field-Level Reference

### Users Table Mutations by Event

| Field | checkout.completed | sub.updated (active) | sub.updated (cancel_end) | sub.deleted | invoice.failed | invoice.succeeded |
|-------|-------------------|---------------------|--------------------------|-------------|----------------|-------------------|
| `subscription_tier` | `plus` | `plus` | *unchanged* | `free` | `free` | `plus` |
| `subscription_status` | `trialing`/`active` | `active` | `active` | `canceled` | `past_due` | `active` |
| `stripe_customer_id` | set | — | — | — | — | — |
| `stripe_subscription_id` | set | — | — | **REMOVED** | — | — |
| `cancel_at_period_end` | — | `false` | `true` | — | — | — |
| `billing_day` | set | — | — | — | — | — |
| `payment_failed_at` | — | — | — | — | set | — |
| `subscription_canceled_at` | — | — | — | set | — | — |
| `last_payment_at` | — | — | — | — | — | set |

### Token-Usage Table Mutations by Event

| Field | checkout.completed | sub.updated | sub.deleted | invoice.failed | invoice.succeeded |
|-------|-------------------|-------------|-------------|----------------|-------------------|
| `subscription_tier` | `plus` | synced | `free` | `free` | `plus` |
| `token_limit` | `2000000` | synced | `100000` | `100000` | `2000000` |
| `total_tokens` | `0` (initialized) | *preserved* | *preserved* | *preserved* | `0` (reset) |

---

## Waitlist / Referral Data Preservation

Referral claim data on the waitlist record is **never modified** by post-checkout events. Regardless of cancellation, payment failure, or resubscription, the following fields are preserved:

| Field | Set by | Preserved through |
|-------|--------|------------------|
| `referral_claimed_at` | `checkout.session.completed` | All lifecycle events |
| `referral_claimed_by` | `checkout.session.completed` | All lifecycle events |
| `referral_trial_days_granted` | `checkout.session.completed` | All lifecycle events |

This ensures referral analytics remain accurate even after a user cancels.

---

## Test Coverage

**Total: 24 E2E/integration tests across 6 test classes**

### Referral Checkout Flow (`TestReferralCheckoutE2E` — 5 tests)

| Test | Scenario |
|------|----------|
| `test_3_referrals_full_flow_30_day_trial` | 3 referrals → 30-day trial, full checkout+webhook flow |
| `test_5_referrals_full_flow_90_day_trial` | 5 referrals → 90-day trial, full checkout+webhook flow |
| `test_fewer_than_3_referrals_no_trial` | <3 referrals → no trial, status=active (not trialing) |
| `test_webhook_marks_referral_claimed` | Webhook sets `referral_claimed_at` on waitlist record |
| `test_double_claim_prevention_no_trial_on_second_checkout` | Already-claimed referral gets no trial on second checkout |

### Trial Lifecycle (`TestReferralTrialLifecycleE2E` — 5 tests)

| Test | Path | Events Chained |
|------|------|---------------|
| `test_trial_to_active_billing_transition` | Path 1 | checkout → sub.updated(active) |
| `test_trial_payment_failed` | Path 2 | checkout → invoice.failed |
| `test_cancel_at_period_end_during_trial` | Path 3 (partial) | checkout → sub.updated(cancel_end) |
| `test_immediate_cancellation_during_trial` | Path 4 | checkout → sub.deleted |
| `test_full_lifecycle_referral_to_cancel` | Path 3 (full) | checkout → sub.updated(cancel_end) → sub.deleted |

### Payment Recovery (`TestPaymentRecoveryE2E` — 2 tests)

| Test | Path | Events Chained |
|------|------|---------------|
| `test_trial_payment_fail_then_recovery` | Path 2 + recovery | checkout → invoice.failed → invoice.succeeded |
| `test_resubscription_after_cancellation_no_referral` | Re-sub (no referral) | seed canceled user → checkout.completed (active) |

### Webhook Error Handling (`TestWebhookErrorHandlingE2E` — 3 tests)

| Test | Scenario |
|------|----------|
| `test_checkout_no_user_id_anywhere_returns_200_no_writes` | No user_id in session → 200, no DB writes, event marked processed |
| `test_checkout_nonexistent_user_returns_500` | Ghost user_id → 500 (ValueError), no user created, event NOT marked processed |
| `test_duplicate_event_replay_returns_already_processed` | Same event_id replayed → second call returns `already_processed`, user unchanged |

### Referral Boundary Values (`TestReferralBoundaryE2E` — 4 tests)

| Test | Scenario |
|------|----------|
| `test_0_referrals_no_trial_no_error` | 0 referrals → no trial, no error |
| `test_4_referrals_gets_30_day_trial` | 4 referrals → 30-day trial (not 90) |
| `test_5_referrals_gets_90_day_trial` | 5 referrals → 90-day trial |
| `test_email_not_in_waitlist_no_trial_no_error` | Email not in waitlist → no trial, no error |

### Invoice Edge Cases (`TestInvoiceEdgeCasesE2E` — 4 tests)

| Test | Scenario |
|------|----------|
| `test_initial_subscription_invoice_skipped` | `billing_reason=subscription_create` → skipped, no state changes |
| `test_renewal_after_past_due_recovery` | Renewal payment restores past_due/free → active/plus, token_limit=2M |
| `test_payment_failure_no_billing_day` | No `billing_day` on user → token-usage sync skipped gracefully, users table still updated |
| `test_non_subscription_invoice_skipped` | `subscription=None` → skipped entirely, no DB writes |

### Integration Tests (`test_stripe_cancellation_lifecycle.py`)

| Test | Scenario |
|------|----------|
| `test_payment_failure_then_success_lifecycle` | Path 2 + recovery |
| `test_exhausted_payment_retries_then_canceled` | Path 2 → Path 4 |
| `test_full_cancellation_lifecycle_cancel_at_period_end` | Path 3 |
| `test_immediate_cancellation` | Path 4 |

---

## Handler Code References

| Handler | File | Line |
|---------|------|------|
| `handle_checkout_completed` | `chat-api/backend/src/handlers/stripe_webhook_handler.py` | ~120 |
| `handle_subscription_updated` | `chat-api/backend/src/handlers/stripe_webhook_handler.py` | ~445 |
| `handle_subscription_deleted` | `chat-api/backend/src/handlers/stripe_webhook_handler.py` | ~392 |
| `handle_invoice_failed` | `chat-api/backend/src/handlers/stripe_webhook_handler.py` | ~339 |
| `handle_invoice_paid` | `chat-api/backend/src/handlers/stripe_webhook_handler.py` | ~280 |
| `_sync_subscription_tier` | `chat-api/backend/src/handlers/stripe_webhook_handler.py` | ~590 |

---

## Safety Mechanisms

| Mechanism | Implementation | Tested By |
|-----------|---------------|-----------|
| **Idempotency** | Event ID tracked in `processed_events_table`; duplicate events return `already_processed` | `test_duplicate_event_replay_returns_already_processed` |
| **Ghost user protection** | `handle_checkout_completed` verifies user exists before updating; returns 500 if missing (triggers Stripe retry) | `test_checkout_nonexistent_user_returns_500` |
| **Double-claim prevention** | `attribute_not_exists(referral_claimed_at)` condition on waitlist update | `test_double_claim_prevention_no_trial_on_second_checkout` |
| **Missing billing_day tolerance** | `_sync_subscription_tier` skips token-usage sync when `billing_day=None` | `test_payment_failure_no_billing_day` |
| **Non-subscription invoice skip** | `handle_invoice_failed` / `handle_invoice_paid` return early when `subscription=None` | `test_non_subscription_invoice_skipped` |
| **Initial invoice skip** | `handle_invoice_paid` returns early when `billing_reason=subscription_create` | `test_initial_subscription_invoice_skipped` |

---

## Change Log

| Date | Change |
|------|--------|
| 2026-03-03 | Added webhook error handling tests (no user_id, ghost user, idempotency) |
| 2026-03-03 | Added referral boundary value tests (0, 4, 5 referrals, no waitlist entry) |
| 2026-03-03 | Added invoice edge case tests (initial invoice skip, renewal recovery, no billing_day, non-subscription invoice) |
| 2026-03-03 | Added payment recovery E2E tests (trial → fail → recovery, re-subscription after cancellation) |
| 2026-03-03 | Added 5 referral trial lifecycle E2E tests |
| 2026-03-03 | Removed grace period: `invoice.payment_failed` now immediately downgrades to free tier |
| 2026-03-03 | Added tier restore: `invoice.payment_succeeded` now restores plus tier via `_sync_subscription_tier` |
| 2026-02-04 | Initial cancellation lifecycle implementation |
