"""
Simulate Anniversary-Based Token Reset Scenarios

This script allows manual testing of the anniversary-based billing logic
by simulating different scenarios against a local or remote DynamoDB table.

Usage:
    python tests/local_simulate_anniversary_reset.py --scenario <scenario_name>

Scenarios:
    1. new_user - Simulates a new user's first request (billing_day set to today)
    2. mid_period - Simulates usage in the middle of a billing period
    3. period_boundary - Simulates crossing from one period to the next
    4. february_edge - Simulates billing_day=31 crossing into February
    5. year_rollover - Simulates December → January transition

Requirements:
    - moto (for local DynamoDB mock)
    - freezegun (for time simulation)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Use moto for local DynamoDB mock
try:
    import boto3
    from moto import mock_aws
    HAS_MOTO = True
except ImportError:
    HAS_MOTO = False
    print("Warning: moto not installed. Run: pip install moto")

try:
    from freezegun import freeze_time
    HAS_FREEZEGUN = True
except ImportError:
    HAS_FREEZEGUN = False
    print("Warning: freezegun not installed. Run: pip install freezegun")


def create_mock_table(dynamodb):
    """Create a mock token-usage table."""
    table = dynamodb.create_table(
        TableName='test-token-usage',
        KeySchema=[
            {'AttributeName': 'user_id', 'KeyType': 'HASH'},
            {'AttributeName': 'billing_period', 'KeyType': 'RANGE'}
        ],
        AttributeDefinitions=[
            {'AttributeName': 'user_id', 'AttributeType': 'S'},
            {'AttributeName': 'billing_period', 'AttributeType': 'S'}
        ],
        BillingMode='PAY_PER_REQUEST'
    )
    table.wait_until_exists()
    return table


def print_separator(title):
    """Print a visual separator."""
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)


def print_result(label, result):
    """Pretty print a result dictionary."""
    print(f"\n{label}:")
    print(json.dumps(result, indent=2, default=str))


def simulate_new_user():
    """
    Scenario 1: New User's First Request

    A new user makes their first request. The system should:
    - Set billing_day to the current day
    - Create a new billing period record
    - Initialize usage counters
    """
    print_separator("Scenario: New User's First Request")

    if not HAS_MOTO or not HAS_FREEZEGUN:
        print("Missing dependencies. Install: pip install moto freezegun")
        return

    @mock_aws
    @freeze_time("2025-03-15 10:30:00", tz_offset=0)
    def run_scenario():
        # Set up environment
        os.environ['ENVIRONMENT'] = 'test'
        os.environ['TOKEN_USAGE_TABLE'] = 'test-token-usage'
        os.environ['DEFAULT_TOKEN_LIMIT'] = '1000000'

        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        create_mock_table(dynamodb)

        from utils.token_usage_tracker import TokenUsageTracker
        tracker = TokenUsageTracker(table_name='test-token-usage', dynamodb_resource=dynamodb)

        user_id = 'new-user-123'

        print(f"\nCurrent simulated date: 2025-03-15")
        print(f"User ID: {user_id}")

        # Step 1: Check limit (first time - no existing record)
        print("\n1. First check_limit (no existing record):")
        result = tracker.check_limit(user_id)
        print_result("   Result", result)
        print(f"   Expected billing_day: 15 (today)")
        print(f"   Expected: allowed=True, billing_day=15")

        # Step 2: Record usage
        print("\n2. Record first usage (1000 input, 500 output):")
        result = tracker.record_usage(user_id, 1000, 500)
        print_result("   Result", result)
        print(f"   Expected: billing_day=15, total_tokens=1500")

        # Step 3: Get usage to see full record
        print("\n3. Get full usage statistics:")
        result = tracker.get_usage(user_id)
        print_result("   Result", result)

        # Step 4: Verify DynamoDB record
        print("\n4. Raw DynamoDB record:")
        table = dynamodb.Table('test-token-usage')
        response = table.get_item(Key={'user_id': user_id, 'billing_period': '2025-03-15'})
        if 'Item' in response:
            item = {k: (int(v) if isinstance(v, Decimal) else v) for k, v in response['Item'].items()}
            print_result("   DynamoDB Item", item)

    run_scenario()


def simulate_mid_period():
    """
    Scenario 2: Usage in Middle of Billing Period

    User subscribed on the 10th, and it's now the 20th of the same month.
    Multiple requests should accumulate in the same billing period.
    """
    print_separator("Scenario: Mid-Period Usage Accumulation")

    if not HAS_MOTO or not HAS_FREEZEGUN:
        print("Missing dependencies. Install: pip install moto freezegun")
        return

    @mock_aws
    @freeze_time("2025-03-20 14:00:00", tz_offset=0)
    def run_scenario():
        os.environ['ENVIRONMENT'] = 'test'
        os.environ['TOKEN_USAGE_TABLE'] = 'test-token-usage'
        os.environ['DEFAULT_TOKEN_LIMIT'] = '1000000'

        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_mock_table(dynamodb)

        # Pre-populate with existing usage from earlier in the period
        user_id = 'existing-user-456'
        table.put_item(Item={
            'user_id': user_id,
            'billing_period': '2025-03-10',  # Subscribed on March 10
            'billing_day': 10,
            'total_tokens': 50000,
            'input_tokens': 30000,
            'output_tokens': 20000,
            'request_count': 5,
            'token_limit': 1000000,
            'subscribed_at': '2025-03-10T08:00:00Z',
            'billing_period_start': '2025-03-10T00:00:00Z',
            'billing_period_end': '2025-04-10T00:00:00Z',
            'subscription_tier': 'plus'
        })

        from utils.token_usage_tracker import TokenUsageTracker
        tracker = TokenUsageTracker(table_name='test-token-usage', dynamodb_resource=dynamodb)

        print(f"\nCurrent simulated date: 2025-03-20 (mid-period)")
        print(f"User subscribed on: March 10")
        print(f"User ID: {user_id}")
        print(f"Existing usage: 50,000 tokens from 5 requests")

        # Step 1: Check limit
        print("\n1. Check current limit:")
        result = tracker.check_limit(user_id)
        print_result("   Result", result)
        print(f"   Expected billing_period key: 2025-03-10")

        # Step 2: Record more usage
        print("\n2. Record additional usage (2000 input, 1000 output):")
        result = tracker.record_usage(user_id, 2000, 1000)
        print_result("   Result", result)
        print(f"   Expected total_tokens: 53000 (50000 + 3000)")

        # Step 3: Get full statistics
        print("\n3. Get full usage statistics:")
        result = tracker.get_usage(user_id)
        print_result("   Result", result)

    run_scenario()


def simulate_period_boundary():
    """
    Scenario 3: Crossing Billing Period Boundary

    Shows what happens when a user's billing day arrives.
    Before: Jan 14 (period: Dec 15 - Jan 15)
    After:  Jan 15 (period: Jan 15 - Feb 15)
    """
    print_separator("Scenario: Crossing Billing Period Boundary")

    if not HAS_MOTO or not HAS_FREEZEGUN:
        print("Missing dependencies. Install: pip install moto freezegun")
        return

    user_id = 'boundary-user-789'

    @mock_aws
    def setup_and_run():
        os.environ['ENVIRONMENT'] = 'test'
        os.environ['TOKEN_USAGE_TABLE'] = 'test-token-usage'
        os.environ['DEFAULT_TOKEN_LIMIT'] = '1000000'

        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_mock_table(dynamodb)

        # Pre-populate with usage from previous period
        table.put_item(Item={
            'user_id': user_id,
            'billing_period': '2024-12-15',  # Previous period
            'billing_day': 15,
            'total_tokens': 800000,  # 80% usage in old period
            'token_limit': 1000000,
            'subscribed_at': '2024-12-15T10:00:00Z',
            'subscription_tier': 'plus'
        })

        from utils.token_usage_tracker import TokenUsageTracker

        # BEFORE boundary (Jan 14)
        print("\n--- BEFORE BILLING DAY (January 14, 2025) ---")
        with freeze_time("2025-01-14 23:00:00", tz_offset=0):
            tracker = TokenUsageTracker(table_name='test-token-usage', dynamodb_resource=dynamodb)

            result = tracker.check_limit(user_id)
            print_result("check_limit result", result)
            print(f"Expected billing_period: 2024-12-15")
            print(f"Expected total_tokens: 800000 (old period usage)")

        # AFTER boundary (Jan 15)
        print("\n--- AFTER BILLING DAY (January 15, 2025) ---")
        with freeze_time("2025-01-15 00:01:00", tz_offset=0):
            tracker = TokenUsageTracker(table_name='test-token-usage', dynamodb_resource=dynamodb)

            result = tracker.check_limit(user_id)
            print_result("check_limit result", result)
            print(f"Expected billing_period: 2025-01-15 (NEW PERIOD)")
            print(f"Expected total_tokens: 0 (fresh start!)")

            # Record first usage in new period
            print("\nRecording first usage in new period:")
            result = tracker.record_usage(user_id, 1000, 500)
            print_result("record_usage result", result)
            print(f"New period created with billing_day=15")

    setup_and_run()


def simulate_february_edge():
    """
    Scenario 4: February Edge Case with billing_day=31

    User subscribed on Jan 31. In February (28/29 days), the billing
    day should adjust to Feb 28 (or Feb 29 in leap years).
    """
    print_separator("Scenario: February Edge Case (billing_day=31)")

    if not HAS_MOTO or not HAS_FREEZEGUN:
        print("Missing dependencies. Install: pip install moto freezegun")
        return

    @mock_aws
    def run_scenario():
        os.environ['ENVIRONMENT'] = 'test'
        os.environ['TOKEN_USAGE_TABLE'] = 'test-token-usage'
        os.environ['DEFAULT_TOKEN_LIMIT'] = '1000000'

        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_mock_table(dynamodb)

        user_id = 'feb-edge-user'

        # Pre-populate: user subscribed on Jan 31
        table.put_item(Item={
            'user_id': user_id,
            'billing_period': '2025-01-31',
            'billing_day': 31,
            'total_tokens': 100000,
            'token_limit': 1000000,
            'subscribed_at': '2025-01-31T10:00:00Z',
            'subscription_tier': 'plus'
        })

        from utils.token_usage_tracker import TokenUsageTracker

        print(f"\nUser subscribed on: January 31, 2025")
        print(f"User billing_day: 31")

        # In February (non-leap year 2025)
        print("\n--- February 15, 2025 (non-leap year, Feb has 28 days) ---")
        with freeze_time("2025-02-15 10:00:00", tz_offset=0):
            tracker = TokenUsageTracker(table_name='test-token-usage', dynamodb_resource=dynamodb)

            # Get billing period
            period_key, start, end = tracker.get_current_billing_period(31)
            print(f"Billing period key: {period_key}")
            print(f"Period start: {start}")
            print(f"Period end: {end}")
            print(f"Expected: period started Jan 31, ends Feb 28")

            result = tracker.check_limit(user_id)
            print_result("check_limit result", result)

        # After Feb 28 (new period)
        print("\n--- March 1, 2025 (after Feb 28 boundary) ---")
        with freeze_time("2025-03-01 10:00:00", tz_offset=0):
            tracker = TokenUsageTracker(table_name='test-token-usage', dynamodb_resource=dynamodb)

            period_key, start, end = tracker.get_current_billing_period(31)
            print(f"Billing period key: {period_key}")
            print(f"Period start: {start}")
            print(f"Period end: {end}")
            print(f"Expected: NEW period starting Feb 28, ends Mar 31")

    run_scenario()


def simulate_year_rollover():
    """
    Scenario 5: Year Rollover (December → January)

    User subscribed mid-December. Shows the billing period
    correctly transitioning from Dec 2024 to Jan 2025.
    """
    print_separator("Scenario: Year Rollover (December → January)")

    if not HAS_MOTO or not HAS_FREEZEGUN:
        print("Missing dependencies. Install: pip install moto freezegun")
        return

    @mock_aws
    def run_scenario():
        os.environ['ENVIRONMENT'] = 'test'
        os.environ['TOKEN_USAGE_TABLE'] = 'test-token-usage'
        os.environ['DEFAULT_TOKEN_LIMIT'] = '1000000'

        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_mock_table(dynamodb)

        user_id = 'year-rollover-user'

        # Pre-populate: user subscribed on Dec 15, 2024
        table.put_item(Item={
            'user_id': user_id,
            'billing_period': '2024-12-15',
            'billing_day': 15,
            'total_tokens': 500000,
            'token_limit': 1000000,
            'subscribed_at': '2024-12-15T10:00:00Z',
            'subscription_tier': 'plus'
        })

        from utils.token_usage_tracker import TokenUsageTracker

        print(f"\nUser subscribed on: December 15, 2024")

        # December 31, 2024
        print("\n--- December 31, 2024 ---")
        with freeze_time("2024-12-31 23:00:00", tz_offset=0):
            tracker = TokenUsageTracker(table_name='test-token-usage', dynamodb_resource=dynamodb)

            result = tracker.check_limit(user_id)
            print_result("check_limit result", result)
            print(f"Expected: Still in 2024-12-15 period")

        # January 10, 2025 (still in Dec 15 - Jan 15 period)
        print("\n--- January 10, 2025 (before billing day) ---")
        with freeze_time("2025-01-10 10:00:00", tz_offset=0):
            tracker = TokenUsageTracker(table_name='test-token-usage', dynamodb_resource=dynamodb)

            result = tracker.check_limit(user_id)
            print_result("check_limit result", result)
            print(f"Expected: Still in 2024-12-15 period (crosses year boundary)")

        # January 16, 2025 (new period)
        print("\n--- January 16, 2025 (after billing day) ---")
        with freeze_time("2025-01-16 10:00:00", tz_offset=0):
            tracker = TokenUsageTracker(table_name='test-token-usage', dynamodb_resource=dynamodb)

            result = tracker.check_limit(user_id)
            print_result("check_limit result", result)
            print(f"Expected: NEW period 2025-01-15, usage reset to 0!")

    run_scenario()


def main():
    parser = argparse.ArgumentParser(
        description='Simulate anniversary-based token reset scenarios',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Scenarios:
  new_user        - New user's first request (billing_day set to today)
  mid_period      - Usage accumulation in middle of billing period
  period_boundary - Crossing from one period to the next
  february_edge   - billing_day=31 adjusting for February
  year_rollover   - December to January year transition
  all             - Run all scenarios

Example:
  python tests/local_simulate_anniversary_reset.py --scenario all
        """
    )
    parser.add_argument(
        '--scenario', '-s',
        choices=['new_user', 'mid_period', 'period_boundary', 'february_edge', 'year_rollover', 'all'],
        default='all',
        help='Which scenario to simulate'
    )

    args = parser.parse_args()

    scenarios = {
        'new_user': simulate_new_user,
        'mid_period': simulate_mid_period,
        'period_boundary': simulate_period_boundary,
        'february_edge': simulate_february_edge,
        'year_rollover': simulate_year_rollover,
    }

    if args.scenario == 'all':
        for name, func in scenarios.items():
            func()
    else:
        scenarios[args.scenario]()

    print_separator("Simulation Complete")
    print("\nAll scenarios use moto (mock DynamoDB) and freezegun (time simulation).")
    print("No actual AWS resources are affected.")


if __name__ == '__main__':
    main()
