"""
Integration tests for message persistence in DynamoDB.

These tests run against the REAL DynamoDB table in dev environment.
Run with: pytest tests/integration/test_message_persistence.py -v -s

NOTE: These tests require AWS credentials and access to DynamoDB.
"""

import boto3
import json
import os
import sys
import uuid
import time
import pytest
from datetime import datetime
from decimal import Decimal
from botocore.exceptions import ClientError

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Configuration
REGION = 'us-east-1'
TABLE_NAME = 'buffett-dev-chat-messages'

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb', region_name=REGION)
table = dynamodb.Table(TABLE_NAME)


def _check_table_exists():
    """Check if the DynamoDB table exists and is accessible."""
    try:
        table.table_status
        return True
    except ClientError:
        return False


@pytest.mark.integration
@pytest.mark.skipif(not _check_table_exists(), reason="DynamoDB table not accessible")
def test_save_and_retrieve_followup_message():
    """
    Integration test: Save a message via save_followup_message and verify it exists in DynamoDB.
    """
    # Generate unique test identifiers
    test_session_id = f"integration-test-{uuid.uuid4()}"
    test_user_id = f"test-user-{uuid.uuid4()}"
    test_content = f"Integration test message at {datetime.utcnow().isoformat()}"

    print(f"\n{'='*60}")
    print(f"Integration Test: Message Persistence")
    print(f"{'='*60}")
    print(f"Session ID: {test_session_id}")
    print(f"User ID: {test_user_id}")

    # Set required environment variables for the handler
    os.environ['CHAT_MESSAGES_TABLE'] = TABLE_NAME
    os.environ['ENVIRONMENT'] = 'integration-test'
    os.environ['PROJECT_NAME'] = 'buffett-chat-api'
    os.environ['BEDROCK_REGION'] = REGION

    # Import after setting env vars
    from handlers.analysis_followup import save_followup_message, messages_table

    # Reinitialize the table reference if needed
    if messages_table is None:
        import handlers.analysis_followup as handler_module
        handler_module.messages_table = table

    # Test 1: Save a user message
    print(f"\n[1] Saving user message...")
    user_message_id = save_followup_message(
        session_id=test_session_id,
        message_type='user',
        content=test_content,
        user_id=test_user_id,
        agent_type='debt',
        ticker='TEST'
    )

    assert user_message_id is not None, "Failed to save user message"
    print(f"    ✓ User message saved with ID: {user_message_id}")

    # Test 2: Save an assistant message
    print(f"\n[2] Saving assistant message...")
    assistant_content = f"This is the assistant response to: {test_content}"
    assistant_message_id = save_followup_message(
        session_id=test_session_id,
        message_type='assistant',
        content=assistant_content,
        user_id=test_user_id,
        agent_type='debt',
        ticker='TEST'
    )

    assert assistant_message_id is not None, "Failed to save assistant message"
    print(f"    ✓ Assistant message saved with ID: {assistant_message_id}")

    # Test 3: Query DynamoDB to verify messages exist
    print(f"\n[3] Querying DynamoDB for saved messages...")
    time.sleep(1)  # Brief wait for eventual consistency

    response = table.query(
        KeyConditionExpression='conversation_id = :sid',
        ExpressionAttributeValues={':sid': test_session_id}
    )

    messages = response.get('Items', [])
    print(f"    Found {len(messages)} messages for session")

    assert len(messages) == 2, f"Expected 2 messages, found {len(messages)}"

    # Verify message types
    user_msgs = [m for m in messages if m['message_type'] == 'user']
    assistant_msgs = [m for m in messages if m['message_type'] == 'assistant']

    assert len(user_msgs) == 1, "Expected 1 user message"
    assert len(assistant_msgs) == 1, "Expected 1 assistant message"
    print(f"    ✓ Found 1 user message and 1 assistant message")

    # Test 4: Verify message content and metadata
    print(f"\n[4] Verifying message content and metadata...")

    user_msg = user_msgs[0]
    assert user_msg['content'] == test_content
    assert user_msg['user_id'] == test_user_id
    assert user_msg['status'] == 'received'
    assert user_msg['metadata']['agent_type'] == 'debt'
    assert user_msg['metadata']['ticker'] == 'TEST'
    assert user_msg['metadata']['source'] == 'investment_research_followup'
    print(f"    ✓ User message metadata verified")

    assistant_msg = assistant_msgs[0]
    assert assistant_msg['content'] == assistant_content
    assert assistant_msg['status'] == 'completed'
    assert assistant_msg['metadata']['agent_type'] == 'debt'
    print(f"    ✓ Assistant message metadata verified")

    # Test 5: Verify timestamps
    print(f"\n[5] Verifying timestamps...")
    for msg in messages:
        assert 'timestamp' in msg, "Missing timestamp"
        assert 'created_at' in msg, "Missing created_at"
        # Timestamp is stored in milliseconds, convert to seconds for comparison
        now_unix = int(datetime.utcnow().timestamp())
        msg_timestamp_secs = int(msg['timestamp']) // 1000  # Convert ms to seconds
        assert abs(msg_timestamp_secs - now_unix) < 3600, "Timestamp not recent"
    print(f"    ✓ Timestamps are valid and recent")

    # Cleanup: Delete test messages
    print(f"\n[6] Cleaning up test messages...")
    for msg in messages:
        table.delete_item(
            Key={
                'conversation_id': msg['conversation_id'],
                'timestamp': msg['timestamp']
            }
        )
    print(f"    ✓ Deleted {len(messages)} test messages")

    print(f"\n{'='*60}")
    print(f"✅ All integration tests passed!")
    print(f"{'='*60}\n")


def test_query_existing_messages():
    """
    Query existing messages in the table to see the current schema.
    This is a read-only diagnostic test.
    """
    print(f"\n{'='*60}")
    print(f"Diagnostic: Scanning recent messages in {TABLE_NAME}")
    print(f"{'='*60}")

    # Scan for a few recent messages
    response = table.scan(Limit=5)
    messages = response.get('Items', [])

    print(f"\nFound {len(messages)} messages (limited to 5)")

    if messages:
        print(f"\nSample message schema:")
        sample = messages[0]
        for key, value in sample.items():
            value_type = type(value).__name__
            value_preview = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
            print(f"  - {key}: ({value_type}) {value_preview}")
    else:
        print("No messages found in table")

    print(f"\n{'='*60}\n")


if __name__ == '__main__':
    # Run tests directly
    test_query_existing_messages()
    test_save_and_retrieve_followup_message()
