"""
Environment-Aware Logger Utility for AWS Lambda

Provides centralized logging configuration that respects environment settings.
In production, logging is restricted to WARNING/ERROR levels to:
- Reduce CloudWatch costs
- Prevent sensitive data leakage
- Improve Lambda performance
- Maintain operational visibility for errors

Usage:
    from utils.logger import get_logger

    logger = get_logger(__name__)
    logger.debug("Debug message")  # Only in dev/staging
    logger.info("Info message")     # Only in dev/staging
    logger.warning("Warning")       # All environments
    logger.error("Error", extra={'user_id': user_id})  # All environments
"""

import logging
import os
import json
from typing import Any, Dict, Optional

# Environment configuration
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# Sensitive field names that should be redacted from logs
SENSITIVE_FIELDS = {
    'password', 'token', 'secret', 'api_key', 'apikey',
    'access_token', 'refresh_token', 'jwt', 'bearer',
    'authorization', 'auth', 'credentials', 'private_key'
}


def sanitize_log_data(data: Any) -> Any:
    """
    Recursively sanitize sensitive data from log output.

    Args:
        data: Any data structure (dict, list, str, etc.)

    Returns:
        Sanitized version of the data with sensitive fields redacted
    """
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            # Check if key contains sensitive terms
            if any(sensitive in key.lower() for sensitive in SENSITIVE_FIELDS):
                sanitized[key] = '[REDACTED]'
            else:
                sanitized[key] = sanitize_log_data(value)
        return sanitized

    elif isinstance(data, list):
        return [sanitize_log_data(item) for item in data]

    elif isinstance(data, str):
        # Don't sanitize strings directly, only when they're values in dicts
        return data

    else:
        return data


class SanitizingFormatter(logging.Formatter):
    """
    Custom formatter that sanitizes sensitive data from log records.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Sanitize extra fields if present
        if hasattr(record, 'extra'):
            record.extra = sanitize_log_data(record.extra)

        # Sanitize args
        if record.args:
            record.args = sanitize_log_data(record.args)

        return super().format(record)


def configure_logging():
    """
    Configure root logger based on environment variables.
    Should be called once at module initialization.
    """
    # Get log level from environment
    log_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Set level
    root_logger.setLevel(log_level)

    # Create console handler with custom formatter
    handler = logging.StreamHandler()
    handler.setLevel(log_level)

    # Format: timestamp - name - level - message
    formatter = SanitizingFormatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)

    root_logger.addHandler(handler)

    # Log configuration (only in non-production)
    if ENVIRONMENT != 'prod':
        root_logger.info(f"Logger configured: ENVIRONMENT={ENVIRONMENT}, LOG_LEVEL={LOG_LEVEL}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.

    Args:
        name: Logger name (typically __name__ of the module)

    Returns:
        Configured logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("Processing message", extra={'user_id': user_id})
    """
    return logging.getLogger(name)


class LambdaLogger:
    """
    Convenience wrapper for Lambda function logging with built-in sanitization.
    """

    def __init__(self, name: str):
        self.logger = get_logger(name)

    def debug(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Debug level - only in dev/staging"""
        if extra:
            extra = sanitize_log_data(extra)
        self.logger.debug(message, extra=extra or {})

    def info(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Info level - only in dev/staging (if LOG_LEVEL permits)"""
        if extra:
            extra = sanitize_log_data(extra)
        self.logger.info(message, extra=extra or {})

    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Warning level - all environments"""
        if extra:
            extra = sanitize_log_data(extra)
        self.logger.warning(message, extra=extra or {})

    def error(self, message: str, extra: Optional[Dict[str, Any]] = None, exc_info: bool = False):
        """Error level - all environments, always logged"""
        if extra:
            extra = sanitize_log_data(extra)
        self.logger.error(message, extra=extra or {}, exc_info=exc_info)

    def critical(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Critical level - all environments, highest priority"""
        if extra:
            extra = sanitize_log_data(extra)
        self.logger.critical(message, extra=extra or {})


# Initialize logging configuration when module is imported
configure_logging()