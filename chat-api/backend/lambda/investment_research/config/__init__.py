"""Configuration module for Investment Research Lambda."""
from .settings import (
    ENVIRONMENT,
    PROJECT_NAME,
    LOG_LEVEL,
    INVESTMENT_REPORTS_TABLE,
    DEFAULT_FISCAL_YEAR,
)

__all__ = [
    'ENVIRONMENT',
    'PROJECT_NAME',
    'LOG_LEVEL',
    'INVESTMENT_REPORTS_TABLE',
    'DEFAULT_FISCAL_YEAR',
]
