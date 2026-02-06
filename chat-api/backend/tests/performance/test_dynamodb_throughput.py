"""
Phase 3 – DynamoDB Throughput & Latency Tests

Tests DynamoDB operations under concurrent load using moto @mock_aws:
- GSI query performance at scale
- GSI vs scan comparison
- Concurrent user updates
- Token usage write throughput
- Conditional update contention
- Batch read/write cycles

Run with: pytest tests/performance/test_dynamodb_throughput.py -v -s
"""

import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from tests.performance.utils.metrics_collector import MetricsCollector
from tests.performance.conftest import (
    create_users_table,
    create_token_usage_table,
    create_stripe_events_table,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_metrics_summary(name: str, mc: MetricsCollector, metric_key: str):
    """Print a formatted metrics summary for a single benchmark."""
    pcts = mc.get_percentiles(metric_key)
    samples = mc._samples.get(metric_key, [])
    count = len(samples)
    elapsed = time.monotonic() - mc._start_time
    throughput = count / elapsed if elapsed > 0 else 0.0

    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    print(f"  Operations : {count}")
    print(f"  Elapsed    : {elapsed:.3f}s")
    print(f"  Throughput : {throughput:.1f} ops/sec")
    if pcts['p50'] is not None:
        print(f"  p50        : {pcts['p50']:.3f} ms")
        print(f"  p95        : {pcts['p95']:.3f} ms")
        print(f"  p99        : {pcts['p99']:.3f} ms")
    if samples:
        print(f"  min        : {min(samples):.3f} ms")
        print(f"  max        : {max(samples):.3f} ms")
    print(f"{'='*60}")


def _seed_users(table, count: int, *, with_stripe=True, with_billing_day=False):
    """Pre-seed users table with realistic data. Returns list of user dicts."""
    users = []
    for i in range(count):
        user_id = f"user-{uuid.uuid4().hex[:12]}"
        item = {
            'user_id': user_id,
            'email': f"user{i}@example.com",
            'name': f"Test User {i}",
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'created_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        }
        if with_stripe:
            item['stripe_customer_id'] = f"cus_{uuid.uuid4().hex[:14]}"
        if with_billing_day:
            item['billing_day'] = 15
        table.put_item(Item=item)
        users.append(item)
    return users


# ---------------------------------------------------------------------------
# Aggregate results store (module-level) for final summary
# ---------------------------------------------------------------------------

_BENCHMARK_RESULTS: dict = {}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.performance
class TestDynamoDBThroughput:
    """DynamoDB throughput and latency benchmarks."""

    # -----------------------------------------------------------------------
    # test_gsi_query_performance_100
    # -----------------------------------------------------------------------
    @mock_aws
    def test_gsi_query_performance_100(self):
        """Pre-seed 100 users, run 100 concurrent GSI queries via _find_user_by_customer_id."""
        os.environ['ENVIRONMENT'] = 'test'
        os.environ['USERS_TABLE'] = 'buffett-test-users'

        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_users_table(dynamodb)
        users = _seed_users(table, 100, with_stripe=True)

        # Re-import handler so module-level globals use mocked DynamoDB
        import importlib
        import handlers.stripe_webhook_handler as handler_mod
        handler_mod.dynamodb = dynamodb
        handler_mod.users_table = dynamodb.Table('buffett-test-users')

        mc = MetricsCollector()

        def query_gsi(user):
            start = time.perf_counter()
            result = handler_mod._find_user_by_customer_id(user['stripe_customer_id'])
            elapsed_ms = (time.perf_counter() - start) * 1000
            mc.record('gsi_query', elapsed_ms)
            return result

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(query_gsi, u) for u in users]
            results = [f.result() for f in as_completed(futures)]

        # All queries must return a user
        assert all(r is not None for r in results), "Some GSI queries returned None"
        assert len(results) == 100

        _print_metrics_summary("GSI Query Performance (100 concurrent)", mc, 'gsi_query')
        _BENCHMARK_RESULTS['gsi_query_100'] = mc.generate_report()

    # -----------------------------------------------------------------------
    # test_gsi_vs_scan_comparison
    # -----------------------------------------------------------------------
    @mock_aws
    def test_gsi_vs_scan_comparison(self):
        """Compare GSI query vs table scan latency for 100 pre-seeded users."""
        os.environ['ENVIRONMENT'] = 'test'
        os.environ['USERS_TABLE'] = 'buffett-test-users'

        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_users_table(dynamodb)
        users = _seed_users(table, 100, with_stripe=True)

        mc = MetricsCollector()

        # GSI queries (50 lookups)
        def gsi_lookup(customer_id):
            start = time.perf_counter()
            resp = table.query(
                IndexName='stripe-customer-index',
                KeyConditionExpression='stripe_customer_id = :cid',
                ExpressionAttributeValues={':cid': customer_id},
                Limit=1,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            mc.record('gsi_query', elapsed_ms)
            return resp.get('Items', [])

        # Scan lookups (50 lookups)
        def scan_lookup(customer_id):
            start = time.perf_counter()
            resp = table.scan(
                FilterExpression='stripe_customer_id = :cid',
                ExpressionAttributeValues={':cid': customer_id},
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            mc.record('scan_query', elapsed_ms)
            return resp.get('Items', [])

        gsi_users = users[:50]
        scan_users = users[50:]

        with ThreadPoolExecutor(max_workers=20) as pool:
            gsi_futures = [pool.submit(gsi_lookup, u['stripe_customer_id']) for u in gsi_users]
            scan_futures = [pool.submit(scan_lookup, u['stripe_customer_id']) for u in scan_users]

            gsi_results = [f.result() for f in as_completed(gsi_futures)]
            scan_results = [f.result() for f in as_completed(scan_futures)]

        assert all(len(r) > 0 for r in gsi_results), "Some GSI lookups returned empty"
        assert all(len(r) > 0 for r in scan_results), "Some scan lookups returned empty"

        gsi_pcts = mc.get_percentiles('gsi_query')
        scan_pcts = mc.get_percentiles('scan_query')

        ratio = scan_pcts['p50'] / gsi_pcts['p50'] if gsi_pcts['p50'] and gsi_pcts['p50'] > 0 else 0

        print(f"\n{'='*60}")
        print(f"  GSI vs Scan Comparison")
        print(f"{'='*60}")
        print(f"  GSI  - p50: {gsi_pcts['p50']:.3f}ms  p95: {gsi_pcts['p95']:.3f}ms  p99: {gsi_pcts['p99']:.3f}ms")
        print(f"  Scan - p50: {scan_pcts['p50']:.3f}ms  p95: {scan_pcts['p95']:.3f}ms  p99: {scan_pcts['p99']:.3f}ms")
        print(f"  Performance ratio (scan/gsi p50): {ratio:.2f}x")
        print(f"{'='*60}")

        _BENCHMARK_RESULTS['gsi_vs_scan'] = mc.generate_report()

    # -----------------------------------------------------------------------
    # test_concurrent_user_updates_50
    # -----------------------------------------------------------------------
    @mock_aws
    def test_concurrent_user_updates_50(self):
        """Run 50 concurrent update_item calls on different users, verify persistence."""
        os.environ['ENVIRONMENT'] = 'test'
        os.environ['USERS_TABLE'] = 'buffett-test-users'

        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_users_table(dynamodb)
        users = _seed_users(table, 50, with_stripe=True)

        mc = MetricsCollector()
        now_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

        def update_user(user):
            start = time.perf_counter()
            table.update_item(
                Key={'user_id': user['user_id']},
                UpdateExpression='''
                    SET subscription_status = :status,
                        subscription_tier = :tier,
                        updated_at = :ts
                ''',
                ExpressionAttributeValues={
                    ':status': 'active',
                    ':tier': 'plus',
                    ':ts': now_iso,
                },
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            mc.record('user_update', elapsed_ms)

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(update_user, u) for u in users]
            for f in as_completed(futures):
                f.result()  # raise if any failed

        # Verify all 50 updates persisted
        for user in users:
            resp = table.get_item(Key={'user_id': user['user_id']})
            item = resp['Item']
            assert item['subscription_status'] == 'active', f"User {user['user_id']} not updated"
            assert item['subscription_tier'] == 'plus'
            assert item['updated_at'] == now_iso

        _print_metrics_summary("Concurrent User Updates (50)", mc, 'user_update')
        _BENCHMARK_RESULTS['concurrent_updates_50'] = mc.generate_report()

    # -----------------------------------------------------------------------
    # test_token_usage_write_throughput
    # -----------------------------------------------------------------------
    @mock_aws
    def test_token_usage_write_throughput(self):
        """Run 50 concurrent _initialize_plus_token_usage calls, verify records."""
        os.environ['ENVIRONMENT'] = 'test'
        os.environ['USERS_TABLE'] = 'buffett-test-users'
        os.environ['TOKEN_USAGE_TABLE'] = 'buffett-test-token-usage'
        os.environ['TOKEN_LIMIT_PLUS'] = '2000000'

        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        users_tbl = create_users_table(dynamodb)
        token_tbl = create_token_usage_table(dynamodb)
        users = _seed_users(users_tbl, 50, with_stripe=True, with_billing_day=True)

        # Point handler module at mocked tables
        import handlers.stripe_webhook_handler as handler_mod
        handler_mod.dynamodb = dynamodb
        handler_mod.users_table = dynamodb.Table('buffett-test-users')
        handler_mod.token_usage_table = dynamodb.Table('buffett-test-token-usage')

        mc = MetricsCollector()

        def init_token_usage(user):
            start = time.perf_counter()
            handler_mod._initialize_plus_token_usage(user['user_id'], 15)
            elapsed_ms = (time.perf_counter() - start) * 1000
            mc.record('token_write', elapsed_ms)

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(init_token_usage, u) for u in users]
            for f in as_completed(futures):
                f.result()

        # Verify all 50 records created with correct token_limit
        from utils.token_usage_tracker import TokenUsageTracker
        billing_period, _, _ = TokenUsageTracker.get_current_billing_period(15)

        for user in users:
            resp = token_tbl.get_item(Key={
                'user_id': user['user_id'],
                'billing_period': billing_period,
            })
            item = resp.get('Item')
            assert item is not None, f"Token record missing for {user['user_id']}"
            assert int(item['token_limit']) == 2000000, (
                f"Expected token_limit=2000000, got {item['token_limit']}"
            )

        _print_metrics_summary("Token Usage Write Throughput (50)", mc, 'token_write')
        _BENCHMARK_RESULTS['token_write_50'] = mc.generate_report()

    # -----------------------------------------------------------------------
    # test_conditional_update_contention
    # -----------------------------------------------------------------------
    @mock_aws
    def test_conditional_update_contention(self):
        """20 concurrent conditional updates to the SAME user record."""
        os.environ['ENVIRONMENT'] = 'test'
        os.environ['USERS_TABLE'] = 'buffett-test-users'

        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_users_table(dynamodb)
        users = _seed_users(table, 1, with_stripe=True)
        target_user_id = users[0]['user_id']

        mc = MetricsCollector()
        successes = []
        failures = []

        def conditional_update(idx):
            start = time.perf_counter()
            try:
                table.update_item(
                    Key={'user_id': target_user_id},
                    UpdateExpression='SET updated_at = :ts, last_writer = :w',
                    ExpressionAttributeValues={
                        ':ts': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                        ':w': f'writer-{idx}',
                    },
                    ConditionExpression='attribute_exists(user_id)',
                )
                elapsed_ms = (time.perf_counter() - start) * 1000
                mc.record('conditional_update', elapsed_ms)
                successes.append(idx)
            except ClientError as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                mc.record('conditional_update', elapsed_ms)
                if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                    mc.record_error('conditional_update')
                    failures.append(idx)
                else:
                    raise

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(conditional_update, i) for i in range(20)]
            for f in as_completed(futures):
                f.result()

        total = len(successes) + len(failures)
        contention_rate = len(failures) / total if total > 0 else 0.0

        print(f"\n{'='*60}")
        print(f"  Conditional Update Contention (20 concurrent)")
        print(f"{'='*60}")
        print(f"  Total attempts  : {total}")
        print(f"  Successes       : {len(successes)}")
        print(f"  Failures        : {len(failures)}")
        print(f"  Contention rate : {contention_rate:.1%}")
        pcts = mc.get_percentiles('conditional_update')
        if pcts['p50'] is not None:
            print(f"  p50             : {pcts['p50']:.3f} ms")
            print(f"  p95             : {pcts['p95']:.3f} ms")
            print(f"  p99             : {pcts['p99']:.3f} ms")
        print(f"{'='*60}")

        # At minimum, some should succeed (moto doesn't have real contention)
        assert len(successes) > 0, "No conditional updates succeeded"
        assert total == 20, f"Expected 20 total attempts, got {total}"

        _BENCHMARK_RESULTS['conditional_contention'] = mc.generate_report()

    # -----------------------------------------------------------------------
    # test_batch_read_write_cycle
    # -----------------------------------------------------------------------
    @mock_aws
    def test_batch_read_write_cycle(self):
        """Write 100 items to stripe-events, read all back. Report throughput."""
        os.environ['ENVIRONMENT'] = 'test'
        os.environ['PROCESSED_EVENTS_TABLE'] = 'buffett-test-stripe-events'

        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_stripe_events_table(dynamodb)

        mc = MetricsCollector()
        event_ids = [f"evt_{uuid.uuid4().hex[:24]}" for _ in range(100)]

        # Write phase
        def write_event(event_id):
            start = time.perf_counter()
            table.put_item(Item={
                'event_id': event_id,
                'event_type': 'checkout.session.completed',
                'processed_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                'ttl': int(time.time()) + 7 * 86400,
            })
            elapsed_ms = (time.perf_counter() - start) * 1000
            mc.record('event_write', elapsed_ms)

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(write_event, eid) for eid in event_ids]
            for f in as_completed(futures):
                f.result()

        write_report = mc.generate_report()
        write_samples = mc._samples.get('event_write', [])

        # Read phase – new collector for read timing
        mc_read = MetricsCollector()

        def read_event(event_id):
            start = time.perf_counter()
            resp = table.get_item(Key={'event_id': event_id})
            elapsed_ms = (time.perf_counter() - start) * 1000
            mc_read.record('event_read', elapsed_ms)
            return resp.get('Item')

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(read_event, eid) for eid in event_ids]
            results = [f.result() for f in as_completed(futures)]

        assert all(r is not None for r in results), "Some events not found on read-back"
        assert len(results) == 100

        read_report = mc_read.generate_report()
        total_cycle_time = write_report['elapsed_seconds'] + read_report['elapsed_seconds']

        write_pcts = mc.get_percentiles('event_write')
        read_pcts = mc_read.get_percentiles('event_read')

        print(f"\n{'='*60}")
        print(f"  Batch Read/Write Cycle (100 items)")
        print(f"{'='*60}")
        print(f"  Write ops       : 100")
        print(f"  Write throughput : {write_report['rps']:.1f} ops/sec")
        print(f"  Write p50       : {write_pcts['p50']:.3f} ms")
        print(f"  Write p95       : {write_pcts['p95']:.3f} ms")
        print(f"  Write p99       : {write_pcts['p99']:.3f} ms")
        print(f"  Read ops        : 100")
        print(f"  Read throughput  : {read_report['rps']:.1f} ops/sec")
        print(f"  Read p50        : {read_pcts['p50']:.3f} ms")
        print(f"  Read p95        : {read_pcts['p95']:.3f} ms")
        print(f"  Read p99        : {read_pcts['p99']:.3f} ms")
        print(f"  Total cycle time : {total_cycle_time:.3f}s")
        print(f"{'='*60}")

        _BENCHMARK_RESULTS['batch_rw_cycle'] = {
            'write': write_report,
            'read': read_report,
            'total_cycle_seconds': round(total_cycle_time, 3),
        }

    # -----------------------------------------------------------------------
    # test_dynamodb_summary (must run last)
    # -----------------------------------------------------------------------
    @mock_aws
    def test_dynamodb_summary(self):
        """Print aggregate table of all DynamoDB benchmarks."""
        print(f"\n{'#'*70}")
        print(f"  DYNAMODB THROUGHPUT BENCHMARK SUMMARY")
        print(f"{'#'*70}")

        if not _BENCHMARK_RESULTS:
            print("  (no benchmark results collected — run full suite)")
            print(f"{'#'*70}")
            return

        header = f"  {'Benchmark':<30} {'Ops':>6} {'p50 ms':>9} {'p95 ms':>9} {'p99 ms':>9} {'RPS':>9}"
        print(header)
        print(f"  {'-'*30} {'-'*6} {'-'*9} {'-'*9} {'-'*9} {'-'*9}")

        for name, report in _BENCHMARK_RESULTS.items():
            # Handle batch_rw_cycle which nests write/read
            if isinstance(report, dict) and 'write' in report and 'read' in report:
                for sub_name, sub_report in [('write', report['write']), ('read', report['read'])]:
                    label = f"{name}/{sub_name}"
                    metrics = sub_report.get('metrics', {})
                    for mkey, mdata in metrics.items():
                        p50 = f"{mdata['p50']:.3f}" if mdata.get('p50') is not None else "N/A"
                        p95 = f"{mdata['p95']:.3f}" if mdata.get('p95') is not None else "N/A"
                        p99 = f"{mdata['p99']:.3f}" if mdata.get('p99') is not None else "N/A"
                        print(f"  {label:<30} {mdata['count']:>6} {p50:>9} {p95:>9} {p99:>9} {sub_report['rps']:>9.1f}")
                continue

            metrics = report.get('metrics', {})
            rps = report.get('rps', 0)
            for mkey, mdata in metrics.items():
                p50 = f"{mdata['p50']:.3f}" if mdata.get('p50') is not None else "N/A"
                p95 = f"{mdata['p95']:.3f}" if mdata.get('p95') is not None else "N/A"
                p99 = f"{mdata['p99']:.3f}" if mdata.get('p99') is not None else "N/A"
                print(f"  {name + '/' + mkey:<30} {mdata['count']:>6} {p50:>9} {p95:>9} {p99:>9} {rps:>9.1f}")

        print(f"{'#'*70}")
