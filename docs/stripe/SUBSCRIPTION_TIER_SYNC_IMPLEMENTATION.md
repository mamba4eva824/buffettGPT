# Implementation Plan: Subscription Tier Sync Fix

> **Purpose:** Fix `subscription.updated` handler with robust dual-table sync
> **Workflow:** RALF (Review-Audit-Loop-Fix)
> **Created:** 2026-02-04
> **Status:** Ready for Implementation

---

## Problem Statement

The `handle_subscription_updated()` function in `stripe_webhook_handler.py` does not sync `subscription_tier`. The `subscription_tier` field exists in both the users table and token-usage table but lacks proper synchronization.

**Impact:** If `subscription.created` webhook fails, subsequent `subscription.updated` events won't fix the tier. Users may be stuck with incorrect tier despite having an active subscription.

**Root Cause:** Missing tier sync logic in `handle_subscription_updated()` handler.

---

## Solution: Robust Dual-Table Sync with Error Handling

### Decision Rationale

| Option | Description | Chosen |
|--------|-------------|--------|
| A | Full merge into users table | No - loses time-series data |
| B | Remove tier from token-usage | No - requires schema change |
| C | Single-table DynamoDB design | No - significant refactor |
| **D** | Keep both tables, add robust sync | **Yes** |

**Why Option D:**
- Minimal schema changes (no table modifications)
- Maintains existing data model
- Adds error handling to prevent sync drift
- Users table is authoritative; token-usage syncs from it
- Retry logic ensures eventual consistency

### Sync Strategy

```
┌─────────────────────┐
│  Stripe Webhook     │
│  (subscription.*)   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  1. Update Users    │◄── Primary (authoritative)
│     Table           │
└──────────┬──────────┘
           │ on success
           ▼
┌─────────────────────┐
│  2. Sync Token      │◄── Secondary (derived)
│     Usage Table     │
└──────────┬──────────┘
           │ on failure
           ▼
┌─────────────────────┐
│  3. Log Error +     │
│     Continue        │◄── Don't fail webhook
└─────────────────────┘
```

**Key Principles:**
1. Users table is the **source of truth** for `subscription_tier`
2. Token-usage table sync is **best-effort** (errors logged, not thrown)
3. `token_limit` is the **functional constraint** for access control
4. Webhook handler returns 200 even if token-usage sync fails (prevents Stripe retries)

---

## Acceptance Criteria

### AC-1: subscription.updated syncs tier to users table
- **Given:** A `subscription.updated` webhook with `status=active`
- **When:** Handler processes the event
- **Then:** User's `subscription_tier` is set to `plus` in users table

### AC-2: subscription.updated syncs tier to token-usage table
- **Given:** A `subscription.updated` webhook with `status=active`
- **When:** Handler processes the event
- **Then:** Current billing period's `subscription_tier` is set to `plus` in token-usage table

### AC-3: subscription.updated handles canceled status
- **Given:** A `subscription.updated` webhook with `status=canceled`
- **When:** Handler processes the event
- **Then:** User's `subscription_tier` is set to `free` in BOTH tables

### AC-4: past_due status preserves tier (grace period)
- **Given:** A `subscription.updated` webhook with `status=past_due`
- **When:** Handler processes the event
- **Then:** User's `subscription_tier` remains `plus` (no change to either table)

### AC-5: cancel_at_period_end preserves tier
- **Given:** A `subscription.updated` webhook with `cancel_at_period_end=true` and `status=active`
- **When:** Handler processes the event
- **Then:** User's `subscription_tier` remains `plus` (until actual deletion)

### AC-6: Token-usage sync failure does not fail webhook
- **Given:** Users table update succeeds but token-usage update fails
- **When:** Handler processes the event
- **Then:** Handler returns 200, error is logged, users table has correct tier

### AC-7: Sync helper is reusable
- **Given:** A new `_sync_subscription_tier()` helper function
- **When:** Called from any webhook handler
- **Then:** Both tables are updated consistently with proper error handling

### AC-8: Unit tests pass
- **Given:** All code changes complete
- **When:** `cd chat-api/backend && make test`
- **Then:** All tests pass including new tier sync tests

### AC-9: E2E cancellation tests pass
- **Given:** Changes deployed to dev
- **When:** RALF workflow from `CANCELLATION_TESTING_GUIDE.md` executed
- **Then:** All 7 tasks pass

---

## Implementation Tasks

Execute these tasks in order using RALF methodology.

### Task 1: Read current implementation
**Files to read:**
- `chat-api/backend/src/handlers/stripe_webhook_handler.py` (full file)
- `chat-api/backend/src/utils/token_usage_tracker.py` (focus on tier-related methods)

**Understand:**
1. Current `handle_subscription_updated()` logic
2. How other handlers sync tier (e.g., `handle_checkout_completed`)
3. Token usage table access patterns

**Verify:** Document current behavior and identify all places tier is written.

---

### Task 2: Create _sync_subscription_tier() helper function
**File:** `chat-api/backend/src/handlers/stripe_webhook_handler.py`

**Create a reusable helper:**
```python
def _sync_subscription_tier(
    user_id: str,
    subscription_tier: str,
    billing_day: Optional[int] = None
) -> bool:
    """
    Sync subscription_tier to both users and token-usage tables.

    Args:
        user_id: User identifier
        subscription_tier: 'plus' or 'free'
        billing_day: Day of month for billing (needed for token-usage lookup)

    Returns:
        True if both updates succeeded, False if token-usage sync failed
        (users table failure raises exception)
    """
    # 1. Update users table (authoritative - must succeed)
    users_table.update_item(
        Key={'user_id': user_id},
        UpdateExpression='SET subscription_tier = :tier, updated_at = :ts',
        ExpressionAttributeValues={
            ':tier': subscription_tier,
            ':ts': datetime.now(timezone.utc).isoformat()
        }
    )

    # 2. Sync token-usage table (best-effort)
    try:
        if billing_day:
            # Calculate current billing period
            billing_period = _get_current_billing_period(billing_day)
            token_usage_table.update_item(
                Key={'user_id': user_id, 'billing_period': billing_period},
                UpdateExpression='SET subscription_tier = :tier',
                ExpressionAttributeValues={':tier': subscription_tier},
                ConditionExpression='attribute_exists(user_id)'  # Only if record exists
            )
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            # No token usage record yet - that's OK
            logger.info(f"No token usage record to sync for user {user_id}")
            return True
        logger.error(f"Failed to sync token-usage tier for {user_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error syncing token-usage tier for {user_id}: {e}")
        return False
```

**Verify:** Helper function handles all error cases gracefully.

---

### Task 3: Update handle_subscription_updated() to use sync helper
**File:** `chat-api/backend/src/handlers/stripe_webhook_handler.py`

**Changes:**
1. Determine tier based on subscription status
2. Call `_sync_subscription_tier()` for tier changes
3. Continue updating other fields (status, cancel_at_period_end)

**Logic:**
```python
def handle_subscription_updated(subscription: Dict[str, Any]) -> None:
    subscription_id = subscription.get('id')
    customer_id = subscription.get('customer')
    status = subscription.get('status')
    cancel_at_period_end = subscription.get('cancel_at_period_end', False)

    # Find user
    user = _find_user_by_customer_id(customer_id)
    if not user:
        logger.error(f"No user found for customer {customer_id}")
        return

    user_id = user['user_id']
    billing_day = user.get('billing_day')

    # Determine if tier should change
    new_tier = None
    if status in ('active', 'trialing'):
        new_tier = 'plus'
    elif status == 'canceled':
        new_tier = 'free'
    # past_due, incomplete, etc. → no tier change (grace period)

    # Sync tier if it should change
    if new_tier:
        sync_success = _sync_subscription_tier(user_id, new_tier, billing_day)
        if not sync_success:
            logger.warning(f"Token-usage tier sync failed for {user_id}, continuing...")

    # Update other subscription fields in users table
    users_table.update_item(
        Key={'user_id': user_id},
        UpdateExpression='''
            SET subscription_status = :status,
                cancel_at_period_end = :cancel,
                updated_at = :ts
        ''',
        ExpressionAttributeValues={
            ':status': status,
            ':cancel': cancel_at_period_end,
            ':ts': datetime.now(timezone.utc).isoformat()
        }
    )

    logger.info(f"Updated subscription for user {user_id}: status={status}, tier={new_tier or 'unchanged'}")
```

**Verify:** Handler syncs tier to both tables on status changes.

---

### Task 4: Update other handlers to use sync helper (if needed)
**File:** `chat-api/backend/src/handlers/stripe_webhook_handler.py`

**Review and potentially update:**
- `handle_checkout_completed()` - may already handle tier correctly
- `handle_subscription_created()` - may already handle tier correctly
- `handle_subscription_deleted()` - ensure it uses sync helper for consistency

**Verify:** All handlers use consistent tier sync logic.

---

### Task 5: Add _get_current_billing_period() helper (if not exists)
**File:** `chat-api/backend/src/handlers/stripe_webhook_handler.py`

**Create helper to calculate billing period key:**
```python
def _get_current_billing_period(billing_day: int) -> str:
    """
    Calculate current billing period start date in YYYY-MM-DD format.

    Args:
        billing_day: Day of month when billing period starts (1-31)

    Returns:
        Billing period start date string
    """
    now = datetime.now(timezone.utc)
    billing_day = max(1, min(31, billing_day))

    # Get last day of current month
    last_day = calendar.monthrange(now.year, now.month)[1]
    effective_day = min(billing_day, last_day)

    # Determine if we're before or after this month's billing day
    if now.day >= effective_day:
        # Current period started this month
        period_start = now.replace(day=effective_day)
    else:
        # Current period started last month
        if now.month == 1:
            prev_month = now.replace(year=now.year - 1, month=12)
        else:
            prev_month = now.replace(month=now.month - 1)
        prev_last_day = calendar.monthrange(prev_month.year, prev_month.month)[1]
        period_start = prev_month.replace(day=min(billing_day, prev_last_day))

    return period_start.strftime('%Y-%m-%d')
```

**Verify:** Correctly calculates billing period for edge cases (Feb 28, month boundaries).

---

### Task 6: Add/update unit tests
**File:** `chat-api/backend/tests/unit/test_stripe_webhook.py`

**New tests needed:**
1. `test_subscription_updated_active_syncs_tier_to_both_tables`
2. `test_subscription_updated_canceled_syncs_tier_to_both_tables`
3. `test_subscription_updated_past_due_preserves_tier`
4. `test_subscription_updated_trialing_sets_tier_plus`
5. `test_sync_tier_token_usage_failure_does_not_raise`
6. `test_sync_tier_no_token_usage_record_succeeds`
7. `test_get_current_billing_period_edge_cases`

**Verify:** All new tests pass.

---

### Task 7: Run unit tests
**Command:**
```bash
cd chat-api/backend && make test
```

**Verify:** All tests pass (0 failures).

---

### Task 8: Build Lambda packages
**Command:**
```bash
cd chat-api/backend && ./scripts/build_lambdas.sh
```

**Verify:** Build completes successfully, `stripe_webhook_handler.zip` created in `build/`.

---

### Task 9: Deploy to dev via Terraform
**Commands:**
```bash
cd chat-api/terraform/environments/dev
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

**Verify:** Lambda updated successfully, no errors.

---

### Task 10: Execute E2E tests
**Guide:** `docs/stripe/CANCELLATION_TESTING_GUIDE.md`

Execute all 7 tasks from the testing guide to verify the fix works end-to-end.

**Additional verification:**
- Check token-usage table has correct `subscription_tier` after each operation
- Verify CloudWatch logs show sync operations

**Verify:** All 7 tasks pass, both tables in sync.

---

### Task 11: Update documentation
**File:** `docs/stripe/CANCELLATION_TESTING_GUIDE.md`

**Changes:**
1. Update Known Issues section - mark issue as RESOLVED
2. Add changelog entry for the fix
3. Update test results with new run
4. Add verification step for token-usage table tier

---

## Files to Modify

| File | Purpose |
|------|---------|
| `chat-api/backend/src/handlers/stripe_webhook_handler.py` | Add `_sync_subscription_tier()` helper, update `handle_subscription_updated()` |
| `chat-api/backend/tests/unit/test_stripe_webhook.py` | Add tests for sync logic and error handling |
| `docs/stripe/CANCELLATION_TESTING_GUIDE.md` | Mark issue resolved, update test results |

---

## Error Handling Matrix

| Scenario | Users Table | Token-Usage Table | Webhook Response | Action |
|----------|-------------|-------------------|------------------|--------|
| Both succeed | Updated | Updated | 200 | None |
| Users succeeds, Token fails | Updated | Stale | 200 | Log error |
| Users fails | Not updated | Not attempted | 500 | Stripe retries |
| User not found | N/A | N/A | 200 | Log warning |

**Rationale:** Users table is authoritative. If it updates successfully, the webhook succeeded. Token-usage sync failure is logged but doesn't fail the webhook to prevent infinite Stripe retries.

---

## Verification Commands

```bash
# Unit tests
cd chat-api/backend && make test

# Build
cd chat-api/backend && ./scripts/build_lambdas.sh

# Deploy
cd chat-api/terraform/environments/dev && terraform apply

# Check CloudWatch logs after E2E test
aws logs tail /aws/lambda/buffett-dev-stripe-webhook-handler --follow

# Verify token-usage table after test
aws dynamodb query \
  --table-name token-usage-dev-buffett \
  --key-condition-expression "user_id = :uid" \
  --expression-attribute-values '{":uid":{"S":"test-cancel-flow-user"}}' \
  --projection-expression "user_id, billing_period, subscription_tier, token_limit"
```

---

## Rollback Plan

If issues are discovered after deployment:

1. Revert code changes in `stripe_webhook_handler.py`
2. Rebuild Lambda: `./scripts/build_lambdas.sh`
3. Redeploy: `terraform apply`
4. Manually fix any affected user records in DynamoDB:
```bash
# Fix users table
aws dynamodb update-item \
  --table-name buffett-dev-users \
  --key '{"user_id":{"S":"USER_ID"}}' \
  --update-expression "SET subscription_tier = :tier" \
  --expression-attribute-values '{":tier":{"S":"plus"}}'

# Fix token-usage table (for current billing period)
aws dynamodb update-item \
  --table-name token-usage-dev-buffett \
  --key '{"user_id":{"S":"USER_ID"}, "billing_period":{"S":"YYYY-MM-DD"}}' \
  --update-expression "SET subscription_tier = :tier" \
  --expression-attribute-values '{":tier":{"S":"plus"}}'
```

---

## Related Documents

| Document | Purpose |
|----------|---------|
| `docs/stripe/ARCHITECTURE.md` | System architecture |
| `docs/stripe/CANCELLATION_TESTING_GUIDE.md` | E2E testing guide |
| `chat-api/terraform/modules/dynamodb/token_usage.tf` | Token usage table schema |
| `chat-api/backend/src/utils/token_usage_tracker.py` | Token tracking utilities |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-02-04 | Created implementation plan (Option B) |
| 2026-02-04 | Revised to Option D: Keep both tables with robust sync |
