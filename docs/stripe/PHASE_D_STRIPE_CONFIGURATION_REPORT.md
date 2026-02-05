# Phase D: Stripe Product & Price Configuration

## Executive Summary

Phase D configures the actual Stripe resources required for the BuffettGPT Plus subscription. Using the Stripe MCP server, this phase created the product definition and recurring price in Stripe's test environment. These resources represent the monetization foundation that connects Stripe Checkout to the backend subscription handlers built in Phase B.

**Completion Status**: All tasks (D1-D4) completed and verified via Stripe MCP.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Stripe Dashboard (Test Mode)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                           PRODUCT                                       │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │ │
│  │  │  Name:        Buffett Plus                                        │  │ │
│  │  │  ID:          prod_TuI3SR1TMzTPFt                                 │  │ │
│  │  │  Type:        Service                                             │  │ │
│  │  │  Description: Premium subscription with 2,000,000 tokens/month    │  │ │
│  │  │               for AI-powered investment analysis                  │  │ │
│  │  └──────────────────────────────────────────────────────────────────┘  │ │
│  │                               │                                         │ │
│  │                               ▼                                         │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │ │
│  │  │                           PRICE                                   │  │ │
│  │  │  ID:          price_1SwTUiGtKkLcbRiapMRnErLu                      │  │ │
│  │  │  Amount:      $10.00 USD                                          │  │ │
│  │  │  Billing:     Monthly recurring                                   │  │ │
│  │  │  Type:        Licensed (per seat)                                 │  │ │
│  │  └──────────────────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Integration Points                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Backend (Phase B)                     Infrastructure (Phase A)             │
│   ┌─────────────────────────┐          ┌─────────────────────────┐          │
│   │ stripe_service.py       │          │ AWS Secrets Manager     │          │
│   │ get_stripe_plus_price_id│◀─────────│ stripe-plus-price-id-dev│          │
│   │ create_checkout_session │          │ = price_1SwTUi...       │          │
│   └─────────────────────────┘          └─────────────────────────┘          │
│                                                                              │
│   Frontend (Phase E)                                                         │
│   ┌─────────────────────────┐                                               │
│   │ PricingModal.jsx        │                                               │
│   │ "Buffett Plus - $10/mo" │                                               │
│   └─────────────────────────┘                                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Task D1: Create Stripe Product

### MCP Tool Used: `mcp__stripe__create_product`

**Request**:
```json
{
  "name": "Buffett Plus",
  "description": "Premium subscription with 2,000,000 tokens/month for AI-powered investment analysis"
}
```

**Response**:
```json
{
  "id": "prod_TuI3SR1TMzTPFt",
  "object": "product",
  "active": true,
  "name": "Buffett Plus",
  "type": "service",
  "description": "Premium subscription with 2,000,000 tokens/month for AI-powered investment analysis",
  "livemode": false
}
```

### Product Configuration

| Property | Value | Rationale |
|----------|-------|-----------|
| Name | Buffett Plus | Branded premium tier name |
| Type | Service | Digital subscription (not physical goods) |
| Description | Contains token limit | Self-documenting for Stripe Dashboard |
| Active | true | Ready for checkout sessions |
| Livemode | false | Test environment |

---

## Task D2: Create Stripe Price

### Initial Creation ($9.99)

**MCP Tool Used**: `mcp__stripe__create_price`

```json
{
  "product": "prod_TuI3SR1TMzTPFt",
  "unit_amount": 999,
  "currency": "usd",
  "recurring": {"interval": "month"}
}
```

**Result**: `price_1SwTTxGtKkLcbRiafyq4Jm8X` (superseded)

### Final Price ($10.00)

Per user request, price was updated to an even $10.00:

```json
{
  "product": "prod_TuI3SR1TMzTPFt",
  "unit_amount": 1000,
  "currency": "usd",
  "recurring": {"interval": "month"}
}
```

**Response**:
```json
{
  "id": "price_1SwTUiGtKkLcbRiapMRnErLu",
  "object": "price",
  "active": true,
  "billing_scheme": "per_unit",
  "currency": "usd",
  "product": "prod_TuI3SR1TMzTPFt",
  "recurring": {
    "interval": "month",
    "interval_count": 1,
    "usage_type": "licensed"
  },
  "unit_amount": 1000,
  "livemode": false
}
```

### Price Configuration

| Property | Value | Rationale |
|----------|-------|-----------|
| Amount | 1000 (cents) | $10.00 even pricing |
| Currency | USD | Primary market |
| Interval | month | Monthly billing cycle |
| Usage Type | licensed | Fixed price per subscription |

---

## Task D3: Verify Configuration

### Product Verification

**MCP Tool Used**: `mcp__stripe__list_products`

```json
[{
  "id": "prod_TuI3SR1TMzTPFt",
  "name": "Buffett Plus",
  "type": "service",
  "description": "Premium subscription with 2,000,000 tokens/month for AI-powered investment analysis"
}]
```

### Price Verification

**MCP Tool Used**: `mcp__stripe__list_prices`

```json
[{
  "id": "price_1SwTUiGtKkLcbRiapMRnErLu",
  "amount": 1000,
  "currency": "usd",
  "product": "prod_TuI3SR1TMzTPFt",
  "type": "recurring",
  "recurring": {"interval": "month"}
}]
```

### Verification Checklist

| Criterion | Expected | Actual | Status |
|-----------|----------|--------|--------|
| Product name | "Buffett Plus" | "Buffett Plus" | PASS |
| Product active | true | true | PASS |
| Price amount | 1000 | 1000 | PASS |
| Price currency | usd | usd | PASS |
| Recurring interval | month | month | PASS |

---

## Task D4: Document IDs

### STRIPE_INTEGRATION_GUIDE.md Updated

- Version bumped to 1.3
- Added "Stripe Resource IDs (Test Mode)" section
- Updated all $9.99 references to $10

---

## Stripe Resource Summary

### Active Resources (Use These)

| Resource | ID | Details |
|----------|-----|---------|
| Product | `prod_TuI3SR1TMzTPFt` | "Buffett Plus" |
| Price | `price_1SwTUiGtKkLcbRiapMRnErLu` | $10.00/month |

### Superseded Resources (Archive These)

| Resource | ID | Action |
|----------|-----|--------|
| Price ($9.99) | `price_1SwTTxGtKkLcbRiafyq4Jm8X` | Archive in Dashboard |

---

## Verification Gates Passed

| Gate | Method | Status |
|------|--------|--------|
| Product created | `list_products` | PASSED |
| Product name correct | "Buffett Plus" | PASSED |
| Price created | `list_prices` | PASSED |
| Price amount correct | $10.00 | PASSED |
| Price recurring | monthly | PASSED |
| IDs documented | Guide updated | PASSED |

---

## AWS Secrets Manager Integration

### Required Action

```bash
aws secretsmanager put-secret-value \
  --secret-id stripe-plus-price-id-dev \
  --secret-string "price_1SwTUiGtKkLcbRiapMRnErLu"
```

### Verification

```bash
aws secretsmanager get-secret-value \
  --secret-id stripe-plus-price-id-dev \
  --query SecretString --output text
```

---

## Metadata Note

Stripe MCP tools don't support metadata during creation. To add metadata:

### Via Stripe Dashboard
1. Products > Buffett Plus > Edit
2. Add: `tier: plus`, `token_limit: 2000000`

### Via Stripe CLI
```bash
stripe products update prod_TuI3SR1TMzTPFt \
  --metadata[tier]=plus \
  --metadata[token_limit]=2000000
```

---

## Next Steps (Phase E: Frontend Integration)

Phase D resources are ready for frontend integration:
1. Create `subscriptionApi.js` with checkout/portal/status endpoints
2. Build upgrade banner and pricing modal components
3. Integrate Stripe.js with publishable key
4. Test end-to-end checkout flow
