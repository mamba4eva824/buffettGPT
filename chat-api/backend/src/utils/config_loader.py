"""
Config Loader - DynamoDB-backed runtime configuration

Provides a cached configuration layer that reads from the admin-config
DynamoDB table with fallback to environment variables and caller defaults.

Usage:
    from utils.config_loader import config

    # Single value with default
    limit = config.get('token_limits', 'plus', default=2000000)

    # Full category dict
    rate_limits = config.get_category('rate_limits')
"""

import os
import time
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ADMIN_CONFIG_TABLE = os.environ.get('ADMIN_CONFIG_TABLE')


class ConfigLoader:
    """
    Cached configuration loader with DynamoDB backend.

    Fallback chain: DynamoDB → environment variable → hardcoded default.
    """

    _cache: Dict[str, Any] = {}
    _cache_ttl: int = 300  # seconds
    _last_refresh: float = 0

    def get(self, category: str, key: str, default: Any = None) -> Any:
        """Return a single config value."""
        self._maybe_refresh()
        cat = self._cache.get(category, {})
        if isinstance(cat, dict):
            value = cat.get(key)
            if value is not None:
                return value
        # Fallback: env var named CATEGORY_KEY (uppercase)
        env_key = f"{category}_{key}".upper()
        env_val = os.environ.get(env_key)
        if env_val is not None:
            return env_val
        return default

    def get_category(self, category: str) -> Dict[str, Any]:
        """Return the full dict for a category."""
        self._maybe_refresh()
        return self._cache.get(category, {})

    def _maybe_refresh(self) -> None:
        """Refresh cache if older than _cache_ttl seconds."""
        now = time.time()
        if now - self._last_refresh < self._cache_ttl and self._cache:
            return
        self._load_from_dynamodb()
        self._last_refresh = now

    def _load_from_dynamodb(self) -> None:
        """Scan admin-config table and populate cache. No-op if table not configured."""
        if not ADMIN_CONFIG_TABLE:
            return

        try:
            import boto3
            dynamodb = boto3.resource('dynamodb')
            table = dynamodb.Table(ADMIN_CONFIG_TABLE)
            response = table.scan()

            new_cache: Dict[str, Any] = {}
            for item in response.get('Items', []):
                config_key = item.get('config_key')
                config_value = item.get('config_value')
                if config_key and config_value is not None:
                    # config_value is stored as JSON string or map
                    if isinstance(config_value, str):
                        try:
                            new_cache[config_key] = json.loads(config_value)
                        except (json.JSONDecodeError, TypeError):
                            new_cache[config_key] = config_value
                    else:
                        # DynamoDB map type - convert Decimals to int/float
                        new_cache[config_key] = _convert_decimals(config_value)

            self._cache = new_cache
            logger.info(f"Config loaded from DynamoDB: {len(new_cache)} categories")

        except Exception as e:
            logger.warning(f"Failed to load config from DynamoDB, using cached/defaults: {e}")

    def invalidate(self) -> None:
        """Force next access to reload from DynamoDB."""
        self._last_refresh = 0


def _convert_decimals(obj: Any) -> Any:
    """Recursively convert Decimal values to int or float."""
    from decimal import Decimal
    if isinstance(obj, Decimal):
        if obj == int(obj):
            return int(obj)
        return float(obj)
    if isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_decimals(i) for i in obj]
    return obj


# Module-level singleton
config = ConfigLoader()
