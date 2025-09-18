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


def update_conversation_timestamp(conversation_id: str, timestamp: Optional[int] = None) -> bool:
    """
    Update conversation's updated_at timestamp and increment message count.

    Args:
        conversation_id: The conversation ID to update
        timestamp: Unix timestamp (defaults to current time)

    Returns:
        bool: True if update succeeded, False otherwise
    """
    if not conversation_id:
        logger.warning("update_conversation_timestamp called with empty conversation_id")
        return False

    if timestamp is None:
        timestamp = int(datetime.utcnow().timestamp())

    try:
        conversations_table.update_item(
            Key={'conversation_id': conversation_id},
            UpdateExpression='SET updated_at = :timestamp, message_count = if_not_exists(message_count, :zero) + :inc',
            ExpressionAttributeValues={
                ':timestamp': timestamp,
                ':zero': 0,
                ':inc': 1
            }
        )

        logger.info(f"Successfully updated conversation {conversation_id} timestamp to {timestamp}")
        return True

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceNotFoundException':
            logger.warning(f"Conversation {conversation_id} not found - may be anonymous session")
        else:
            logger.error(f"Failed to update conversation {conversation_id}: {str(e)}")
        return False

    except Exception as e:
        logger.error(f"Unexpected error updating conversation {conversation_id}: {str(e)}")
        return False