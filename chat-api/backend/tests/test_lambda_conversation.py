#!/usr/bin/env python3
"""
Test script to simulate Lambda function conversation retrieval
Testing how handlers would retrieve conversation with null user_id
"""

import os
import sys
import boto3
import json
from datetime import datetime

# Set environment variables as Lambda would have them
os.environ['AWS_REGION'] = 'us-east-1'
os.environ['ENVIRONMENT'] = 'dev'
os.environ['PROJECT_NAME'] = 'buffett'
os.environ['CONVERSATIONS_TABLE'] = 'buffett-dev-conversations'
os.environ['CHAT_MESSAGES_TABLE'] = 'buffett-dev-chat-messages'

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Table names from environment
conversations_table = dynamodb.Table(os.environ['CONVERSATIONS_TABLE'])
messages_table = dynamodb.Table(os.environ['CHAT_MESSAGES_TABLE'])

def simulate_conversations_handler_get_messages():
    """
    Simulate what conversations_handler.get_conversation_messages() does
    """

    print("="*70)
    print("SIMULATING conversations_handler.get_conversation_messages()")
    print("="*70)

    conversation_id = '7e646aab-2929-4842-bf49-895c720b66b0'
    user_id = '109099666789991076125'  # The authenticated user

    print(f"\nInput parameters:")
    print(f"  conversation_id: {conversation_id}")
    print(f"  user_id (from auth): {user_id}")

    # Step 1: Verify user owns the conversation (Line 330-336 in conversations_handler.py)
    print("\nStep 1: Verify user owns conversation...")
    try:
        conv_response = conversations_table.get_item(
            Key={'conversation_id': conversation_id}
        )

        conversation = conv_response.get('Item')
        if not conversation:
            print("  ✗ FAIL: Conversation not found")
            print("  Lambda would return: 403 Access denied")
            return False

        print(f"  ✓ Conversation found")
        print(f"    conversation['user_id'] = {conversation.get('user_id')}")
        print(f"    auth user_id = {user_id}")

        # This is the critical check that's failing!
        if conversation.get('user_id') != user_id:
            print(f"\n  ✗ FAIL: User ID mismatch!")
            print(f"    Lambda check: conversation['user_id'] != user_id")
            print(f"    {conversation.get('user_id')} != {user_id}")
            print(f"  Lambda would return: 403 Access denied")
            return False

        print("  ✓ PASS: User owns conversation")

    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False

    # Step 2: Get messages (Line 339-355 in conversations_handler.py)
    print("\nStep 2: Get messages for conversation...")
    try:
        response = messages_table.query(
            KeyConditionExpression='conversation_id = :conversation_id',
            ExpressionAttributeValues={':conversation_id': conversation_id},
            ScanIndexForward=True  # Oldest first
        )

        messages = response.get('Items', [])
        print(f"  ✓ Found {len(messages)} messages")
        print("  Lambda would return: 200 OK with messages")
        return True

    except Exception as e:
        print(f"  ✗ ERROR getting messages: {e}")
        return False


def simulate_alternative_approach():
    """
    Alternative approach: Check if user_id exists in messages
    """

    print("\n" + "="*70)
    print("ALTERNATIVE APPROACH: Verify via messages table")
    print("="*70)

    conversation_id = '7e646aab-2929-4842-bf49-895c720b66b0'
    user_id = '109099666789991076125'

    print(f"\nInput parameters:")
    print(f"  conversation_id: {conversation_id}")
    print(f"  user_id (from auth): {user_id}")

    # Get first message to check user_id
    print("\nChecking user_id from messages...")
    try:
        response = messages_table.query(
            KeyConditionExpression='conversation_id = :conversation_id',
            ExpressionAttributeValues={':conversation_id': conversation_id},
            Limit=1,
            ScanIndexForward=True
        )

        messages = response.get('Items', [])
        if messages:
            msg_user_id = messages[0].get('user_id')
            print(f"  First message user_id: {msg_user_id}")

            if msg_user_id == user_id:
                print(f"  ✓ User ID matches! User owns this conversation")
                print(f"  Could use this as alternative authorization check")
                return True
            else:
                print(f"  ✗ User ID doesn't match")
                return False
        else:
            print("  No messages found")
            return False

    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False


def propose_fix():
    """
    Propose a fix for the issue
    """

    print("\n" + "="*70)
    print("PROPOSED FIX OPTIONS")
    print("="*70)

    print("""
Option 1: Update conversations_handler.py to handle null user_id
    - Modify the access check to also verify against messages table
    - If conversation.user_id is None, check messages table for user_id

Option 2: Fix the conversation record
    - Update the existing conversation to have the correct user_id
    - Ensure new conversations are created with user_id properly set

Option 3: Use message-based authorization
    - Skip conversation table check
    - Authorize based on user_id in messages table

Current failing code (conversations_handler.py:335-336):
    if not conversation or conversation['user_id'] != user_id:
        return create_response(403, {'error': 'Access denied'})

Proposed fix:
    if not conversation:
        return create_response(403, {'error': 'Access denied'})

    # If conversation has no user_id, check messages for ownership
    if conversation.get('user_id') is None:
        # Verify via first message
        msg_response = messages_table.query(
            KeyConditionExpression='conversation_id = :cid',
            ExpressionAttributeValues={':cid': conversation_id},
            Limit=1
        )
        if msg_response.get('Items'):
            msg_user_id = msg_response['Items'][0].get('user_id')
            if msg_user_id != user_id:
                return create_response(403, {'error': 'Access denied'})
        # If no messages, allow access (new conversation)
    elif conversation['user_id'] != user_id:
        return create_response(403, {'error': 'Access denied'})
""")


if __name__ == "__main__":
    # Test current Lambda logic
    result1 = simulate_conversations_handler_get_messages()

    # Test alternative approach
    result2 = simulate_alternative_approach()

    # Propose fix
    propose_fix()

    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"Current Lambda logic would: {'✓ SUCCEED' if result1 else '✗ FAIL'}")
    print(f"Alternative approach would: {'✓ SUCCEED' if result2 else '✗ FAIL'}")
    print("\nThe Lambda functions cannot currently retrieve this conversation")
    print("because the conversation record has user_id=None while messages have")
    print("the correct user_id. The access control check fails.")