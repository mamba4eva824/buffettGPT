"""
Unit tests for ConfigLoader utility.

Tests the cached configuration loader with DynamoDB backend,
including cache behavior, fallback chain, and Decimal conversion.

Run with: pytest tests/unit/test_config_loader.py -v
"""

import json
import os
import sys
import time
import pytest
import boto3
from moto import mock_aws
from unittest.mock import patch, MagicMock
from decimal import Decimal

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Set environment BEFORE imports
os.environ['ENVIRONMENT'] = 'test'


# =============================================================================
# DynamoDB Table Helpers
# =============================================================================

def create_admin_config_table(dynamodb, table_name='test-admin-config'):
    """Create admin-config table."""
    table = dynamodb.create_table(
        TableName=table_name,
        KeySchema=[{'AttributeName': 'config_key', 'KeyType': 'HASH'}],
        AttributeDefinitions=[
            {'AttributeName': 'config_key', 'AttributeType': 'S'},
        ],
        BillingMode='PAY_PER_REQUEST'
    )
    table.wait_until_exists()
    return table


# =============================================================================
# Test Class: ConfigLoader
# =============================================================================

class TestConfigLoader:
    """Tests for ConfigLoader class."""

    def _make_loader(self):
        """Create a fresh ConfigLoader instance (avoids class-level cache sharing)."""
        from utils.config_loader import ConfigLoader
        loader = ConfigLoader()
        # Reset class-level cache for test isolation
        loader._cache = {}
        loader._last_refresh = 0
        return loader

    def test_get_returns_default_when_no_table(self):
        """
        Given: No ADMIN_CONFIG_TABLE configured
        When: get() is called
        Then: Returns the default value
        """
        with patch.dict(os.environ, {'ADMIN_CONFIG_TABLE': ''}, clear=False):
            # Need to reimport to pick up env change
            import importlib
            import utils.config_loader as mod
            importlib.reload(mod)

            loader = self._make_loader()
            result = loader.get('token_limits', 'plus', default=999)
            assert result == 999

    def test_get_falls_back_to_env_var(self):
        """
        Given: No DynamoDB data, but env var TOKEN_LIMITS_PLUS is set
        When: get('token_limits', 'plus') is called
        Then: Returns the env var value
        """
        with patch.dict(os.environ, {
            'ADMIN_CONFIG_TABLE': '',
            'TOKEN_LIMITS_PLUS': '5000000',
        }, clear=False):
            import importlib
            import utils.config_loader as mod
            importlib.reload(mod)

            loader = self._make_loader()
            result = loader.get('token_limits', 'plus', default=100)
            assert result == '5000000'

    @mock_aws
    def test_loads_from_dynamodb(self):
        """
        Given: ADMIN_CONFIG_TABLE is set and has data
        When: get_category() is called
        Then: Returns the DynamoDB data
        """
        table_name = 'test-admin-config'
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_admin_config_table(dynamodb, table_name)
        table.put_item(Item={
            'config_key': 'model_config',
            'config_value': {
                'followup_temperature': Decimal('0.7'),
                'followup_max_tokens': 2048,
            },
        })

        with patch.dict(os.environ, {'ADMIN_CONFIG_TABLE': table_name}, clear=False):
            import importlib
            import utils.config_loader as mod
            importlib.reload(mod)

            loader = self._make_loader()
            cat = loader.get_category('model_config')
            assert cat['followup_temperature'] == 0.7
            assert cat['followup_max_tokens'] == 2048

    @mock_aws
    def test_get_single_value(self):
        """
        Given: DynamoDB has token_limits with plus=3000000
        When: get('token_limits', 'plus') is called
        Then: Returns 3000000
        """
        table_name = 'test-admin-config'
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_admin_config_table(dynamodb, table_name)
        table.put_item(Item={
            'config_key': 'token_limits',
            'config_value': {'plus': 3000000, 'free': 100000},
        })

        with patch.dict(os.environ, {'ADMIN_CONFIG_TABLE': table_name}, clear=False):
            import importlib
            import utils.config_loader as mod
            importlib.reload(mod)

            loader = self._make_loader()
            result = loader.get('token_limits', 'plus')
            assert result == 3000000

    @mock_aws
    def test_cache_ttl_prevents_reload(self):
        """
        Given: Config loaded once
        When: get() called again within TTL
        Then: Does not reload from DynamoDB
        """
        table_name = 'test-admin-config'
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_admin_config_table(dynamodb, table_name)
        table.put_item(Item={
            'config_key': 'feature_flags',
            'config_value': {'enable_rate_limiting': True},
        })

        with patch.dict(os.environ, {'ADMIN_CONFIG_TABLE': table_name}, clear=False):
            import importlib
            import utils.config_loader as mod
            importlib.reload(mod)

            loader = self._make_loader()
            # First call triggers load
            loader.get_category('feature_flags')

            # Modify DynamoDB directly
            table.put_item(Item={
                'config_key': 'feature_flags',
                'config_value': {'enable_rate_limiting': False},
            })

            # Second call should return cached (stale) value
            result = loader.get_category('feature_flags')
            assert result['enable_rate_limiting'] is True

    @mock_aws
    def test_invalidate_forces_reload(self):
        """
        Given: Config is cached
        When: invalidate() is called, then get()
        Then: Reloads from DynamoDB
        """
        table_name = 'test-admin-config'
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_admin_config_table(dynamodb, table_name)
        table.put_item(Item={
            'config_key': 'feature_flags',
            'config_value': {'enable_rate_limiting': True},
        })

        with patch.dict(os.environ, {'ADMIN_CONFIG_TABLE': table_name}, clear=False):
            import importlib
            import utils.config_loader as mod
            importlib.reload(mod)

            loader = self._make_loader()
            loader.get_category('feature_flags')

            # Update DynamoDB
            table.put_item(Item={
                'config_key': 'feature_flags',
                'config_value': {'enable_rate_limiting': False},
            })

            # Invalidate and reload
            loader.invalidate()
            result = loader.get_category('feature_flags')
            assert result['enable_rate_limiting'] is False


# =============================================================================
# Test Class: Decimal Conversion
# =============================================================================

class TestDecimalConversion:
    """Tests for _convert_decimals helper."""

    def test_converts_decimal_to_int(self):
        from utils.config_loader import _convert_decimals
        assert _convert_decimals(Decimal('42')) == 42
        assert isinstance(_convert_decimals(Decimal('42')), int)

    def test_converts_decimal_to_float(self):
        from utils.config_loader import _convert_decimals
        result = _convert_decimals(Decimal('0.7'))
        assert abs(result - 0.7) < 0.001
        assert isinstance(result, float)

    def test_converts_nested_structures(self):
        from utils.config_loader import _convert_decimals
        data = {
            'a': Decimal('100'),
            'b': [Decimal('1'), Decimal('2.5')],
            'c': {'d': Decimal('0.3')},
        }
        result = _convert_decimals(data)
        assert result == {'a': 100, 'b': [1, 2.5], 'c': {'d': 0.3}}

    def test_leaves_non_decimal_unchanged(self):
        from utils.config_loader import _convert_decimals
        assert _convert_decimals('hello') == 'hello'
        assert _convert_decimals(True) is True
        assert _convert_decimals(None) is None
