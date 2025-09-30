#!/usr/bin/env python3
"""
Repair Script: Fix Incomplete Conversation Records

This script identifies conversation records missing user_id and other metadata,
then repairs them by looking up the user_id from the messages table.
"""

import os
import boto3
import json
from datetime import datetime
from botocore.exceptions import ClientError

# Set environment variables
os.environ['AWS_REGION'] = 'us-east-1'
os.environ['ENVIRONMENT'] = 'dev'
os.environ['PROJECT_NAME'] = 'buffett'

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Table names
CONVERSATIONS_TABLE = 'buffett-dev-conversations'
MESSAGES_TABLE = 'buffett-dev-chat-messages'

conversations_table = dynamodb.Table(CONVERSATIONS_TABLE)
messages_table = dynamodb.Table(MESSAGES_TABLE)

def scan_incomplete_conversations():
    """
    Scan all conversation records and identify incomplete ones
    (missing user_id, created_at, title, etc.)
    """
    print("🔍 Scanning for incomplete conversation records...")

    incomplete_conversations = []

    try:
        # Scan all conversations
        response = conversations_table.scan()
        conversations = response.get('Items', [])

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = conversations_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            conversations.extend(response.get('Items', []))

        print(f"  Found {len(conversations)} total conversation records")

        # Check each conversation for missing fields
        for conv in conversations:
            missing_fields = []

            if 'user_id' not in conv:
                missing_fields.append('user_id')
            if 'created_at' not in conv:
                missing_fields.append('created_at')
            if 'title' not in conv:
                missing_fields.append('title')
            if 'is_archived' not in conv:
                missing_fields.append('is_archived')
            if 'user_type' not in conv:
                missing_fields.append('user_type')

            if missing_fields:
                incomplete_conversations.append({
                    'conversation_id': conv['conversation_id'],
                    'missing_fields': missing_fields,
                    'current_data': conv
                })

        print(f"  Found {len(incomplete_conversations)} incomplete conversation records")

        return incomplete_conversations

    except Exception as e:
        print(f"  ❌ Error scanning conversations: {e}")
        return []

def get_user_id_from_messages(conversation_id):
    """
    Get user_id by querying the first message in a conversation
    """
    try:
        response = messages_table.query(
            KeyConditionExpression='conversation_id = :cid',
            ExpressionAttributeValues={':cid': conversation_id},
            Limit=1,
            ScanIndexForward=True  # Get oldest message first
        )

        messages = response.get('Items', [])
        if messages:
            return messages[0].get('user_id')

        return None

    except Exception as e:
        print(f"    ❌ Error querying messages for {conversation_id}: {e}")
        return None

def repair_conversation(conversation_id, missing_fields, current_data):
    """
    Repair a single conversation record by adding missing fields
    """
    print(f"  Repairing conversation: {conversation_id}")
    print(f"    Missing fields: {missing_fields}")

    # Get user_id from messages if missing
    user_id = current_data.get('user_id')
    if not user_id:
        user_id = get_user_id_from_messages(conversation_id)
        if user_id:
            print(f"    Found user_id from messages: {user_id}")
        else:
            print(f"    ⚠️  No user_id found in messages, treating as anonymous")

    # Prepare update expression
    update_expression = "SET"
    expression_values = {}
    updates = []

    # Add missing fields
    if 'user_id' in missing_fields and user_id:
        updates.append("user_id = :user_id")
        expression_values[':user_id'] = user_id

    if 'user_type' in missing_fields:
        user_type = 'authenticated' if user_id else 'anonymous'
        updates.append("user_type = :user_type")
        expression_values[':user_type'] = user_type

    if 'created_at' in missing_fields:
        # Use updated_at if available, otherwise current time
        created_at = current_data.get('updated_at')
        if created_at:
            # Convert timestamp to ISO format
            if isinstance(created_at, (int, float)):
                created_at = datetime.fromtimestamp(created_at).isoformat()
            elif isinstance(created_at, str) and created_at.isdigit():
                created_at = datetime.fromtimestamp(int(created_at)).isoformat()
        else:
            created_at = datetime.utcnow().isoformat()

        updates.append("created_at = :created_at")
        expression_values[':created_at'] = created_at

    if 'title' in missing_fields:
        updates.append("title = :title")
        expression_values[':title'] = 'New Conversation'

    if 'is_archived' in missing_fields:
        updates.append("is_archived = :is_archived")
        expression_values[':is_archived'] = False

    if not updates:
        print(f"    ⚠️  No updates needed")
        return True

    update_expression += " " + ", ".join(updates)

    try:
        conversations_table.update_item(
            Key={'conversation_id': conversation_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )

        print(f"    ✅ Successfully repaired conversation {conversation_id}")
        return True

    except Exception as e:
        print(f"    ❌ Failed to repair conversation {conversation_id}: {e}")
        return False

def main():
    """
    Main repair process
    """
    print("=" * 70)
    print("🔧 Conversation Records Repair Script")
    print("=" * 70)

    # Step 1: Find incomplete conversations
    incomplete_conversations = scan_incomplete_conversations()

    if not incomplete_conversations:
        print("\n✅ All conversation records are complete!")
        return

    # Step 2: Show what we found
    print(f"\n📋 Incomplete Conversations Summary:")
    for conv in incomplete_conversations:
        print(f"  - {conv['conversation_id']}: missing {conv['missing_fields']}")

    # Step 3: Auto-proceed with repairs
    print(f"\nReady to repair {len(incomplete_conversations)} conversation records.")
    print("Proceeding with repairs automatically...")

    # Step 4: Repair each conversation
    print(f"\n🔧 Starting repairs...")
    successful_repairs = 0
    failed_repairs = 0

    for conv in incomplete_conversations:
        success = repair_conversation(
            conv['conversation_id'],
            conv['missing_fields'],
            conv['current_data']
        )

        if success:
            successful_repairs += 1
        else:
            failed_repairs += 1

    # Step 5: Summary
    print(f"\n" + "=" * 70)
    print("📊 Repair Summary")
    print("=" * 70)
    print(f"Total conversations processed: {len(incomplete_conversations)}")
    print(f"Successful repairs: {successful_repairs}")
    print(f"Failed repairs: {failed_repairs}")

    if failed_repairs == 0:
        print("\n🎉 All conversation records have been successfully repaired!")
    else:
        print(f"\n⚠️  {failed_repairs} repairs failed. Check the errors above.")

if __name__ == "__main__":
    main()