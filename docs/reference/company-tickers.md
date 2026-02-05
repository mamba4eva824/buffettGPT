# Company Tickers

This document lists the DJIA 30 companies supported by BuffettGPT's investment research module.

## DJIA 30 Companies

| Ticker | Company Name | Sector |
|--------|--------------|--------|
| AAPL | Apple Inc. | Technology |
| AMGN | Amgen Inc. | Healthcare |
| AMZN | Amazon.com Inc. | Consumer Discretionary |
| AXP | American Express Co. | Financials |
| BA | Boeing Co. | Industrials |
| CAT | Caterpillar Inc. | Industrials |
| CRM | Salesforce Inc. | Technology |
| CSCO | Cisco Systems Inc. | Technology |
| CVX | Chevron Corp. | Energy |
| DIS | Walt Disney Co. | Communication Services |
| DOW | Dow Inc. | Materials |
| GS | Goldman Sachs Group Inc. | Financials |
| HD | Home Depot Inc. | Consumer Discretionary |
| HON | Honeywell International Inc. | Industrials |
| IBM | International Business Machines | Technology |
| INTC | Intel Corp. | Technology |
| JNJ | Johnson & Johnson | Healthcare |
| JPM | JPMorgan Chase & Co. | Financials |
| KO | Coca-Cola Co. | Consumer Staples |
| MCD | McDonald's Corp. | Consumer Discretionary |
| MMM | 3M Co. | Industrials |
| MRK | Merck & Co. Inc. | Healthcare |
| MSFT | Microsoft Corp. | Technology |
| NKE | Nike Inc. | Consumer Discretionary |
| PG | Procter & Gamble Co. | Consumer Staples |
| TRV | Travelers Companies Inc. | Financials |
| UNH | UnitedHealth Group Inc. | Healthcare |
| V | Visa Inc. | Financials |
| VZ | Verizon Communications Inc. | Communication Services |
| WMT | Walmart Inc. | Consumer Staples |

## Sector Breakdown

| Sector | Count | Companies |
|--------|-------|-----------|
| Technology | 6 | AAPL, CRM, CSCO, IBM, INTC, MSFT |
| Financials | 5 | AXP, GS, JPM, TRV, V |
| Healthcare | 4 | AMGN, JNJ, MRK, UNH |
| Industrials | 4 | BA, CAT, HON, MMM |
| Consumer Discretionary | 4 | AMZN, HD, MCD, NKE |
| Consumer Staples | 3 | KO, PG, WMT |
| Communication Services | 2 | DIS, VZ |
| Energy | 1 | CVX |
| Materials | 1 | DOW |

## Usage

### Generate Report for a Ticker

```python
from investment_research.report_generator import ReportGenerator

generator = ReportGenerator(use_api=False, prompt_version=4.8)
data = generator.prepare_data('AAPL')
```

### Get All Supported Tickers

```python
from investment_research.index_tickers import DJIA_30_TICKERS

print(DJIA_30_TICKERS)
# ['AAPL', 'AMGN', 'AMZN', ...]
```

### Company Name Lookup

```python
from investment_research.company_names import get_company_name

name = get_company_name('AAPL')
# 'Apple Inc.'
```

## Batch Generation

For generating reports for all DJIA 30 companies:

```bash
cd chat-api/backend/investment_research/batch_generation

# Prepare data for all tickers
python prepare_batch_data.py

# Run parallel generation
./run_parallel_reports.sh
```

See [Batch Generation](../investment-research/batch-generation.md) for details.

## Adding New Tickers

To add support for additional companies:

1. Add ticker to `index_tickers.py`
2. Add company name to `company_names.py`
3. Verify FMP API has data available
4. Test report generation

```python
# index_tickers.py
SUPPORTED_TICKERS = DJIA_30_TICKERS + ['NVDA', 'TSLA']

# company_names.py
COMPANY_NAMES = {
    ...
    'NVDA': 'NVIDIA Corp.',
    'TSLA': 'Tesla Inc.',
}
```
