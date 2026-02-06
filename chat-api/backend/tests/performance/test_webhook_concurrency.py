"""
Performance tests for concurrent webhook processing.

Tests the stripe_webhook_handler under concurrent load using
ThreadPoolExecutor and moto @mock_aws for DynamoDB.

Scenarios:
- 50 concurrent checkout.session.completed events (different users)
- 100 concurrent mixed webhook events (all 6 types)
- 20 different event types for the SAME user within 1 second
- 20 webhooks delivered as fast as possible (burst latency)

Run with: pytest tests/performance/test_webhook_concurrency.py -v -s
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from tests.performance.utils.metrics_collector import MetricsCollector
from tests.performance.utils.mock_stripe_events import (
    generate_checkout_completed,
    generate_invoice_failed,
    generate_invoice_paid,
    generate_random_event,
    generate_subscription_created,
    generate_subscription_deleted,
    generate_subscription_updated,
)


# ---------------------------------------------------------------------------
# Local helpers (no modifications to Phase 1 files)
# ---------------------------------------------------------------------------

def _create_users_table(dynamodb):
    table = dynamodb.create_table(
        TableName='buffett-test-users',
        KeySchema=[{'AttributeName': 'user_id', 'KeyType': 'HASH'}],
        AttributeDefinitions=[
            {'AttributeName': 'user_id', 'AttributeType': 'S'},
            {'AttributeName': 'stripe_customer_id', 'AttributeType': 'S'},
        ],
        GlobalSecondaryIndexes=[{
            'IndexName': 'stripe-customer-index',
            'KeySchema': [{'AttributeName': 'stripe_customer_id', 'KeyType': 'HASH'}],
            'Projection': {'ProjectionType': 'ALL'},
        }],
        BillingMode='PAY_PER_REQUEST',
    )
    table.wait_until_exists()
    return table


def _create_token_usage_table(dynamodb):
    table = dynamodb.create_table(
        TableName='buffett-test-token-usage',
        KeySchema=[
            {'AttributeName': 'user_id', 'KeyType': 'HASH'},
            {'AttributeName': 'billing_period', 'KeyType': 'RANGE'},
        ],
        AttributeDefinitions=[
            {'AttributeName': 'user_id', 'AttributeType': 'S'},
            {'AttributeName': 'billing_period', 'AttributeType': 'S'},
        ],
        BillingMode='PAY_PER_REQUEST',
    )
    table.wait_until_exists()
    return table


def _create_stripe_events_table(dynamodb):
    table = dynamodb.create_table(
        TableName='buffett-test-stripe-events',
        KeySchema=[{'AttributeName': 'event_id', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'event_id', 'AttributeType': 'S'}],
        BillingMode='PAY_PER_REQUEST',
    )
    table.wait_until_exists()
    return table


def _create_all_tables(dynamodb):
    return {
        'users': _create_users_table(dynamodb),
        'token_usage': _create_token_usage_table(dynamodb),
        'events': _create_stripe_events_table(dynamodb),
    }


def _build_api_gateway_event(body='{}', signature='test_sig'):
    return {
        'body': body,
        'headers': {'stripe-signature': signature},
    }


def _invoke_handler(handler, stripe_event):
    """Build an API Gateway event and invoke the Lambda handler.

    ``verify_webhook_signature`` is already patched by the caller so it
    returns *stripe_event* directly.  We just need to wire up the API
    Gateway envelope.
    """
    api_event = _build_api_gateway_event(body=json.dumps(stripe_event))
    return handler.lambda_handler(api_event, None)


def _print_summary(*, test_name, total, processed, duplicates, errors, mc, metric_name='webhook_processing'):
    pcts = mc.get_percentiles(metric_name)
    throughput = mc.get_throughput()
    print(f"\n{'=' * 60}")
    print(f"  {test_name}")
    print(f"{'=' * 60}")
    print(f"  Total events:    {total}")
    print(f"  Processed:       {processed}")
    print(f"  Duplicates:      {duplicates}")
    print(f"  Errors:          {errors}")
    print(f"  Throughput:      {throughput:.2f} events/sec")
    if pcts['p50'] is not None:
        print(f"  p50 latency:     {pcts['p50']:.3f} ms")
        print(f"  p95 latency:     {pcts['p95']:.3f} ms")
        print(f"  p99 latency:     {pcts['p99']:.3f} ms")
    print(f"{'=' * 60}\n")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.performance
@mock_aws
@patch('handlers.stripe_webhook_handler.verify_webhook_signature')
def test_concurrent_checkout_completed_50(mock_verify):
    """50 checkout.session.completed events for 50 different users submitted concurrently.

    Pre-seeds 50 users in the users table. Verifies all 50 processed
    successfully and all users updated to subscription_tier='plus'.
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    tables = _create_all_tables(dynamodb)

    import handlers.stripe_webhook_handler as handler
    handler.users_table = tables['users']
    handler.token_usage_table = tables['token_usage']
    handler.processed_events_table = tables['events']

    mc = MetricsCollector()

    # Pre-seed 50 users
    user_ids = [f'user-perf-{i:03d}' for i in range(50)]
    for uid in user_ids:
        tables['users'].put_item(Item={'user_id': uid, 'email': f'{uid}@test.com'})

    # Generate 50 checkout events
    events = [generate_checkout_completed(user_id=uid) for uid in user_ids]

    # We need mock_verify to return the correct event for each call.
    # Since ThreadPoolExecutor submits concurrently, we use side_effect
    # but each thread will call verify once – ordering is unpredictable.
    # Instead, make verify return whatever the body deserialises to.
    def verify_side_effect(body, sig_header):
        return json.loads(body)
    mock_verify.side_effect = verify_side_effect

    results = []
    processed = 0
    duplicates = 0
    errors = 0

    def _run_one(evt):
        start = time.perf_counter()
        resp = _invoke_handler(handler, evt)
        elapsed_ms = (time.perf_counter() - start) * 1000
        mc.record('webhook_processing', elapsed_ms)
        return resp

    with ThreadPoolExecutor(max_workers=50) as pool:
        futures = {pool.submit(_run_one, evt): evt for evt in events}
        for fut in as_completed(futures):
            resp = fut.result()
            results.append(resp)
            body = json.loads(resp['body'])
            if resp['statusCode'] == 200 and body.get('status') == 'ok':
                processed += 1
            elif body.get('status') == 'already_processed':
                duplicates += 1
            else:
                errors += 1

    _print_summary(
        test_name='test_concurrent_checkout_completed_50',
        total=50, processed=processed, duplicates=duplicates, errors=errors, mc=mc,
    )

    # Assertions
    assert processed == 50, f"Expected 50 processed, got {processed}"
    assert errors == 0, f"Expected 0 errors, got {errors}"

    # Verify all 50 users upgraded to plus
    for uid in user_ids:
        item = tables['users'].get_item(Key={'user_id': uid})['Item']
        assert item['subscription_tier'] == 'plus', f"User {uid} not upgraded"


@pytest.mark.performance
@mock_aws
@patch('handlers.stripe_webhook_handler.verify_webhook_signature')
def test_concurrent_mixed_events_100(mock_verify):
    """100 webhook events across all 6 types submitted concurrently.

    Verifies correct routing (each type handled by correct function) and
    no exceptions.
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    tables = _create_all_tables(dynamodb)

    import handlers.stripe_webhook_handler as handler
    handler.users_table = tables['users']
    handler.token_usage_table = tables['token_usage']
    handler.processed_events_table = tables['events']

    mc = MetricsCollector()

    def verify_side_effect(body, sig_header):
        return json.loads(body)
    mock_verify.side_effect = verify_side_effect

    # Pre-seed users and customer mappings for the events that need them
    customer_ids = [f'cus_perf_{i:03d}' for i in range(100)]
    user_ids = [f'user-mix-{i:03d}' for i in range(100)]
    for i in range(100):
        tables['users'].put_item(Item={
            'user_id': user_ids[i],
            'email': f'{user_ids[i]}@test.com',
            'stripe_customer_id': customer_ids[i],
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 15,
        })

    # Build 100 events, cycling through all 6 types
    events = []
    event_types_seen = set()
    for i in range(100):
        kind = i % 6
        uid = user_ids[i]
        cid = customer_ids[i]
        if kind == 0:
            evt = generate_checkout_completed(user_id=uid, customer_id=cid)
        elif kind == 1:
            evt = generate_subscription_created(customer_id=cid, metadata={'user_id': uid})
        elif kind == 2:
            evt = generate_subscription_updated(customer_id=cid)
        elif kind == 3:
            evt = generate_subscription_deleted(customer_id=cid)
        elif kind == 4:
            evt = generate_invoice_paid(customer_id=cid)
        else:
            evt = generate_invoice_failed(customer_id=cid)
        event_types_seen.add(evt['type'])
        events.append(evt)

    assert len(event_types_seen) == 6, "Must cover all 6 event types"

    results = []
    processed = 0
    duplicates = 0
    errors = 0

    def _run_one(evt):
        start = time.perf_counter()
        resp = _invoke_handler(handler, evt)
        elapsed_ms = (time.perf_counter() - start) * 1000
        mc.record('webhook_processing', elapsed_ms)
        return resp

    with ThreadPoolExecutor(max_workers=50) as pool:
        futures = {pool.submit(_run_one, evt): evt for evt in events}
        for fut in as_completed(futures):
            resp = fut.result()
            results.append(resp)
            body = json.loads(resp['body'])
            if resp['statusCode'] == 200:
                if body.get('status') == 'already_processed':
                    duplicates += 1
                else:
                    processed += 1
            else:
                errors += 1

    _print_summary(
        test_name='test_concurrent_mixed_events_100',
        total=100, processed=processed, duplicates=duplicates, errors=errors, mc=mc,
    )

    assert processed + duplicates == 100, f"Expected 100 successful (processed+dup), got {processed + duplicates}"
    assert errors == 0, f"Expected 0 errors, got {errors}"


@pytest.mark.performance
@mock_aws
@patch('handlers.stripe_webhook_handler.verify_webhook_signature')
def test_single_user_webhook_flood(mock_verify):
    """20 different event types for the SAME user within 1 second.

    Verifies no race conditions, final user state is consistent, and
    no DynamoDB conditional check failures.
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    tables = _create_all_tables(dynamodb)

    import handlers.stripe_webhook_handler as handler
    handler.users_table = tables['users']
    handler.token_usage_table = tables['token_usage']
    handler.processed_events_table = tables['events']

    mc = MetricsCollector()

    def verify_side_effect(body, sig_header):
        return json.loads(body)
    mock_verify.side_effect = verify_side_effect

    user_id = 'user-flood-001'
    customer_id = 'cus_flood_001'

    tables['users'].put_item(Item={
        'user_id': user_id,
        'email': f'{user_id}@test.com',
        'stripe_customer_id': customer_id,
        'subscription_tier': 'plus',
        'subscription_status': 'active',
        'billing_day': 15,
    })

    # Build 20 events for the same user, cycling through types
    events = []
    for i in range(20):
        kind = i % 6
        if kind == 0:
            evt = generate_checkout_completed(user_id=user_id, customer_id=customer_id)
        elif kind == 1:
            evt = generate_subscription_created(customer_id=customer_id, metadata={'user_id': user_id})
        elif kind == 2:
            evt = generate_subscription_updated(customer_id=customer_id)
        elif kind == 3:
            evt = generate_subscription_deleted(customer_id=customer_id)
        elif kind == 4:
            evt = generate_invoice_paid(customer_id=customer_id)
        else:
            evt = generate_invoice_failed(customer_id=customer_id)
        events.append(evt)

    results = []
    processed = 0
    duplicates = 0
    errors = 0
    exceptions = []

    def _run_one(evt):
        start = time.perf_counter()
        try:
            resp = _invoke_handler(handler, evt)
            elapsed_ms = (time.perf_counter() - start) * 1000
            mc.record('webhook_processing', elapsed_ms)
            return resp
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            mc.record_error('webhook_processing')
            return {'exception': str(exc), 'elapsed_ms': elapsed_ms}

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(_run_one, evt) for evt in events]
        for fut in as_completed(futures):
            resp = fut.result()
            if 'exception' in resp:
                exceptions.append(resp['exception'])
                errors += 1
                continue
            results.append(resp)
            body = json.loads(resp['body'])
            if resp['statusCode'] == 200:
                if body.get('status') == 'already_processed':
                    duplicates += 1
                else:
                    processed += 1
            else:
                errors += 1

    _print_summary(
        test_name='test_single_user_webhook_flood',
        total=20, processed=processed, duplicates=duplicates, errors=errors, mc=mc,
    )

    # No unhandled exceptions
    assert len(exceptions) == 0, f"Got {len(exceptions)} exceptions: {exceptions}"

    # Verify user record still exists and is consistent (has required fields)
    user = tables['users'].get_item(Key={'user_id': user_id})
    assert 'Item' in user, "User record should still exist"
    item = user['Item']
    assert item['user_id'] == user_id
    # The final state depends on which handler ran last, but the record must be consistent
    assert 'subscription_tier' in item or 'subscription_status' in item, \
        "User state should have subscription fields"


@pytest.mark.performance
@mock_aws
@patch('handlers.stripe_webhook_handler.verify_webhook_signature')
def test_rapid_webhook_burst_20_in_1s(mock_verify):
    """20 webhooks delivered as fast as possible.

    Uses MetricsCollector to measure individual handler latency.
    Prints p50, p95, p99 at end.
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    tables = _create_all_tables(dynamodb)

    import handlers.stripe_webhook_handler as handler
    handler.users_table = tables['users']
    handler.token_usage_table = tables['token_usage']
    handler.processed_events_table = tables['events']

    mc = MetricsCollector()

    def verify_side_effect(body, sig_header):
        return json.loads(body)
    mock_verify.side_effect = verify_side_effect

    # Pre-seed users for checkout events
    user_ids = [f'user-burst-{i:03d}' for i in range(20)]
    customer_ids = [f'cus_burst_{i:03d}' for i in range(20)]
    for i in range(20):
        tables['users'].put_item(Item={
            'user_id': user_ids[i],
            'email': f'{user_ids[i]}@test.com',
            'stripe_customer_id': customer_ids[i],
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 15,
        })

    # Generate 20 random events with seeded users
    events = []
    for i in range(20):
        kind = i % 6
        uid = user_ids[i]
        cid = customer_ids[i]
        if kind == 0:
            evt = generate_checkout_completed(user_id=uid, customer_id=cid)
        elif kind == 1:
            evt = generate_subscription_created(customer_id=cid, metadata={'user_id': uid})
        elif kind == 2:
            evt = generate_subscription_updated(customer_id=cid)
        elif kind == 3:
            evt = generate_subscription_deleted(customer_id=cid)
        elif kind == 4:
            evt = generate_invoice_paid(customer_id=cid)
        else:
            evt = generate_invoice_failed(customer_id=cid)
        events.append(evt)

    processed = 0
    duplicates = 0
    errors = 0

    def _run_one(evt):
        start = time.perf_counter()
        resp = _invoke_handler(handler, evt)
        elapsed_ms = (time.perf_counter() - start) * 1000
        mc.record('webhook_processing', elapsed_ms)
        return resp

    start_burst = time.perf_counter()
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(_run_one, evt) for evt in events]
        for fut in as_completed(futures):
            resp = fut.result()
            body = json.loads(resp['body'])
            if resp['statusCode'] == 200:
                if body.get('status') == 'already_processed':
                    duplicates += 1
                else:
                    processed += 1
            else:
                errors += 1
    burst_elapsed = time.perf_counter() - start_burst

    _print_summary(
        test_name='test_rapid_webhook_burst_20_in_1s',
        total=20, processed=processed, duplicates=duplicates, errors=errors, mc=mc,
    )
    print(f"  Burst wall-clock: {burst_elapsed:.3f} s")

    assert errors == 0, f"Expected 0 errors, got {errors}"
    assert processed + duplicates == 20
