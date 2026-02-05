#!/usr/bin/env python3
"""
Test new conversation creation to verify conversation_updater.py fixes

NOTE: This is an integration test that requires a deployed WebSocket endpoint
and AWS credentials with DynamoDB access.
"""
import asyncio
import websockets
import json
import time
import uuid
import boto3
import pytest
from datetime import datetime

# WebSocket endpoint
WEBSOCKET_URL = "wss://2df7w41edl.execute-api.us-east-1.amazonaws.com/dev"

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
conversations_table = dynamodb.Table('buffett-dev-conversations')


@pytest.mark.asyncio
@pytest.mark.integration
async def test_new_conversation_creation():
    """Test creating a new conversation and verify it gets proper metadata"""
    print("🧪 Testing new conversation creation...")

    # Generate a unique conversation ID for testing
    test_conversation_id = f"test-conv-{int(time.time())}-{uuid.uuid4().hex[:8]}"

    print(f"  Test conversation ID: {test_conversation_id}")

    try:
        # Connect to WebSocket with the test conversation ID
        connection_url = f"{WEBSOCKET_URL}?session_id={test_conversation_id}&conversation_id={test_conversation_id}"

        async with websockets.connect(connection_url) as websocket:
            print("  ✅ WebSocket connection established")

            # Send a test message to trigger conversation creation
            test_message = {
                "action": "message",
                "message": "This is a test message to create a new conversation with proper metadata.",
                "timestamp": datetime.utcnow().isoformat()
            }

            print(f"  📤 Sending test message...")
            await websocket.send(json.dumps(test_message))

            # Wait for acknowledgment
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                response_data = json.loads(response)
                print(f"  📥 Received acknowledgment: {response_data.get('action')}")

                if response_data.get('action') == 'message_received':
                    print("  ✅ Message acknowledged - conversation should be created")
                else:
                    print(f"  ⚠️  Unexpected response: {response_data}")
                    return False

            except asyncio.TimeoutError:
                print("  ❌ No acknowledgment received")
                return False

    except Exception as e:
        print(f"  ❌ WebSocket error: {e}")
        return False

    # Wait a moment for processing
    print("  ⏳ Waiting for conversation to be processed...")
    await asyncio.sleep(3)

    # Check if conversation was created correctly
    print("  🔍 Checking conversation record in DynamoDB...")
    try:
        response = conversations_table.get_item(
            Key={'conversation_id': test_conversation_id}
        )

        conversation = response.get('Item')
        if not conversation:
            print("  ❌ Conversation record not found!")
            return False

        print("  ✅ Conversation record found!")
        print(f"    conversation_id: {conversation.get('conversation_id')}")
        print(f"    user_id: {conversation.get('user_id')}")
        print(f"    user_type: {conversation.get('user_type')}")
        print(f"    title: {conversation.get('title')}")
        print(f"    created_at: {conversation.get('created_at')}")
        print(f"    updated_at: {conversation.get('updated_at')}")
        print(f"    message_count: {conversation.get('message_count')}")
        print(f"    is_archived: {conversation.get('is_archived')}")

        # Verify all required fields are present
        required_fields = ['conversation_id', 'user_id', 'user_type', 'title', 'created_at', 'updated_at', 'message_count', 'is_archived']
        missing_fields = [field for field in required_fields if field not in conversation]

        if missing_fields:
            print(f"  ❌ Missing fields: {missing_fields}")
            return False

        # Verify user_id is not None or empty
        if not conversation.get('user_id'):
            print(f"  ❌ user_id is empty or None: {conversation.get('user_id')}")
            return False

        print("  ✅ All required fields present with valid values!")
        return True

    except Exception as e:
        print(f"  ❌ Error checking conversation: {e}")
        return False

async def main():
    """Run the test"""
    print("=" * 70)
    print("🧪 New Conversation Creation Test")
    print("=" * 70)

    success = await test_new_conversation_creation()

    print("\n" + "=" * 70)
    print("📊 Test Results")
    print("=" * 70)

    if success:
        print("🎉 ✅ PASS: New conversation created with all required metadata!")
        print("   The conversation_updater.py fix is working correctly.")
    else:
        print("❌ FAIL: New conversation creation test failed.")
        print("   Check the logs above for details.")

    return success

if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)