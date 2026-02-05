# Forex Rate Cache - Multi-Currency Support

## Overview

The forex cache enables multi-currency support for investment reports, displaying financial data in both native currency and USD equivalent (e.g., "DKK 75.0B (~$10.7B USD)").

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Report         │     │  FMP Client      │     │  DynamoDB       │
│  Generator      │────▶│  (fmp_client.py) │────▶│  Forex Cache    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │                        │
                               ▼                        │
                        ┌──────────────────┐            │
                        │  FMP Forex API   │◀───────────┘
                        │  (fallback)      │   Cache miss
                        └──────────────────┘
```

## Components

| Component | File | Purpose |
|-----------|------|---------|
| Forex Cache Table | `terraform/modules/dynamodb/ml_tables.tf` | DynamoDB table for rate storage |
| FMP Client | `backend/src/utils/fmp_client.py` | Forex fetching and caching logic |
| Currency Formatter | `backend/src/utils/currency.py` | Dual-currency display formatting |
| Report Generator | `backend/investment_research/report_generator.py` | Consumes formatted values |

---

## Step-by-Step Workflow

### Step 1: Financial Data Request

When `get_financial_data(ticker)` is called:

```python
# fmp_client.py - get_financial_data()
financial_data = get_financial_data("NVO")  # Novo Nordisk (Danish)
```

### Step 2: Currency Detection

The FMP API returns `reportedCurrency` in each financial statement:

```python
# fmp_client.py - fetch_from_fmp()
def fetch_from_fmp(ticker: str) -> dict:
    # ... fetch statements ...

    # Extract currency from first response
    if data and len(data) > 0:
        reported_currency = data[0].get('reportedCurrency') or 'USD'
        # Example: "DKK" for Novo Nordisk

    statements['reported_currency'] = reported_currency
    return statements
```

### Step 3: Forex Rate Lookup

After detecting a non-USD currency, fetch the exchange rate:

```python
# fmp_client.py - get_financial_data()
reported_currency = raw_financials.pop('reported_currency', 'USD')

if reported_currency != 'USD':
    usd_rate = get_forex_rate(reported_currency, 'USD')
else:
    usd_rate = 1.0

currency_info = {
    'code': reported_currency,      # "DKK"
    'usd_rate': usd_rate,           # 0.143
    'rate_fetched_at': timestamp
}
```

### Step 4: Cache Check (get_forex_rate)

The main entry point checks cache before calling API:

```python
# fmp_client.py - get_forex_rate()
def get_forex_rate(from_currency: str, to_currency: str = 'USD') -> float:
    # 1. Same currency = 1.0
    if from_currency.upper() == to_currency.upper():
        return 1.0

    # 2. Check DynamoDB cache
    cached_rate = get_cached_forex_rate(from_currency, to_currency)
    if cached_rate is not None:
        return cached_rate  # Cache hit!

    # 3. Fetch from FMP API (cache miss)
    rate = fetch_forex_rate(from_currency, to_currency)
    if rate is not None:
        store_forex_rate(from_currency, to_currency, rate)
        return rate

    # 4. Fallback to 1.0 if all fails
    return 1.0
```

### Step 5: DynamoDB Cache Operations

**Cache Check:**
```python
# fmp_client.py - get_cached_forex_rate()
def get_cached_forex_rate(from_currency: str, to_currency: str = 'USD') -> Optional[float]:
    table = get_forex_cache_table()  # buffett-dev-forex-cache
    pair_key = f"{from_currency}{to_currency}"  # "DKKUSD"

    response = table.get_item(Key={'currency_pair': pair_key})

    if 'Item' not in response:
        return None  # Cache miss

    # Check TTL
    if int(cached['expires_at']) < int(datetime.now().timestamp()):
        return None  # Expired

    return float(cached['rate'])  # Cache hit
```

**Cache Store:**
```python
# fmp_client.py - store_forex_rate()
def store_forex_rate(from_currency: str, to_currency: str, rate: float) -> None:
    table = get_forex_cache_table()

    item = {
        'currency_pair': f"{from_currency}{to_currency}",  # PK
        'rate': Decimal(str(round(rate, 6))),
        'from_currency': from_currency,
        'to_currency': to_currency,
        'cached_at': int(datetime.now().timestamp()),
        'expires_at': int((datetime.now() + timedelta(hours=24)).timestamp())
    }

    table.put_item(Item=item)
```

### Step 6: FMP Forex API Call (Cache Miss)

If cache misses, fetch from FMP:

```python
# fmp_client.py - fetch_forex_rate()
def fetch_forex_rate(from_currency: str, to_currency: str = 'USD') -> Optional[float]:
    url = "https://financialmodelingprep.com/stable/quote"
    pair_symbol = f"{from_currency}{to_currency}"  # "DKKUSD"

    response = client.get(url, params={
        'symbol': pair_symbol,
        'apikey': api_key
    })

    # Response: [{"symbol": "DKKUSD", "price": 0.143, ...}]
    return float(data[0].get('price'))
```

### Step 7: Currency Formatting in Reports

The `CurrencyFormatter` class handles dual-currency display:

```python
# report_generator.py - _format_metrics_for_prompt()
from src.utils.currency import CurrencyFormatter

def _format_metrics_for_prompt(self, features, trends, raw_financials, currency_info):
    # Initialize formatter with currency info
    fmt = CurrencyFormatter(
        currency_info.get('code', 'USD'),
        currency_info.get('usd_rate', 1.0)
    )

    # Format values - automatically adds USD equivalent for non-USD
    revenue = fmt.money(75_000_000_000)  # "DKK 75.0B (~$10.7B)"
    eps = fmt.eps(32.15)                  # "DKK 32.15 (~$4.60)"
```

---

## DynamoDB Table Schema

**Table Name:** `buffett-dev-forex-cache`

| Attribute | Type | Description |
|-----------|------|-------------|
| `currency_pair` | String (PK) | E.g., "DKKUSD", "EURUSD" |
| `rate` | Number | Exchange rate (1 from = X to) |
| `from_currency` | String | Source currency code |
| `to_currency` | String | Target currency code |
| `cached_at` | Number | Unix timestamp of cache write |
| `expires_at` | Number | TTL - 24 hours after cached_at |

**Example Item:**
```json
{
  "currency_pair": "DKKUSD",
  "rate": 0.143287,
  "from_currency": "DKK",
  "to_currency": "USD",
  "cached_at": 1736280000,
  "expires_at": 1736366400
}
```

---

## TTL and Expiration

- **TTL:** 24 hours
- **Rationale:** Forex rates change daily but intraday fluctuations are acceptable for financial report context
- **DynamoDB TTL:** Enabled on `expires_at` attribute for automatic cleanup

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Cache miss | Fetch from FMP API, store in cache |
| Cache expired | Treat as cache miss |
| FMP API error | Log warning, return fallback rate 1.0 |
| DynamoDB error | Log warning, continue without caching |
| Invalid rate (0 or negative) | Use fallback rate 1.0 |

---

## Currency Display Examples

| Ticker | Currency | Raw Value | Formatted Output |
|--------|----------|-----------|------------------|
| AAPL | USD | 383,000,000,000 | $383.0B |
| NVO | DKK | 524,000,000,000 | DKK 524.0B (~$75.0B) |
| SHEL | EUR | 280,000,000,000 | €280.0B (~$305.2B) |
| TSM | TWD | 2,100,000,000,000 | NT$2,100.0B (~$64.7B) |

---

## Supported Currencies

The `currency.py` module supports 30+ currencies:

```
USD ($), EUR (€), GBP (£), JPY (¥), CNY (¥), CHF, CAD (C$), AUD (A$),
HKD (HK$), SGD (S$), DKK, NOK, SEK, KRW (₩), INR (₹), BRL (R$),
MXN (MX$), TWD (NT$), ZAR (R), PLN (zł), THB (฿), IDR (Rp),
MYR (RM), PHP (₱), CZK (Kč), ILS (₪), CLP, AED, SAR, RUB (₽), TRY (₺)
```

---

## Monitoring

**CloudWatch Logs to watch:**
- `[FOREX] Cache hit for DKKUSD: 0.143` - Cache working
- `[FOREX] Cache miss for DKKUSD` - Will fetch from API
- `[FOREX] Fetched DKKUSD rate: 0.143` - API call successful
- `[FOREX] Using fallback rate 1.0` - Error condition

**DynamoDB Metrics:**
- Read capacity consumed (cache hits)
- Write capacity consumed (cache stores)
- TTL deletions (expired items)

---

## Testing

**Test tickers by currency:**

| Ticker | Company | Currency | Purpose |
|--------|---------|----------|---------|
| AAPL | Apple | USD | Baseline (no conversion) |
| NVO | Novo Nordisk | DKK | Danish Krone |
| SHEL | Shell | EUR | Euro |
| TSM | Taiwan Semi | TWD | Taiwan Dollar |
| TM | Toyota | JPY | Japanese Yen |

**Verify cache is working:**
```bash
# Check table contents
aws dynamodb scan --table-name buffett-dev-forex-cache

# Expected output after NVO report generation:
# {
#   "currency_pair": "DKKUSD",
#   "rate": 0.143,
#   "expires_at": 1736366400
# }
```
