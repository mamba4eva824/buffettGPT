"""
Conversation Updater Utility
Updates conversation timestamps and metadata when messages are added.
"""

import os
import logging
from datetime import datetime
from typing import Optional
import boto3
from botocore.exceptions import ClientError

# Set up logging
logger = logging.getLogger(__name__)

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
CONVERSATIONS_TABLE = os.environ.get('CONVERSATIONS_TABLE', 'buffett-dev-conversations')
conversations_table = dynamodb.Table(CONVERSATIONS_TABLE)


def update_conversation_timestamp(conversation_id: str, timestamp: Optional[int] = None, user_id: Optional[str] = None) -> bool:
    """
    Update conversation's updated_at timestamp and increment message count.
    Creates the conversation if it doesn't exist.

    Args:
        conversation_id: The conversation ID to update
        timestamp: Unix timestamp as integer (defaults to current time)
        user_id: User ID for creating new conversations

    Returns:
        bool: True if update succeeded, False otherwise
    """
    if not conversation_id:
        logger.warning("update_conversation_timestamp called with empty conversation_id")
        return False

    if timestamp is None:
        timestamp = int(datetime.utcnow().timestamp())

    try:
        # First try to update existing conversation
        update_expression = 'SET updated_at = :timestamp, message_count = if_not_exists(message_count, :zero) + :inc'
        expression_values = {
            ':timestamp': timestamp,
            ':zero': 0,
            ':inc': 1
        }

        # Add user_id and other fields if provided and missing
        if user_id:
            update_expression += ', user_id = if_not_exists(user_id, :user_id)'
            update_expression += ', user_type = if_not_exists(user_type, :user_type)'
            update_expression += ', created_at = if_not_exists(created_at, :created_at)'
            update_expression += ', title = if_not_exists(title, :title)'
            update_expression += ', is_archived = if_not_exists(is_archived, :is_archived)'

            expression_values.update({
                ':user_id': user_id,
                ':user_type': 'authenticated',
                ':created_at': datetime.utcnow().isoformat() + 'Z',
                ':title': 'New Conversation',
                ':is_archived': False
            })
        else:
            # For anonymous users
            update_expression += ', user_type = if_not_exists(user_type, :user_type)'
            update_expression += ', created_at = if_not_exists(created_at, :created_at)'
            update_expression += ', title = if_not_exists(title, :title)'
            update_expression += ', is_archived = if_not_exists(is_archived, :is_archived)'

            expression_values.update({
                ':user_type': 'anonymous',
                ':created_at': datetime.utcnow().isoformat() + 'Z',
                ':title': 'New Conversation',
                ':is_archived': False
            })

        conversations_table.update_item(
            Key={'conversation_id': conversation_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )

        logger.info(f"Successfully updated conversation {conversation_id} timestamp to {timestamp}")
        return True

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceNotFoundException' or error_code == 'ValidationException':
            # Conversation doesn't exist, create it
            logger.info(f"Conversation {conversation_id} not found - creating new conversation record")

            try:
                conversation_item = {
                    'conversation_id': conversation_id,
                    'user_id': user_id,
                    'created_at': datetime.utcnow().isoformat() + 'Z',
                    'updated_at': timestamp,  # Already an int timestamp
                    'message_count': 1,
                    'title': 'New Conversation',
                    'is_archived': False
                }

                # Only add user_id if provided
                if user_id:
                    conversation_item['user_id'] = user_id
                    conversation_item['user_type'] = 'authenticated'
                else:
                    conversation_item['user_type'] = 'anonymous'

                conversations_table.put_item(Item=conversation_item)
                logger.info(f"Successfully created conversation {conversation_id} with user_id {user_id}")
                return True

            except Exception as create_error:
                logger.error(f"Failed to create conversation {conversation_id}: {str(create_error)}")
                return False
        else:
            logger.error(f"Failed to update conversation {conversation_id}: {str(e)}")
        return False

    except Exception as e:
        logger.error(f"Unexpected error updating conversation {conversation_id}: {str(e)}")
        return False