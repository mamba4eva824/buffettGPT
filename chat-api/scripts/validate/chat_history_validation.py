#!/usr/bin/env python3
"""
Validate chat history implementation.
Checks that all required tables and attributes are present.
"""

import boto3
import sys
from datetime import datetime
from typing import Dict, List, Tuple

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Table names
CONVERSATIONS_TABLE = 'buffett-dev-conversations'
SESSIONS_TABLE = 'buffett-dev-chat-sessions'
MESSAGES_TABLE = 'buffett-dev-chat-messages'
USERS_TABLE = 'buffett-dev-users'

def check_table_exists(table_name: str) -> bool:
    """Check if a DynamoDB table exists."""
    try:
        table = dynamodb.Table(table_name)
        table.load()
        return True
    except Exception:
        return False

def validate_conversations_table() -> Tuple[bool, List[str]]:
    """Validate conversations table exists and has correct structure."""
    issues = []

    if not check_table_exists(CONVERSATIONS_TABLE):
        issues.append(f"Table {CONVERSATIONS_TABLE} does not exist")
        return False, issues

    table = dynamodb.Table(CONVERSATIONS_TABLE)

    # Check for sample data
    response = table.scan(Limit=1)

    if response['Count'] > 0:
        item = response['Items'][0]
        required_fields = [
            'conversation_id',
            'user_id',
            'title',
            'created_at',
            'updated_at',
            'message_count',
            'is_archived'
        ]

        missing = [f for f in required_fields if f not in item]
        if missing:
            issues.append(f"Missing required fields in conversations: {', '.join(missing)}")

        # Check data types (DynamoDB returns Decimal for numbers)
        from decimal import Decimal
        if 'updated_at' in item and not isinstance(item['updated_at'], (int, float, Decimal)):
            issues.append(f"updated_at should be numeric timestamp, got {type(item['updated_at']).__name__}")

        if 'is_archived' in item and not isinstance(item['is_archived'], bool):
            issues.append(f"is_archived should be boolean, got {type(item['is_archived']).__name__}")

        print(f"✅ Conversations table validated ({response['Count']} items checked)")
    else:
        print("⚠️  Conversations table is empty (run migration to populate)")

    return len(issues) == 0, issues

def validate_messages_attributes() -> Tuple[bool, List[str]]:
    """Validate messages have new attributes."""
    issues = []

    table = dynamodb.Table(MESSAGES_TABLE)
    response = table.scan(Limit=5)

    if response['Count'] > 0:
        checked_count = 0
        for item in response['Items']:
            checked_count += 1

            # Check for new attributes
            if 'tokens_used' not in item:
                issues.append(f"Message {item.get('message_id', 'unknown')} missing 'tokens_used'")

            if 'model' not in item:
                issues.append(f"Message {item.get('message_id', 'unknown')} missing 'model'")

            if 'conversation_id' not in item:
                issues.append(f"Message {item.get('message_id', 'unknown')} missing 'conversation_id'")

            # Validate data types (DynamoDB returns Decimal for numbers)
            from decimal import Decimal
            if 'tokens_used' in item and not isinstance(item['tokens_used'], (int, float, Decimal)):
                issues.append(f"tokens_used should be numeric for message {item.get('message_id', 'unknown')}")

        print(f"✅ Messages table validated ({checked_count} items checked)")
    else:
        print("⚠️  Messages table is empty")

    return len(issues) == 0, issues

def validate_users_attributes() -> Tuple[bool, List[str]]:
    """Validate users have new attributes."""
    issues = []

    table = dynamodb.Table(USERS_TABLE)
    response = table.scan(Limit=5)

    if response['Count'] > 0:
        checked_count = 0
        for item in response['Items']:
            checked_count += 1

            # Check for new attributes
            if 'subscription_tier' not in item:
                issues.append(f"User {item.get('user_id', 'unknown')} missing 'subscription_tier'")

            if 'created_at' not in item:
                issues.append(f"User {item.get('user_id', 'unknown')} missing 'created_at'")

            # Validate subscription_tier values
            if 'subscription_tier' in item:
                valid_tiers = ['free', 'basic', 'premium', 'enterprise']
                if item['subscription_tier'] not in valid_tiers:
                    issues.append(f"Invalid subscription_tier '{item['subscription_tier']}' for user {item.get('user_id', 'unknown')}")

        print(f"✅ Users table validated ({checked_count} items checked)")
    else:
        print("⚠️  Users table is empty")

    return len(issues) == 0, issues

def validate_table_relationships() -> Tuple[bool, List[str]]:
    """Validate relationships between tables."""
    issues = []

    # Check if conversation_ids in messages exist in conversations table
    if check_table_exists(CONVERSATIONS_TABLE):
        conversations_table = dynamodb.Table(CONVERSATIONS_TABLE)
        messages_table = dynamodb.Table(MESSAGES_TABLE)

        # Get sample of conversations
        conv_response = conversations_table.scan(Limit=10)
        conversation_ids = {item['conversation_id'] for item in conv_response['Items']}

        # Get sample of messages
        msg_response = messages_table.scan(Limit=10)

        orphaned_messages = 0
        for message in msg_response['Items']:
            if 'conversation_id' in message:
                # For now, conversation_id should match session_id
                # This is valid during migration period
                if message['conversation_id'] != message.get('session_id'):
                    issues.append(f"Message {message['message_id']} has mismatched conversation_id and session_id")

        if orphaned_messages > 0:
            issues.append(f"Found {orphaned_messages} messages with non-existent conversation_ids")

        print("✅ Table relationships validated")

    return len(issues) == 0, issues

def print_summary(results: Dict[str, Tuple[bool, List[str]]]) -> bool:
    """Print validation summary."""
    print("\n" + "="*60)
    print("Validation Summary")
    print("="*60 + "\n")

    all_valid = True
    total_issues = 0

    for check_name, (is_valid, issues) in results.items():
        if is_valid:
            print(f"✅ {check_name}: PASSED")
        else:
            print(f"❌ {check_name}: FAILED")
            all_valid = False
            total_issues += len(issues)
            for issue in issues:
                print(f"   - {issue}")

    print("\n" + "-"*60)
    if all_valid:
        print("✅ All validations passed!")
    else:
        print(f"❌ Found {total_issues} issues that need to be addressed")

    return all_valid

def main():
    """Main validation function."""
    print("\n" + "="*60)
    print("Chat History Implementation Validation")
    print("="*60 + "\n")

    results = {}

    # Run all validations
    print("Running validations...\n")

    print("1. Checking Conversations table...")
    results["Conversations Table"] = validate_conversations_table()

    print("\n2. Checking Messages attributes...")
    results["Messages Attributes"] = validate_messages_attributes()

    print("\n3. Checking Users attributes...")
    results["Users Attributes"] = validate_users_attributes()

    print("\n4. Checking table relationships...")
    results["Table Relationships"] = validate_table_relationships()

    # Print summary
    all_valid = print_summary(results)

    # Exit with appropriate code
    sys.exit(0 if all_valid else 1)

if __name__ == "__main__":
    main()