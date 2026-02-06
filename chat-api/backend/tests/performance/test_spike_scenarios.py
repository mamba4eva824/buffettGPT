"""
Performance tests for spike and sustained-load webhook scenarios.

Tests the stripe_webhook_handler under various traffic patterns:
- Ramp from 0 to 100 concurrent webhooks over 5 seconds
- Sustained load at ~10/second for 30 seconds
- Spike-calm-spike recovery pattern
- Mixed event storm (all 6 types concurrently)
- Error rate measurement under load

Run with: pytest tests/performance/test_spike_scenarios.py -v -s
"""

import json
import time
from collections import defaultdict
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
    generate_subscription_created,
    generate_subscription_deleted,
    generate_subscription_updated,
)

# ---------------------------------------------------------------------------
# Configurable constants for sustained load test
# ---------------------------------------------------------------------------
SUSTAINED_RATE_PER_SECOND = 10
SUSTAINED_DURATION_SECONDS = 30
SUSTAINED_TOTAL_EVENTS = SUSTAINED_RATE_PER_SECOND * SUSTAINED_DURATION_SECONDS
SUSTAINED_SLEEP_INTERVAL = 1.0 / SUSTAINED_RATE_PER_SECOND


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
    api_event = _build_api_gateway_event(body=json.dumps(stripe_event))
    return handler.lambda_handler(api_event, None)


def _seed_user(users_table, user_id, customer_id):
    users_table.put_item(Item={
        'user_id': user_id,
        'stripe_customer_id': customer_id,
        'email': f'{user_id}@test.com',
        'subscription_tier': 'plus',
        'subscription_status': 'active',
        'billing_day': 15,
    })


def _generate_event_for_user(user_id, customer_id, kind):
    """Generate a webhook event of the given kind (0-5) for a specific user."""
    if kind == 0:
        return generate_checkout_completed(user_id=user_id, customer_id=customer_id)
    elif kind == 1:
        return generate_subscription_created(customer_id=customer_id, metadata={'user_id': user_id})
    elif kind == 2:
        return generate_subscription_updated(customer_id=customer_id)
    elif kind == 3:
        return generate_subscription_deleted(customer_id=customer_id)
    elif kind == 4:
        return generate_invoice_paid(customer_id=customer_id)
    else:
        return generate_invoice_failed(customer_id=customer_id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.performance
@mock_aws
@patch('handlers.stripe_webhook_handler.verify_webhook_signature')
def test_spike_0_to_100_in_5s(mock_verify):
    """Ramp load from 0 to 100 concurrent webhooks over 5 seconds (20/sec ramp rate).

    Pre-seeds 100 users. Records latency per second window. Prints a table
    showing latency at each second of the ramp. Verifies all events processed.
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    tables = _create_all_tables(dynamodb)

    import handlers.stripe_webhook_handler as handler
    handler.users_table = tables['users']
    handler.token_usage_table = tables['token_usage']
    handler.processed_events_table = tables['events']

    mock_verify.side_effect = lambda body, sig: json.loads(body) if isinstance(body, str) else body

    mc = MetricsCollector()

    # Pre-seed 100 users
    num_users = 100
    for i in range(num_users):
        _seed_user(tables['users'], f'user-{i}', f'cus_{i}')

    # Generate 100 events, cycling through types
    events = []
    for i in range(num_users):
        kind = i % 6
        events.append(_generate_event_for_user(f'user-{i}', f'cus_{i}', kind))

    # Track per-second results
    window_latencies = defaultdict(list)
    total_processed = 0
    total_errors = 0

    ramp_start = time.monotonic()

    # Ramp: 20 events per second for 5 seconds
    with ThreadPoolExecutor(max_workers=100) as pool:
        futures = {}
        event_idx = 0

        for second in range(5):
            batch_size = 20
            batch_events = events[event_idx:event_idx + batch_size]
            event_idx += batch_size

            for evt in batch_events:
                submit_time = time.monotonic()

                def _run(e=evt, sec=second, st=submit_time):
                    start = time.perf_counter()
                    resp = _invoke_handler(handler, e)
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    mc.record(f'window_{sec}', elapsed_ms)
                    mc.record('overall', elapsed_ms)
                    return resp, sec, elapsed_ms

                futures[pool.submit(_run)] = second

            # Wait ~1 second before next batch (account for time already spent)
            if second < 4:
                elapsed_in_second = time.monotonic() - ramp_start - second
                sleep_time = max(0, 1.0 - elapsed_in_second)
                time.sleep(sleep_time)

        # Collect results
        for fut in as_completed(futures):
            resp, sec, elapsed_ms = fut.result()
            window_latencies[sec].append(elapsed_ms)
            body = json.loads(resp['body'])
            if resp['statusCode'] == 200 and body.get('status') in ('ok', 'already_processed'):
                total_processed += 1
            else:
                total_errors += 1

    ramp_elapsed = time.monotonic() - ramp_start

    # Print summary table
    print(f"\n{'=' * 70}")
    print(f"  test_spike_0_to_100_in_5s - Ramp Load Results")
    print(f"{'=' * 70}")
    print(f"  {'Second':<10} {'Count':<10} {'p50 (ms)':<12} {'p95 (ms)':<12} {'p99 (ms)':<12}")
    print(f"  {'-' * 56}")

    for sec in range(5):
        pcts = mc.get_percentiles(f'window_{sec}')
        count = len(window_latencies.get(sec, []))
        p50 = f"{pcts['p50']:.3f}" if pcts['p50'] is not None else 'N/A'
        p95 = f"{pcts['p95']:.3f}" if pcts['p95'] is not None else 'N/A'
        p99 = f"{pcts['p99']:.3f}" if pcts['p99'] is not None else 'N/A'
        print(f"  {sec:<10} {count:<10} {p50:<12} {p95:<12} {p99:<12}")

    overall = mc.get_percentiles('overall')
    print(f"  {'-' * 56}")
    print(f"  {'Overall':<10} {total_processed:<10} "
          f"{overall['p50']:.3f}{'':>4} {overall['p95']:.3f}{'':>4} {overall['p99']:.3f}")
    print(f"\n  Total wall-clock: {ramp_elapsed:.3f} s")
    print(f"  Events processed: {total_processed}")
    print(f"  Errors:           {total_errors}")
    print(f"{'=' * 70}\n")

    # Assertions
    assert total_processed == 100, f"Expected 100 processed, got {total_processed}"
    assert total_errors == 0, f"Expected 0 errors, got {total_errors}"


@pytest.mark.performance
@mock_aws
@patch('handlers.stripe_webhook_handler.verify_webhook_signature')
def test_sustained_load_60s(mock_verify):
    """Submit webhooks at a sustained rate for a configurable duration.

    Uses SUSTAINED_RATE_PER_SECOND and SUSTAINED_DURATION_SECONDS constants.
    Pre-seeds 200 users and cycles through them. Tracks latency in 10-second
    windows. Verifies latency stays stable (p95 of last window within 2x of
    first window).
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    tables = _create_all_tables(dynamodb)

    import handlers.stripe_webhook_handler as handler
    handler.users_table = tables['users']
    handler.token_usage_table = tables['token_usage']
    handler.processed_events_table = tables['events']

    mock_verify.side_effect = lambda body, sig: json.loads(body) if isinstance(body, str) else body

    mc = MetricsCollector()

    # Pre-seed 200 users
    num_users = 200
    for i in range(num_users):
        _seed_user(tables['users'], f'user-{i}', f'cus_{i}')

    # Pre-generate all events
    events = []
    for i in range(SUSTAINED_TOTAL_EVENTS):
        user_idx = i % num_users
        kind = i % 6
        events.append(_generate_event_for_user(f'user-{user_idx}', f'cus_{user_idx}', kind))

    total_processed = 0
    total_errors = 0
    window_size = 10  # seconds per window

    start_time = time.monotonic()

    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = []

        for i, evt in enumerate(events):
            def _run(e=evt, idx=i):
                elapsed_since_start = time.monotonic() - start_time
                window = int(elapsed_since_start / window_size)
                window_name = f'window_{window}'

                start = time.perf_counter()
                resp = _invoke_handler(handler, e)
                elapsed_ms = (time.perf_counter() - start) * 1000
                mc.record(window_name, elapsed_ms)
                mc.record('overall', elapsed_ms)
                return resp

            futures.append(pool.submit(_run))

            # Pace submissions
            time.sleep(SUSTAINED_SLEEP_INTERVAL)

        # Collect results
        for fut in as_completed(futures):
            resp = fut.result()
            body = json.loads(resp['body'])
            if resp['statusCode'] == 200 and body.get('status') in ('ok', 'already_processed'):
                total_processed += 1
            else:
                total_errors += 1

    total_elapsed = time.monotonic() - start_time

    # Print summary
    overall = mc.get_percentiles('overall')
    num_windows = max(1, int(total_elapsed / window_size) + 1)

    print(f"\n{'=' * 70}")
    print(f"  test_sustained_load_60s - Sustained Load Results")
    print(f"  Config: {SUSTAINED_RATE_PER_SECOND}/sec for {SUSTAINED_DURATION_SECONDS}s "
          f"({SUSTAINED_TOTAL_EVENTS} total)")
    print(f"{'=' * 70}")
    print(f"  Overall p50: {overall['p50']:.3f} ms")
    print(f"  Overall p95: {overall['p95']:.3f} ms")
    print(f"  Overall p99: {overall['p99']:.3f} ms")
    print(f"  Total elapsed: {total_elapsed:.3f} s")
    print(f"  Events processed: {total_processed}")
    print(f"  Errors: {total_errors}")
    print(f"\n  {'Window':<10} {'Count':<10} {'p50 (ms)':<12} {'p95 (ms)':<12} {'Throughput':<12}")
    print(f"  {'-' * 56}")

    first_window_p95 = None
    last_window_p95 = None

    for w in range(num_windows):
        wname = f'window_{w}'
        pcts = mc.get_percentiles(wname)
        samples = mc._samples.get(wname, [])
        count = len(samples)
        if count == 0:
            continue

        throughput = count / window_size
        p50 = f"{pcts['p50']:.3f}" if pcts['p50'] is not None else 'N/A'
        p95_val = pcts['p95']
        p95_str = f"{p95_val:.3f}" if p95_val is not None else 'N/A'
        print(f"  {w:<10} {count:<10} {p50:<12} {p95_str:<12} {throughput:.1f}/s")

        if p95_val is not None:
            if first_window_p95 is None:
                first_window_p95 = p95_val
            last_window_p95 = p95_val

    print(f"{'=' * 70}\n")

    # Assertions
    assert total_processed > 0, "Should have processed at least some events"
    assert total_processed + total_errors == SUSTAINED_TOTAL_EVENTS, \
        f"Expected {SUSTAINED_TOTAL_EVENTS} total, got {total_processed + total_errors}"

    # Verify latency stability: last window p95 within 2x of first window p95
    if first_window_p95 is not None and last_window_p95 is not None:
        ratio = last_window_p95 / first_window_p95 if first_window_p95 > 0 else 1.0
        print(f"  Latency stability: first_p95={first_window_p95:.3f}ms, "
              f"last_p95={last_window_p95:.3f}ms, ratio={ratio:.2f}x")
        assert ratio <= 2.0, (
            f"Latency degraded: last window p95 ({last_window_p95:.3f}ms) > "
            f"2x first window p95 ({first_window_p95:.3f}ms)"
        )


@pytest.mark.performance
@mock_aws
@patch('handlers.stripe_webhook_handler.verify_webhook_signature')
def test_spike_recovery_pattern(mock_verify):
    """Three phases: spike -> calm -> spike. Verifies recovery.

    Phase 1 (Spike): 100 concurrent events in ~1 second
    Phase 2 (Calm):  10 events/second for 5 seconds (50 total)
    Phase 3 (Spike): 100 concurrent events in ~1 second

    Tracks latency separately per phase. Verifies second spike performs
    similarly to the first (recovery confirmation).
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    tables = _create_all_tables(dynamodb)

    import handlers.stripe_webhook_handler as handler
    handler.users_table = tables['users']
    handler.token_usage_table = tables['token_usage']
    handler.processed_events_table = tables['events']

    mock_verify.side_effect = lambda body, sig: json.loads(body) if isinstance(body, str) else body

    mc = MetricsCollector()

    # Pre-seed 250 users (100 + 50 + 100)
    num_users = 250
    for i in range(num_users):
        _seed_user(tables['users'], f'user-{i}', f'cus_{i}')

    # Pre-generate events for each phase
    def _make_events(start_idx, count):
        evts = []
        for i in range(count):
            idx = start_idx + i
            user_idx = idx % num_users
            kind = idx % 6
            evts.append(_generate_event_for_user(f'user-{user_idx}', f'cus_{user_idx}', kind))
        return evts

    spike1_events = _make_events(0, 100)
    calm_events = _make_events(100, 50)
    spike2_events = _make_events(150, 100)

    phase_results = {'spike_1': {'processed': 0, 'errors': 0},
                     'calm': {'processed': 0, 'errors': 0},
                     'spike_2': {'processed': 0, 'errors': 0}}

    def _run_event(evt, phase_name):
        start = time.perf_counter()
        resp = _invoke_handler(handler, evt)
        elapsed_ms = (time.perf_counter() - start) * 1000
        mc.record(phase_name, elapsed_ms)
        return resp, phase_name

    def _run_spike(events, phase_name):
        with ThreadPoolExecutor(max_workers=100) as pool:
            futures = [pool.submit(_run_event, evt, phase_name) for evt in events]
            for fut in as_completed(futures):
                resp, pname = fut.result()
                body = json.loads(resp['body'])
                if resp['statusCode'] == 200 and body.get('status') in ('ok', 'already_processed'):
                    phase_results[pname]['processed'] += 1
                else:
                    phase_results[pname]['errors'] += 1

    # Phase 1: Spike
    _run_spike(spike1_events, 'spike_1')

    # Phase 2: Calm (10 events/second for 5 seconds)
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = []
        for i, evt in enumerate(calm_events):
            futures.append(pool.submit(_run_event, evt, 'calm'))
            time.sleep(0.1)  # 10/second

        for fut in as_completed(futures):
            resp, pname = fut.result()
            body = json.loads(resp['body'])
            if resp['statusCode'] == 200 and body.get('status') in ('ok', 'already_processed'):
                phase_results[pname]['processed'] += 1
            else:
                phase_results[pname]['errors'] += 1

    # Phase 3: Spike
    _run_spike(spike2_events, 'spike_2')

    # Print comparison table
    print(f"\n{'=' * 70}")
    print(f"  test_spike_recovery_pattern - Spike/Calm/Spike Results")
    print(f"{'=' * 70}")
    print(f"  {'Phase':<15} {'Count':<10} {'Processed':<12} {'Errors':<10} "
          f"{'p50 (ms)':<12} {'p95 (ms)':<12} {'p99 (ms)':<12}")
    print(f"  {'-' * 83}")

    for phase_name, label, count in [('spike_1', 'Spike 1', 100),
                                      ('calm', 'Calm', 50),
                                      ('spike_2', 'Spike 2', 100)]:
        pcts = mc.get_percentiles(phase_name)
        proc = phase_results[phase_name]['processed']
        errs = phase_results[phase_name]['errors']
        p50 = f"{pcts['p50']:.3f}" if pcts['p50'] is not None else 'N/A'
        p95 = f"{pcts['p95']:.3f}" if pcts['p95'] is not None else 'N/A'
        p99 = f"{pcts['p99']:.3f}" if pcts['p99'] is not None else 'N/A'
        print(f"  {label:<15} {count:<10} {proc:<12} {errs:<10} {p50:<12} {p95:<12} {p99:<12}")

    print(f"{'=' * 70}\n")

    # Assertions: all events processed
    total_processed = sum(r['processed'] for r in phase_results.values())
    total_errors = sum(r['errors'] for r in phase_results.values())
    assert total_processed == 250, f"Expected 250 processed, got {total_processed}"
    assert total_errors == 0, f"Expected 0 errors, got {total_errors}"

    # Recovery check: spike_2 p95 within 2x of spike_1 p95
    spike1_pcts = mc.get_percentiles('spike_1')
    spike2_pcts = mc.get_percentiles('spike_2')
    if spike1_pcts['p95'] is not None and spike2_pcts['p95'] is not None and spike1_pcts['p95'] > 0:
        ratio = spike2_pcts['p95'] / spike1_pcts['p95']
        print(f"  Recovery ratio: spike_2 p95 / spike_1 p95 = {ratio:.2f}x")
        assert ratio <= 2.0, (
            f"Recovery failed: spike_2 p95 ({spike2_pcts['p95']:.3f}ms) > "
            f"2x spike_1 p95 ({spike1_pcts['p95']:.3f}ms)"
        )


@pytest.mark.performance
@mock_aws
@patch('handlers.stripe_webhook_handler.verify_webhook_signature')
def test_mixed_event_storm(mock_verify):
    """Generate 100 events (~17 of each of 6 types) submitted concurrently.

    Verifies each event type was handled by checking the processed events table.
    Tracks distribution of event types processed. Prints distribution table.
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    tables = _create_all_tables(dynamodb)

    import handlers.stripe_webhook_handler as handler
    handler.users_table = tables['users']
    handler.token_usage_table = tables['token_usage']
    handler.processed_events_table = tables['events']

    mock_verify.side_effect = lambda body, sig: json.loads(body) if isinstance(body, str) else body

    mc = MetricsCollector()

    # Pre-seed 100 users
    num_users = 100
    for i in range(num_users):
        _seed_user(tables['users'], f'user-{i}', f'cus_{i}')

    # Generate ~17 of each type (6 types, totaling 100: 17*5 + 15 = 100, use 16+17 mix)
    # Simpler: 17 each for first 4 types, 16 each for last 2 types = 17*4 + 16*2 = 68+32=100
    event_type_names = [
        'checkout.session.completed',
        'customer.subscription.created',
        'customer.subscription.updated',
        'customer.subscription.deleted',
        'invoice.payment_succeeded',
        'invoice.payment_failed',
    ]
    events = []
    event_id_to_type = {}
    type_counts_generated = defaultdict(int)

    for i in range(100):
        kind = i % 6
        user_idx = i % num_users
        evt = _generate_event_for_user(f'user-{user_idx}', f'cus_{user_idx}', kind)
        events.append(evt)
        event_id_to_type[evt['id']] = evt['type']
        type_counts_generated[evt['type']] += 1

    # Verify we have events of all 6 types
    assert len(type_counts_generated) == 6, f"Expected 6 types, got {len(type_counts_generated)}"

    total_processed = 0
    total_errors = 0
    type_counts_processed = defaultdict(int)

    def _run_one(evt):
        start = time.perf_counter()
        resp = _invoke_handler(handler, evt)
        elapsed_ms = (time.perf_counter() - start) * 1000
        mc.record('storm', elapsed_ms)
        return resp, evt['id'], evt['type']

    with ThreadPoolExecutor(max_workers=50) as pool:
        futures = [pool.submit(_run_one, evt) for evt in events]
        for fut in as_completed(futures):
            resp, event_id, event_type = fut.result()
            body = json.loads(resp['body'])
            if resp['statusCode'] == 200 and body.get('status') in ('ok', 'already_processed'):
                total_processed += 1
                type_counts_processed[event_type] += 1
            else:
                total_errors += 1

    # Verify events are in the processed events table
    processed_event_ids = set()
    scan_result = tables['events'].scan()
    for item in scan_result.get('Items', []):
        processed_event_ids.add(item['event_id'])

    # Print distribution table
    pcts = mc.get_percentiles('storm')
    print(f"\n{'=' * 70}")
    print(f"  test_mixed_event_storm - Event Distribution")
    print(f"{'=' * 70}")
    print(f"  {'Event Type':<40} {'Generated':<12} {'Processed':<12}")
    print(f"  {'-' * 64}")
    for etype in event_type_names:
        gen = type_counts_generated.get(etype, 0)
        proc = type_counts_processed.get(etype, 0)
        print(f"  {etype:<40} {gen:<12} {proc:<12}")
    print(f"  {'-' * 64}")
    print(f"  {'TOTAL':<40} {100:<12} {total_processed:<12}")
    print(f"\n  p50: {pcts['p50']:.3f} ms  |  p95: {pcts['p95']:.3f} ms  |  p99: {pcts['p99']:.3f} ms")
    print(f"  Errors: {total_errors}")
    print(f"  Events in processed table: {len(processed_event_ids)}")
    print(f"{'=' * 70}\n")

    # Assertions
    assert total_processed == 100, f"Expected 100 processed, got {total_processed}"
    assert total_errors == 0, f"Expected 0 errors, got {total_errors}"

    # Verify all 6 event types were processed
    for etype in event_type_names:
        assert type_counts_processed[etype] > 0, f"Event type {etype} was not processed"

    # Verify events are in the processed events table
    for evt in events:
        assert evt['id'] in processed_event_ids, \
            f"Event {evt['id']} ({evt['type']}) not found in processed events table"


@pytest.mark.performance
@mock_aws
@patch('handlers.stripe_webhook_handler.verify_webhook_signature')
def test_error_rate_under_load(mock_verify):
    """90 valid events + 10 invalid events submitted concurrently.

    Invalid events are checkout.session.completed events with user_ids that
    do not exist in the users table, causing handle_checkout_completed to
    raise ValueError.

    Verifies ~90 succeed (200) and ~10 return 500.
    Calculates and reports error rate. Verifies error rate is approximately 10%.
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    tables = _create_all_tables(dynamodb)

    import handlers.stripe_webhook_handler as handler
    handler.users_table = tables['users']
    handler.token_usage_table = tables['token_usage']
    handler.processed_events_table = tables['events']

    mock_verify.side_effect = lambda body, sig: json.loads(body) if isinstance(body, str) else body

    mc = MetricsCollector()

    # Pre-seed 90 users for valid events
    num_valid = 90
    for i in range(num_valid):
        _seed_user(tables['users'], f'user-{i}', f'cus_{i}')

    # Generate 90 valid events (use checkout events since they clearly succeed/fail)
    valid_events = []
    for i in range(num_valid):
        kind = i % 6
        valid_events.append(_generate_event_for_user(f'user-{i}', f'cus_{i}', kind))

    # Generate 10 invalid events: checkout events with non-existent user_ids
    invalid_events = []
    for i in range(10):
        evt = generate_checkout_completed(user_id=f'nonexistent-user-{i}')
        invalid_events.append(evt)

    all_events = valid_events + invalid_events

    success_count = 0
    error_count = 0
    status_codes = defaultdict(int)

    def _run_one(evt):
        start = time.perf_counter()
        resp = _invoke_handler(handler, evt)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if resp['statusCode'] == 200:
            mc.record('success', elapsed_ms)
        else:
            mc.record('error', elapsed_ms)
            mc.record_error('overall')
        mc.record('all', elapsed_ms)
        return resp

    with ThreadPoolExecutor(max_workers=50) as pool:
        futures = [pool.submit(_run_one, evt) for evt in all_events]
        for fut in as_completed(futures):
            resp = fut.result()
            status_codes[resp['statusCode']] += 1
            if resp['statusCode'] == 200:
                success_count += 1
            else:
                error_count += 1

    total = success_count + error_count
    error_rate = error_count / total if total > 0 else 0.0

    # Print summary
    all_pcts = mc.get_percentiles('all')
    success_pcts = mc.get_percentiles('success')
    error_pcts = mc.get_percentiles('error')

    print(f"\n{'=' * 70}")
    print(f"  test_error_rate_under_load - Error Rate Analysis")
    print(f"{'=' * 70}")
    print(f"  Total events:     {total}")
    print(f"  Successes (200):  {success_count}")
    print(f"  Errors (non-200): {error_count}")
    print(f"  Error rate:       {error_rate:.1%}")
    print(f"\n  Status code distribution:")
    for code, count in sorted(status_codes.items()):
        print(f"    {code}: {count}")
    print(f"\n  {'Metric':<15} {'p50 (ms)':<12} {'p95 (ms)':<12} {'p99 (ms)':<12}")
    print(f"  {'-' * 51}")
    for label, pcts in [('All', all_pcts), ('Success', success_pcts), ('Error', error_pcts)]:
        p50 = f"{pcts['p50']:.3f}" if pcts['p50'] is not None else 'N/A'
        p95 = f"{pcts['p95']:.3f}" if pcts['p95'] is not None else 'N/A'
        p99 = f"{pcts['p99']:.3f}" if pcts['p99'] is not None else 'N/A'
        print(f"  {label:<15} {p50:<12} {p95:<12} {p99:<12}")
    print(f"{'=' * 70}\n")

    # Assertions
    assert success_count == 90, f"Expected 90 successes, got {success_count}"
    assert error_count == 10, f"Expected 10 errors, got {error_count}"
    assert 0.05 <= error_rate <= 0.15, f"Error rate {error_rate:.1%} not approximately 10%"
