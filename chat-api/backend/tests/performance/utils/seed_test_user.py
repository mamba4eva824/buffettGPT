"""
Seed and cleanup test users in DynamoDB for AWS dev load testing.
All test users are prefixed with 'perf-test-' for easy identification and cleanup.
"""

import boto3
import uuid
import time

TEST_USER_PREFIX = 'perf-test-'
DEFAULT_TABLE = 'buffett-dev-users'
DEFAULT_REGION = 'us-east-1'


def seed_test_users(
    table_name: str = DEFAULT_TABLE,
    region: str = DEFAULT_REGION,
    count: int = 5
) -> list[dict]:
    """
    Create test users in the DynamoDB users table.

    Returns a list of user dicts with user_id, email, and stripe_customer_id.
    Each user is created with:
      - user_id: perf-test-<uuid>
      - email: perf-test-<uuid>@buffettgpt.test
      - subscription_tier: 'free'
      - stripe_customer_id: cus_perftest_<uuid>
    """
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)

    users = []
    for i in range(count):
        uid = f"{TEST_USER_PREFIX}{uuid.uuid4().hex[:12]}"
        user = {
            'user_id': uid,
            'email': f"{uid}@buffettgpt.test",
            'name': f"Perf Test User {i+1}",
            'subscription_tier': 'free',
            'stripe_customer_id': f"cus_perftest_{uuid.uuid4().hex[:12]}",
            'created_at': int(time.time()),
            'updated_at': int(time.time()),
        }
        table.put_item(Item=user)
        users.append(user)
        print(f"  Seeded user: {uid}")

    return users


def cleanup_test_users(
    table_name: str = DEFAULT_TABLE,
    region: str = DEFAULT_REGION,
    user_ids: list[str] | None = None
) -> int:
    """
    Remove test users from DynamoDB.

    If user_ids is None, scans for all users with the perf-test- prefix.
    Returns the number of users deleted.
    """
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)

    if user_ids is None:
        # Scan for all perf-test- users
        response = table.scan(
            FilterExpression='begins_with(user_id, :prefix)',
            ExpressionAttributeValues={':prefix': TEST_USER_PREFIX},
            ProjectionExpression='user_id'
        )
        user_ids = [item['user_id'] for item in response.get('Items', [])]

    deleted = 0
    for uid in user_ids:
        table.delete_item(Key={'user_id': uid})
        deleted += 1
        print(f"  Cleaned up user: {uid}")

    return deleted


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Seed or cleanup test users')
    parser.add_argument('action', choices=['seed', 'cleanup'], help='Action to perform')
    parser.add_argument('--count', type=int, default=5, help='Number of users to seed')
    parser.add_argument('--table', default=DEFAULT_TABLE, help='DynamoDB table name')
    parser.add_argument('--region', default=DEFAULT_REGION, help='AWS region')
    args = parser.parse_args()

    if args.action == 'seed':
        print(f"Seeding {args.count} test users in {args.table}...")
        users = seed_test_users(args.table, args.region, args.count)
        print(f"Done. {len(users)} users created.")
    else:
        print(f"Cleaning up test users in {args.table}...")
        count = cleanup_test_users(args.table, args.region)
        print(f"Done. {count} users deleted.")
