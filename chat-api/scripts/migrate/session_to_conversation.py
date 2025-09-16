#!/usr/bin/env python3
"""
Migrate session_id to conversation_id in DynamoDB tables.
This script adds conversation_id while preserving session_id for backward compatibility.
"""

import boto3
import json
from datetime import datetime
from typing import Dict, Any
import logging
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Table names - using dev environment
SESSIONS_TABLE = 'buffett-dev-chat-sessions'
MESSAGES_TABLE = 'buffett-dev-chat-messages'
USERS_TABLE = 'buffett-dev-users'
CONVERSATIONS_TABLE = 'buffett-dev-conversations'

def migrate_conversations_table():
    """Create conversations from existing sessions."""
    logger.info("Starting conversations migration...")

    sessions_table = dynamodb.Table(SESSIONS_TABLE)
    conversations_table = dynamodb.Table(CONVERSATIONS_TABLE)

    # Scan all sessions
    logger.info(f"Scanning {SESSIONS_TABLE} table...")
    response = sessions_table.scan()
    sessions = response['Items']

    # Handle pagination if there are many items
    while 'LastEvaluatedKey' in response:
        response = sessions_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        sessions.extend(response['Items'])

    logger.info(f"Found {len(sessions)} session entries to process")

    # Group sessions by session_id (since there can be multiple entries per session due to composite key)
    session_groups = {}
    for session in sessions:
        session_id = session['session_id']
        if session_id not in session_groups:
            session_groups[session_id] = []
        session_groups[session_id].append(session)

    logger.info(f"Found {len(session_groups)} unique sessions")

    # Create conversation for each unique session
    created_count = 0
    error_count = 0

    for session_id, session_entries in session_groups.items():
        # Use the most recent session entry
        latest_session = max(session_entries, key=lambda x: x.get('timestamp', 0))

        # Generate a meaningful title based on the creation time
        created_at = latest_session.get('created_at', latest_session.get('timestamp_iso', ''))
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                title = f"Chat from {dt.strftime('%B %d, %Y at %I:%M %p')}"
            except:
                title = f"Chat session {session_id[:8]}"
        else:
            title = f"Chat session {session_id[:8]}"

        conversation = {
            'conversation_id': session_id,  # Use session_id as conversation_id initially
            'user_id': latest_session['user_id'],
            'title': title,
            'created_at': latest_session.get('created_at', datetime.utcnow().isoformat()),
            'updated_at': int(datetime.utcnow().timestamp()),
            'message_count': latest_session.get('message_count', 0),
            'is_archived': False,
            'user_type': latest_session.get('user_type', 'unknown'),
            'legacy_session_id': session_id  # Keep reference to original
        }

        try:
            conversations_table.put_item(Item=conversation)
            created_count += 1
            logger.debug(f"Created conversation for session {session_id}")
        except Exception as e:
            error_count += 1
            logger.error(f"Failed to create conversation for session {session_id}: {e}")

    logger.info(f"Conversation migration completed: {created_count} created, {error_count} errors")
    return created_count, error_count

def update_messages_table():
    """Add conversation_id and new attributes to existing messages."""
    logger.info("Starting messages table update...")

    messages_table = dynamodb.Table(MESSAGES_TABLE)

    # Scan all messages
    logger.info(f"Scanning {MESSAGES_TABLE} table...")
    response = messages_table.scan()
    messages = response['Items']

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = messages_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        messages.extend(response['Items'])

    logger.info(f"Found {len(messages)} messages to update")

    updated_count = 0
    error_count = 0

    # Use batch writer for efficiency
    with messages_table.batch_writer() as batch:
        for message in messages:
            try:
                # Add conversation_id (initially same as session_id)
                if 'conversation_id' not in message:
                    message['conversation_id'] = message['session_id']

                # Add placeholder values for new attributes if missing
                if 'tokens_used' not in message:
                    message['tokens_used'] = 0

                if 'model' not in message:
                    # Determine model based on message type
                    if message.get('message_type') == 'assistant':
                        message['model'] = 'bedrock-claude'
                    else:
                        message['model'] = 'user-input'

                batch.put_item(Item=message)
                updated_count += 1

                if updated_count % 100 == 0:
                    logger.info(f"Updated {updated_count} messages...")

            except Exception as e:
                error_count += 1
                logger.error(f"Failed to update message {message.get('message_id', 'unknown')}: {e}")

    logger.info(f"Messages update completed: {updated_count} updated, {error_count} errors")
    return updated_count, error_count

def update_users_table():
    """Add missing attributes to users."""
    logger.info("Starting users table update...")

    users_table = dynamodb.Table(USERS_TABLE)

    # Scan all users
    logger.info(f"Scanning {USERS_TABLE} table...")
    response = users_table.scan()
    users = response['Items']

    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = users_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        users.extend(response['Items'])

    logger.info(f"Found {len(users)} users to check")

    updated_count = 0
    skipped_count = 0
    error_count = 0

    for user in users:
        update_needed = False
        update_expr = []
        expr_attr_values = {}

        # Check and add subscription_tier if missing
        if 'subscription_tier' not in user:
            update_expr.append('subscription_tier = :tier')
            expr_attr_values[':tier'] = 'free'
            update_needed = True

        # Check and add created_at if missing
        if 'created_at' not in user:
            update_expr.append('created_at = :created')
            # Use updated_at as fallback, or current time
            created_at = user.get('updated_at', datetime.utcnow().isoformat())
            expr_attr_values[':created'] = created_at
            update_needed = True

        if update_needed:
            try:
                users_table.update_item(
                    Key={'user_id': user['user_id']},
                    UpdateExpression='SET ' + ', '.join(update_expr),
                    ExpressionAttributeValues=expr_attr_values
                )
                updated_count += 1
                logger.debug(f"Updated user {user['user_id']}")
            except Exception as e:
                error_count += 1
                logger.error(f"Failed to update user {user['user_id']}: {e}")
        else:
            skipped_count += 1
            logger.debug(f"User {user['user_id']} already has all required attributes")

    logger.info(f"Users update completed: {updated_count} updated, {skipped_count} skipped, {error_count} errors")
    return updated_count, error_count

def verify_conversations_table_exists():
    """Check if the conversations table exists."""
    try:
        table = dynamodb.Table(CONVERSATIONS_TABLE)
        table.load()
        logger.info(f"✅ Conversations table '{CONVERSATIONS_TABLE}' exists")
        return True
    except Exception as e:
        logger.error(f"❌ Conversations table '{CONVERSATIONS_TABLE}' does not exist: {e}")
        logger.error("Please run 'terraform apply' first to create the table")
        return False

def main():
    """Main migration function."""
    print("\n" + "="*60)
    print("DynamoDB Chat History Migration Script")
    print("="*60 + "\n")

    # Check if conversations table exists
    if not verify_conversations_table_exists():
        print("\n❌ Migration aborted: Conversations table must be created first")
        print("Run 'terraform apply' in terraform/environments/dev directory")
        sys.exit(1)

    print("\nThis script will:")
    print("1. Create conversation records from existing sessions")
    print("2. Add conversation_id to all messages")
    print("3. Add tokens_used and model attributes to messages")
    print("4. Add subscription_tier and created_at to users")
    print("\n⚠️  This is a non-destructive operation - no data will be deleted")

    # Confirm before proceeding
    response = input("\nDo you want to proceed? (yes/no): ")
    if response.lower() != 'yes':
        print("Migration cancelled")
        sys.exit(0)

    print("\nStarting migration...\n")

    total_created = 0
    total_updated = 0
    total_errors = 0

    # Step 1: Create conversations from sessions
    print("Step 1: Creating conversations from sessions...")
    created, errors = migrate_conversations_table()
    total_created += created
    total_errors += errors

    # Step 2: Update messages with new attributes
    print("\nStep 2: Updating messages with new attributes...")
    updated, errors = update_messages_table()
    total_updated += updated
    total_errors += errors

    # Step 3: Update users with missing attributes
    print("\nStep 3: Updating users with missing attributes...")
    updated, errors = update_users_table()
    total_updated += updated
    total_errors += errors

    # Print summary
    print("\n" + "="*60)
    print("Migration Summary")
    print("="*60)
    print(f"✅ Conversations created: {total_created}")
    print(f"✅ Records updated: {total_updated}")
    if total_errors > 0:
        print(f"❌ Errors encountered: {total_errors}")
        print("Check the logs above for error details")
    else:
        print("✅ No errors encountered")

    print("\n✅ Migration completed successfully!")

    if total_errors > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()