"""
Configuration for S&P 500 data fetching pipeline.
Defines endpoints, time periods, rate limits, and file paths.

Starter tier availability (verified 2026-02-11):
  WORKS:  /stable/income-statement, cash-flow-statement, balance-sheet-statement
  WORKS:  /stable/historical-price-eod/full (SPY proxy for index)
  WORKS:  /stable/profile (company profile with sector, marketCap)
  WORKS:  /stable/dividends (per-company dividend history)
  WORKS:  /stable/stock-list (all listed stocks)
  402:    /stable/sp500-constituent (tier-restricted)
  402:    /stable/dividends-calendar (tier-restricted)
  404:    /stable/sector-performance, etf-holdings, stock-screener
"""

import os

# ---------------------------------------------------------------------------
# FMP API settings
# ---------------------------------------------------------------------------
FMP_BASE_URL = "https://financialmodelingprep.com"
FMP_SECRET_NAME = os.environ.get("FMP_SECRET_NAME", "buffett-dev-fmp")

# Rate limits — Starter tier: 300 calls/min
CALLS_PER_MINUTE = 300
BATCH_SIZE = 50  # Fetch 50 calls, then brief pause
BATCH_PAUSE_SECONDS = 12  # ~250 calls/min effective rate

REQUEST_TIMEOUT_SECONDS = 30

# How many quarters of financial data per company (5 years = 20 quarters)
QUARTERLY_LIMIT = 20

# ---------------------------------------------------------------------------
# FMP API endpoints (all /stable/ — verified working on Starter tier)
# ---------------------------------------------------------------------------
ENDPOINTS = {
    # Index proxy — SPY ETF as S&P 500 proxy (~5 years daily data)
    "spy_historical_prices": "/stable/historical-price-eod/full",
    # Per-company endpoints
    "profile": "/stable/profile",
    "income_statement": "/stable/income-statement",
    "cashflow_statement": "/stable/cash-flow-statement",
    "balance_sheet": "/stable/balance-sheet-statement",
    "dividends": "/stable/dividends",
}

# The financial statement types we fetch per company
# (endpoint_key, label_in_output_json)
STATEMENT_TYPES = [
    ("income_statement", "income"),
    ("cashflow_statement", "cashflow"),
    ("balance_sheet", "balance"),
]

# ---------------------------------------------------------------------------
# Output paths (relative to sp500_analysis/)
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

OUTPUT_PATHS = {
    "constituents": os.path.join(DATA_DIR, "constituents.json"),
    "spy_historical_prices": os.path.join(DATA_DIR, "spy_historical_prices.json"),
    "manifest": os.path.join(DATA_DIR, "manifest.json"),
    # Subdirectories
    "company_financials_dir": os.path.join(DATA_DIR, "company_financials"),
    "company_profiles_dir": os.path.join(DATA_DIR, "company_profiles"),
    "company_dividends_dir": os.path.join(DATA_DIR, "company_dividends"),
}

# ---------------------------------------------------------------------------
# S&P 500 constituents (as of Feb 2026)
# Since the /stable/sp500-constituent endpoint requires a higher FMP tier,
# we maintain the list here. Source: Wikipedia S&P 500 list.
# This list should be refreshed periodically.
# ---------------------------------------------------------------------------
SP500_SYMBOLS = [
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "ADI", "ADM", "ADP", "ADSK", "AEE",
    "AEP", "AES", "AFL", "AIG", "AIZ", "AJG", "AKAM", "ALB", "ALGN", "ALK",
    "ALL", "ALLE", "AMAT", "AMCR", "AMD", "AME", "AMGN", "AMP", "AMT", "AMZN",
    "ANET", "ANSS", "AON", "AOS", "APA", "APD", "APH", "APTV", "ARE", "ATO",
    "ATVI", "AVB", "AVGO", "AVY", "AWK", "AXP", "AZO", "BA", "BAC", "BAX",
    "BBWI", "BBY", "BDX", "BEN", "BF.B", "BG", "BIIB", "BIO", "BK", "BKNG",
    "BKR", "BLDR", "BLK", "BMY", "BR", "BRK.B", "BRO", "BSX", "BWA", "BXP",
    "C", "CAG", "CAH", "CARR", "CAT", "CB", "CBOE", "CBRE", "CCI", "CCL",
    "CDAY", "CDNS", "CDW", "CE", "CEG", "CF", "CFG", "CHD", "CHRW", "CHTR",
    "CI", "CINF", "CL", "CLX", "CMA", "CMCSA", "CME", "CMG", "CMI", "CMS",
    "CNC", "CNP", "COF", "COO", "COP", "COR", "COST", "CPAY", "CPB", "CPRT",
    "CPT", "CRL", "CRM", "CRWD", "CSCO", "CSGP", "CSX", "CTAS", "CTLT", "CTRA",
    "CTSH", "CTVA", "CVS", "CVX", "CZR", "D", "DAL", "DAY", "DD", "DE",
    "DECK", "DFS", "DG", "DGX", "DHI", "DHR", "DIS", "DLTR", "DOV", "DOW",
    "DPZ", "DRI", "DTE", "DUK", "DVA", "DVN", "DXCM", "EA", "EBAY", "ECL",
    "ED", "EFX", "EIX", "EL", "EMN", "EMR", "ENPH", "EOG", "EPAM", "EQIX",
    "EQR", "EQT", "ES", "ESS", "ETN", "ETR", "EVRG", "EW", "EXC", "EXPD",
    "EXPE", "EXR", "F", "FANG", "FAST", "FCNCA", "FCX", "FDS", "FDX", "FE",
    "FFIV", "FI", "FICO", "FIS", "FISV", "FITB", "FLT", "FMC", "FOX", "FOXA",
    "FRT", "FSLR", "FTNT", "FTV", "GD", "GDDY", "GE", "GEHC", "GEN", "GILD",
    "GIS", "GL", "GLW", "GM", "GNRC", "GOOG", "GOOGL", "GPC", "GPN", "GRMN",
    "GS", "GWW", "HAL", "HAS", "HBAN", "HCA", "HD", "HOLX", "HON", "HPE",
    "HPQ", "HRL", "HSIC", "HST", "HSY", "HUBB", "HUM", "HWM", "IBM", "ICE",
    "IDXX", "IEX", "IFF", "ILMN", "INCY", "INTC", "INTU", "INVH", "IP", "IPG",
    "IQV", "IR", "IRM", "ISRG", "IT", "ITW", "IVZ", "J", "JBHT", "JBL",
    "JCI", "JKHY", "JNJ", "JNPR", "JPM", "K", "KDP", "KEY", "KEYS", "KHC",
    "KIM", "KLAC", "KMB", "KMI", "KMX", "KO", "KR", "KVUE", "L", "LDOS",
    "LEN", "LH", "LHX", "LIN", "LKQ", "LLY", "LMT", "LNT", "LOW", "LRCX",
    "LULU", "LUV", "LVS", "LW", "LYB", "LYV", "MA", "MAA", "MAR", "MAS",
    "MCD", "MCHP", "MCK", "MCO", "MDLZ", "MDT", "MET", "META", "MGM", "MHK",
    "MKC", "MKTX", "MLM", "MMC", "MMM", "MNST", "MO", "MOH", "MOS", "MPC",
    "MPWR", "MRK", "MRNA", "MRO", "MS", "MSCI", "MSFT", "MSI", "MTB", "MTCH",
    "MTD", "MU", "NCLH", "NDAQ", "NDSN", "NEE", "NEM", "NFLX", "NI", "NKE",
    "NOC", "NOW", "NRG", "NSC", "NTAP", "NTRS", "NUE", "NVDA", "NVR", "NWL",
    "NWS", "NWSA", "NXPI", "O", "ODFL", "OKE", "OMC", "ON", "ORCL", "ORLY",
    "OTIS", "OXY", "PANW", "PARA", "PAYC", "PAYX", "PCAR", "PCG", "PEG", "PEP",
    "PFE", "PFG", "PG", "PGR", "PH", "PHM", "PKG", "PLD", "PLTR", "PM",
    "PNC", "PNR", "PNW", "POOL", "PPG", "PPL", "PRU", "PSA", "PSX", "PTC",
    "PVH", "PWR", "PXD", "PYPL", "QCOM", "QRVO", "RCL", "REG", "REGN", "RF",
    "RHI", "RJF", "RL", "RMD", "ROK", "ROL", "ROP", "ROST", "RSG", "RTX",
    "RVTY", "SBAC", "SBUX", "SCHW", "SEE", "SHW", "SJM", "SLB", "SMCI", "SNA",
    "SNPS", "SO", "SPG", "SPGI", "SRE", "STE", "STLD", "STT", "STX", "STZ",
    "SWK", "SWKS", "SYF", "SYK", "SYY", "T", "TAP", "TDG", "TDY", "TECH",
    "TEL", "TER", "TFC", "TFX", "TGT", "TJX", "TMO", "TMUS", "TPR", "TRGP",
    "TRMB", "TROW", "TRV", "TSCO", "TSLA", "TSN", "TT", "TTWO", "TXN", "TXT",
    "TYL", "UAL", "UBER", "UDR", "UHS", "ULTA", "UNH", "UNP", "UPS", "URI",
    "USB", "V", "VFC", "VICI", "VLO", "VLTO", "VMC", "VRSN", "VRTX", "VST",
    "VTR", "VTRS", "VZ", "WAB", "WAT", "WBA", "WBD", "WDC", "WEC", "WELL",
    "WFC", "WM", "WMB", "WMT", "WRB", "WRK", "WST", "WTW", "WY", "WYNN",
    "XEL", "XOM", "XYL", "YUM", "ZBH", "ZBRA", "ZION", "ZTS",
]
