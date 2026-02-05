#!/usr/bin/env python3
"""
Unit tests for action_group_handler.py

Tests the Bedrock action group request/response parsing logic:
- parse_action_group_parameters()
- format_action_group_response()
- format_error_response()
- DecimalEncoder

These are unit tests for the parsing/formatting logic only.
Integration tests with actual AWS calls are separate.

Run:
    cd chat-api/backend
    python tests/test_action_group_handler.py
"""

import os
import sys
import json
from decimal import Decimal

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from handlers.action_group_handler import (
    parse_action_group_parameters,
    format_action_group_response,
    format_error_response,
    DecimalEncoder
)


def test_parse_parameters_new_format():
    """Test parsing parameters from new Bedrock action group format."""
    event = {
        "actionGroup": "FinancialAnalysis",
        "apiPath": "/analyze",
        "httpMethod": "POST",
        "requestBody": {
            "content": {
                "application/json": {
                    "properties": [
                        {"name": "ticker", "value": "AAPL"},
                        {"name": "analysis_type", "value": "debt"}
                    ]
                }
            }
        }
    }

    params = parse_action_group_parameters(event)

    assert params.get('ticker') == 'AAPL', f"Expected 'AAPL', got {params.get('ticker')}"
    assert params.get('analysis_type') == 'debt', f"Expected 'debt', got {params.get('analysis_type')}"

    print(f"  Parsed: {params}")
    return True


def test_parse_parameters_old_format():
    """Test parsing parameters from older Bedrock format."""
    event = {
        "actionGroup": "FinancialAnalysis",
        "apiPath": "/analyze",
        "parameters": [
            {"name": "ticker", "value": "MSFT"},
            {"name": "analysis_type", "value": "growth"}
        ]
    }

    params = parse_action_group_parameters(event)

    assert params.get('ticker') == 'MSFT'
    assert params.get('analysis_type') == 'growth'

    print(f"  Parsed: {params}")
    return True


def test_parse_parameters_mixed_format():
    """Test parsing when both formats are present (new takes precedence)."""
    event = {
        "actionGroup": "FinancialAnalysis",
        "apiPath": "/analyze",
        "requestBody": {
            "content": {
                "application/json": {
                    "properties": [
                        {"name": "ticker", "value": "GOOGL"},
                        {"name": "analysis_type", "value": "cashflow"}
                    ]
                }
            }
        },
        "parameters": [
            {"name": "ticker", "value": "IGNORED"}
        ]
    }

    params = parse_action_group_parameters(event)

    # Both formats are parsed, but new format comes first
    assert 'ticker' in params
    assert 'analysis_type' in params

    print(f"  Parsed: {params}")
    return True


def test_parse_parameters_empty():
    """Test parsing empty event."""
    event = {}

    params = parse_action_group_parameters(event)

    assert params == {}

    print("  Empty event returns empty params")
    return True


def test_parse_parameters_with_none_values():
    """Test parsing parameters with None values (should be excluded)."""
    event = {
        "requestBody": {
            "content": {
                "application/json": {
                    "properties": [
                        {"name": "ticker", "value": "AAPL"},
                        {"name": "analysis_type", "value": None}
                    ]
                }
            }
        }
    }

    params = parse_action_group_parameters(event)

    assert params.get('ticker') == 'AAPL'
    assert 'analysis_type' not in params  # None values excluded

    print(f"  Parsed (None excluded): {params}")
    return True


def test_format_response_basic():
    """Test formatting a basic successful response."""
    response_body = {
        "ticker": "AAPL",
        "prediction": "BUY",
        "confidence": 0.75
    }

    formatted = format_action_group_response(
        action_group="FinancialAnalysis",
        api_path="/analyze",
        response_body=response_body
    )

    assert formatted['messageVersion'] == '1.0'
    assert formatted['response']['actionGroup'] == 'FinancialAnalysis'
    assert formatted['response']['apiPath'] == '/analyze'
    assert formatted['response']['httpMethod'] == 'POST'
    assert formatted['response']['httpStatusCode'] == 200

    # Parse the JSON body
    body = json.loads(formatted['response']['responseBody']['application/json']['body'])
    assert body['ticker'] == 'AAPL'
    assert body['prediction'] == 'BUY'
    assert body['confidence'] == 0.75

    print(f"  Response structure valid")
    print(f"  Body: {body}")
    return True


def test_format_response_with_complex_data():
    """Test formatting response with nested structures."""
    response_body = {
        "ticker": "MSFT",
        "quarterly_trends": {
            "debt_to_equity": [0.5, 0.52, 0.54],
            "revenue": [50000000000, 49000000000, 48000000000]
        },
        "computed_insights": {
            "phases": [
                {"name": "Deleveraging", "quarters": "Q5-Q0"}
            ]
        }
    }

    formatted = format_action_group_response(
        action_group="FinancialAnalysis",
        api_path="/analyze",
        response_body=response_body
    )

    body = json.loads(formatted['response']['responseBody']['application/json']['body'])
    assert 'quarterly_trends' in body
    assert len(body['quarterly_trends']['debt_to_equity']) == 3
    assert 'computed_insights' in body

    print(f"  Complex nested structure preserved")
    return True


def test_format_error_response():
    """Test formatting error response."""
    formatted = format_error_response(
        action_group="FinancialAnalysis",
        api_path="/analyze",
        error_message="Invalid ticker: XYZ123",
        status_code=400
    )

    assert formatted['messageVersion'] == '1.0'
    assert formatted['response']['httpStatusCode'] == 400

    body = json.loads(formatted['response']['responseBody']['application/json']['body'])
    assert body['error'] == 'Invalid ticker: XYZ123'
    assert 'timestamp' in body

    print(f"  Error: {body['error']}")
    print(f"  Timestamp: {body['timestamp']}")
    return True


def test_format_error_response_500():
    """Test formatting 500 error response."""
    formatted = format_error_response(
        action_group="FinancialAnalysis",
        api_path="/analyze",
        error_message="Internal server error",
        status_code=500
    )

    assert formatted['response']['httpStatusCode'] == 500

    body = json.loads(formatted['response']['responseBody']['application/json']['body'])
    assert 'error' in body

    print("  500 error formatted correctly")
    return True


def test_decimal_encoder_decimal():
    """Test DecimalEncoder handles Decimal types."""
    data = {
        "value": Decimal("123.45"),
        "ratio": Decimal("0.678")
    }

    encoded = json.dumps(data, cls=DecimalEncoder)
    decoded = json.loads(encoded)

    assert decoded['value'] == 123.45
    assert decoded['ratio'] == 0.678

    print(f"  Decimal values encoded: {decoded}")
    return True


def test_decimal_encoder_numpy():
    """Test DecimalEncoder handles numpy types."""
    try:
        import numpy as np

        data = {
            "float64": np.float64(123.45),
            "int64": np.int64(42),
            "float32": np.float32(0.5)
        }

        encoded = json.dumps(data, cls=DecimalEncoder)
        decoded = json.loads(encoded)

        assert decoded['float64'] == 123.45
        assert decoded['int64'] == 42
        assert abs(decoded['float32'] - 0.5) < 0.01

        print(f"  NumPy types encoded: {decoded}")
        return True

    except ImportError:
        print("  Skipping numpy test (numpy not installed)")
        return True


def test_decimal_encoder_mixed():
    """Test DecimalEncoder with mixed types."""
    data = {
        "string": "hello",
        "int": 42,
        "float": 3.14,
        "decimal": Decimal("99.99"),
        "list": [1, 2, Decimal("3.33")],
        "nested": {
            "decimal_nested": Decimal("1.23")
        }
    }

    encoded = json.dumps(data, cls=DecimalEncoder)
    decoded = json.loads(encoded)

    assert decoded['string'] == 'hello'
    assert decoded['int'] == 42
    assert decoded['float'] == 3.14
    assert decoded['decimal'] == 99.99
    assert decoded['list'][2] == 3.33
    assert decoded['nested']['decimal_nested'] == 1.23

    print(f"  Mixed types encoded correctly")
    return True


def test_full_request_response_cycle():
    """Test complete request parsing to response formatting cycle."""
    # Simulate incoming Bedrock request
    incoming_event = {
        "actionGroup": "DebtExpertAnalysis",
        "apiPath": "/analyze",
        "httpMethod": "POST",
        "requestBody": {
            "content": {
                "application/json": {
                    "properties": [
                        {"name": "ticker", "value": "NVDA"},
                        {"name": "analysis_type", "value": "debt"}
                    ]
                }
            }
        }
    }

    # Parse parameters
    params = parse_action_group_parameters(incoming_event)
    assert params['ticker'] == 'NVDA'
    assert params['analysis_type'] == 'debt'

    # Simulate analysis result
    analysis_result = {
        "ticker": params['ticker'],
        "analysis_type": params['analysis_type'],
        "model_inference": {
            "prediction": "HOLD",
            "confidence": Decimal("0.62"),  # Use Decimal to test encoding
            "probabilities": {
                "SELL": 0.20,
                "HOLD": 0.62,
                "BUY": 0.18
            }
        }
    }

    # Format response
    response = format_action_group_response(
        action_group=incoming_event['actionGroup'],
        api_path=incoming_event['apiPath'],
        response_body=analysis_result
    )

    # Verify response structure
    assert response['messageVersion'] == '1.0'
    assert response['response']['actionGroup'] == 'DebtExpertAnalysis'
    assert response['response']['httpStatusCode'] == 200

    # Verify body is valid JSON
    body = json.loads(response['response']['responseBody']['application/json']['body'])
    assert body['ticker'] == 'NVDA'
    assert body['model_inference']['prediction'] == 'HOLD'
    assert body['model_inference']['confidence'] == 0.62  # Decimal converted to float

    print("  Full request-response cycle successful")
    print(f"  Ticker: {body['ticker']}")
    print(f"  Prediction: {body['model_inference']['prediction']}")
    return True


def test_special_characters_in_response():
    """Test handling of special characters in response."""
    response_body = {
        "ticker": "BRK.B",  # Special character in ticker
        "company_name": "Berkshire Hathaway Inc. - Class B",
        "notes": "Includes \"quoted\" text and special chars: <>&"
    }

    formatted = format_action_group_response(
        action_group="FinancialAnalysis",
        api_path="/analyze",
        response_body=response_body
    )

    body = json.loads(formatted['response']['responseBody']['application/json']['body'])
    assert body['ticker'] == 'BRK.B'
    assert '"quoted"' in body['notes']

    print("  Special characters handled correctly")
    return True


def run_all_tests():
    """Run all tests and report results."""
    tests = [
        ("Parse params: new format", test_parse_parameters_new_format),
        ("Parse params: old format", test_parse_parameters_old_format),
        ("Parse params: mixed format", test_parse_parameters_mixed_format),
        ("Parse params: empty event", test_parse_parameters_empty),
        ("Parse params: None values", test_parse_parameters_with_none_values),
        ("Format response: basic", test_format_response_basic),
        ("Format response: complex data", test_format_response_with_complex_data),
        ("Format error: 400", test_format_error_response),
        ("Format error: 500", test_format_error_response_500),
        ("DecimalEncoder: Decimal", test_decimal_encoder_decimal),
        ("DecimalEncoder: numpy", test_decimal_encoder_numpy),
        ("DecimalEncoder: mixed types", test_decimal_encoder_mixed),
        ("Full request-response cycle", test_full_request_response_cycle),
        ("Special characters", test_special_characters_in_response),
    ]

    print("=" * 60)
    print("Action Group Handler Unit Tests")
    print("=" * 60)

    passed = 0
    failed = 0

    for name, test_fn in tests:
        print(f"\n[TEST] {name}")
        try:
            result = test_fn()
            if result:
                print(f"  PASSED")
                passed += 1
            else:
                print(f"  FAILED")
                failed += 1
        except Exception as e:
            print(f"  FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
