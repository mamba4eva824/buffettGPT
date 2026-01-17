"""
Currency utilities for multi-currency financial data display.

Supports displaying values in native currency with USD equivalent.
Example: "DKK 75.0B (~$10.7B USD)"
"""

from typing import Optional, Dict
from decimal import Decimal


# Currency symbol mapping
CURRENCY_SYMBOLS: Dict[str, str] = {
    'USD': '$',
    'EUR': '€',
    'GBP': '£',
    'JPY': '¥',
    'CNY': '¥',
    'CHF': 'CHF ',
    'CAD': 'C$',
    'AUD': 'A$',
    'HKD': 'HK$',
    'SGD': 'S$',
    'DKK': 'DKK ',
    'NOK': 'NOK ',
    'SEK': 'SEK ',
    'KRW': '₩',
    'INR': '₹',
    'BRL': 'R$',
    'MXN': 'MX$',
    'TWD': 'NT$',
    'ZAR': 'R',
    'PLN': 'zł',
    'THB': '฿',
    'IDR': 'Rp',
    'MYR': 'RM',
    'PHP': '₱',
    'CZK': 'Kč',
    'ILS': '₪',
    'CLP': 'CLP$',
    'AED': 'AED ',
    'SAR': 'SAR ',
    'RUB': '₽',
    'TRY': '₺',
}


def get_currency_symbol(currency_code: str) -> str:
    """
    Get display symbol for a currency code.

    Args:
        currency_code: ISO 4217 currency code (e.g., 'USD', 'DKK')

    Returns:
        Currency symbol (e.g., '$', 'DKK ')
    """
    if not currency_code:
        return '$'
    return CURRENCY_SYMBOLS.get(currency_code.upper(), f'{currency_code} ')


def format_value_billions(value: float, currency_code: str = 'USD') -> str:
    """
    Format a value in billions/millions/thousands with currency symbol.

    Args:
        value: Raw numeric value
        currency_code: ISO currency code

    Returns:
        Formatted string like "$10.5B" or "DKK 75.0B"
    """
    if value is None:
        return 'N/A'

    # Handle Decimal type from DynamoDB
    if isinstance(value, Decimal):
        value = float(value)

    symbol = get_currency_symbol(currency_code)

    if abs(value) >= 1e9:
        return f"{symbol}{value / 1e9:.1f}B"
    elif abs(value) >= 1e6:
        return f"{symbol}{value / 1e6:.1f}M"
    elif abs(value) >= 1e3:
        return f"{symbol}{value / 1e3:.1f}K"
    else:
        return f"{symbol}{value:,.0f}"


def format_value_full(value: float, currency_code: str = 'USD') -> str:
    """
    Format a value with full precision and commas.

    Args:
        value: Raw numeric value
        currency_code: ISO currency code

    Returns:
        Formatted string like "$1,234,567,890"
    """
    if value is None:
        return 'N/A'

    # Handle Decimal type from DynamoDB
    if isinstance(value, Decimal):
        value = float(value)

    symbol = get_currency_symbol(currency_code)
    return f"{symbol}{value:,.0f}"


def format_with_usd_equivalent(
    value: float,
    native_currency: str,
    usd_rate: float,
    format_type: str = 'billions'
) -> str:
    """
    Format value in native currency with USD equivalent.

    Args:
        value: Raw value in native currency
        native_currency: ISO currency code (e.g., 'DKK')
        usd_rate: Exchange rate to USD (e.g., 0.143 for DKK)
        format_type: 'billions' or 'full'

    Returns:
        Formatted string like "DKK 75.0B (~$10.7B USD)"
        or just "$75.0B" if native_currency is USD
    """
    if value is None:
        return 'N/A'

    # Handle Decimal type from DynamoDB
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(usd_rate, Decimal):
        usd_rate = float(usd_rate)

    # If already USD, just format normally
    if native_currency == 'USD' or native_currency is None:
        if format_type == 'billions':
            return format_value_billions(value, 'USD')
        else:
            return format_value_full(value, 'USD')

    # Format native currency
    if format_type == 'billions':
        native_formatted = format_value_billions(value, native_currency)
    else:
        native_formatted = format_value_full(value, native_currency)

    # Calculate and format USD equivalent
    usd_value = value * usd_rate
    if format_type == 'billions':
        usd_formatted = format_value_billions(usd_value, 'USD')
    else:
        usd_formatted = format_value_full(usd_value, 'USD')

    return f"{native_formatted} (~{usd_formatted})"


def format_eps(value: float, currency_code: str = 'USD') -> str:
    """
    Format EPS with currency symbol.

    Args:
        value: EPS value
        currency_code: ISO currency code

    Returns:
        Formatted string like "$4.50" or "DKK 32.15"
    """
    if value is None:
        return 'N/A'

    # Handle Decimal type from DynamoDB
    if isinstance(value, Decimal):
        value = float(value)

    symbol = get_currency_symbol(currency_code)
    return f"{symbol}{value:.2f}"


def format_eps_with_usd(
    value: float,
    native_currency: str,
    usd_rate: float
) -> str:
    """
    Format EPS with USD equivalent.

    Args:
        value: EPS value in native currency
        native_currency: ISO currency code
        usd_rate: Exchange rate to USD

    Returns:
        Formatted string like "DKK 32.15 (~$4.60)"
    """
    if value is None:
        return 'N/A'

    # Handle Decimal type from DynamoDB
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(usd_rate, Decimal):
        usd_rate = float(usd_rate)

    if native_currency == 'USD' or native_currency is None:
        return format_eps(value, 'USD')

    native_formatted = format_eps(value, native_currency)
    usd_value = value * usd_rate
    usd_formatted = format_eps(usd_value, 'USD')

    return f"{native_formatted} (~{usd_formatted})"


class CurrencyFormatter:
    """
    Stateful currency formatter for consistent formatting across a report.

    Usage:
        formatter = CurrencyFormatter('DKK', 0.143)
        formatter.money(75_000_000_000)  # "DKK 75.0B (~$10.7B)"
        formatter.money(500_000_000)     # "DKK 500.0M (~$71.5M)"

    For USD reports:
        formatter = CurrencyFormatter('USD', 1.0)
        formatter.money(75_000_000_000)  # "$75.0B"
    """

    def __init__(self, native_currency: str = 'USD', usd_rate: float = 1.0):
        """
        Initialize formatter with currency and exchange rate.

        Args:
            native_currency: ISO currency code for the report
            usd_rate: Exchange rate to USD (1 native = X USD)
        """
        self.native_currency = (native_currency or 'USD').upper()
        self.usd_rate = usd_rate if usd_rate and usd_rate > 0 else 1.0
        self.is_usd = self.native_currency == 'USD'

    def money(self, value: float) -> str:
        """
        Format monetary value with auto-scaling (B/M/K) and USD equivalent.

        Automatically chooses appropriate scale:
        - >= 1 billion: "DKK 75.0B (~$10.7B)"
        - >= 1 million: "DKK 500.0M (~$71.5M)"
        - >= 1 thousand: "DKK 50.0K (~$7.2K)"
        - < 1 thousand: "DKK 500 (~$72)"
        """
        return format_with_usd_equivalent(
            value, self.native_currency, self.usd_rate, 'billions'
        )

    def full(self, value: float) -> str:
        """Format value with full precision (no scaling) and USD equivalent."""
        return format_with_usd_equivalent(
            value, self.native_currency, self.usd_rate, 'full'
        )

    # Alias for backwards compatibility
    billions = money

    def eps(self, value: float) -> str:
        """Format EPS with USD equivalent if non-USD."""
        return format_eps_with_usd(value, self.native_currency, self.usd_rate)

    @property
    def symbol(self) -> str:
        """Get native currency symbol."""
        return get_currency_symbol(self.native_currency)

    @property
    def currency_note(self) -> str:
        """
        Get a note about currency for report headers.

        Returns empty string for USD, formatted note for other currencies.
        """
        if self.is_usd:
            return ""
        return (
            f"**Currency Note:** All figures in {self.native_currency}. "
            f"USD equivalents shown in parentheses. "
            f"Rate: 1 {self.native_currency} = ${self.usd_rate:.4f} USD"
        )

    def __repr__(self) -> str:
        return f"CurrencyFormatter({self.native_currency}, rate={self.usd_rate})"
