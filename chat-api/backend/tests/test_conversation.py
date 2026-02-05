#!/usr/bin/env python3
"""
Test script to retrieve conversation from DynamoDB
"""

import os
import sys
import boto3
import json
from datetime import datetime

# Set environment variables
os.environ['AWS_REGION'] = 'us-east-1'
os.environ['ENVIRONMENT'] = 'dev'
os.environ['PROJECT_NAME'] = 'buffett'

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Table names
conversations_table = dynamodb.Table('buffett-dev-conversations')
messages_table = dynamodb.Table('buffett-dev-chat-messages')

def test_get_conversation():
    """Test retrieving conversation and messages"""

    conversation_id = '7e646aab-2929-4842-bf49-895c720b66b0'
    user_id = '109099666789991076125'  # User ID from the message

    print(f"Testing conversation retrieval for ID: {conversation_id}")
    print(f"Expected user_id: {user_id}")
    print("="*60)

    # 1. Get conversation from conversations table
    print("\n1. Fetching conversation from conversations table...")
    try:
        response = conversations_table.get_item(
            Key={'conversation_id': conversation_id}
        )

        conversation = response.get('Item')
        if conversation:
            print(f"  ✓ Conversation found")
            print(f"    - conversation_id: {conversation.get('conversation_id')}")
            print(f"    - user_id: {conversation.get('user_id')} (actual)")
            print(f"    - title: {conversation.get('title')}")
            print(f"    - created_at: {conversation.get('created_at')}")

            # Check if user_id matches
            if conversation.get('user_id') != user_id:
                print(f"  ⚠️  WARNING: user_id mismatch!")
                print(f"     Expected: {user_id}")
                print(f"     Got: {conversation.get('user_id')}")
        else:
            print(f"  ✗ Conversation not found!")
    except Exception as e:
        print(f"  ✗ Error getting conversation: {e}")

    # 2. Get messages for this conversation
    print("\n2. Fetching messages from chat-messages table...")
    try:
        response = messages_table.query(
            KeyConditionExpression='conversation_id = :conversation_id',
            ExpressionAttributeValues={':conversation_id': conversation_id},
            ScanIndexForward=True,  # Oldest first
            Limit=5
        )

        messages = response.get('Items', [])
        print(f"  ✓ Found {len(messages)} messages")

        for i, msg in enumerate(messages, 1):
            print(f"\n  Message {i}:")
            print(f"    - message_id: {msg.get('message_id')}")
            print(f"    - role/type: {msg.get('role', msg.get('message_type'))}")
            print(f"    - user_id: {msg.get('user_id')}")
            print(f"    - content: {msg.get('content', '')[:100]}...")
            print(f"    - timestamp: {msg.get('timestamp_iso', msg.get('timestamp'))}")
            print(f"    - status: {msg.get('status')}")

    except Exception as e:
        print(f"  ✗ Error getting messages: {e}")

    # 3. Test the access control logic
    print("\n3. Testing access control logic...")
    print(f"  Simulating conversations_handler.get_conversation_messages() check:")

    if conversation and conversation.get('user_id') != user_id:
        print(f"  ✗ Access would be DENIED - user_id mismatch")
        print(f"    Handler checks: conversation['user_id'] != user_id")
        print(f"    {conversation.get('user_id')} != {user_id}")
    elif not conversation:
        print(f"  ✗ Access would be DENIED - conversation not found")
    else:
        print(f"  ✓ Access would be GRANTED")

if __name__ == "__main__":
    test_get_conversation()