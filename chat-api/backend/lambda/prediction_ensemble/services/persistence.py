"""
DynamoDB persistence service for chat messages.

EXTRACTED FROM: handler.py lines 1280-1325
- save_message(): lines 1280-1325
- messages_table: line 122

Handles saving user and assistant messages to DynamoDB.
"""
import uuid
import logging
import boto3
from decimal import Decimal
from datetime import datetime
from typing import Optional

from config.settings import CHAT_MESSAGES_TABLE, ENVIRONMENT, PROJECT_NAME

logger = logging.getLogger(__name__)

# DynamoDB resources
dynamodb = boto3.resource('dynamodb')
messages_table = dynamodb.Table(CHAT_MESSAGES_TABLE)


def save_message(conversation_id: str, user_id: str, message_type: str,
                 content: str, parent_message_id: str = None,
                 processing_time_ms: float = None) -> str:
    """
    Save a message to the chat_messages DynamoDB table.

    Args:
        conversation_id: Conversation ID
        user_id: User ID
        message_type: 'user' or 'assistant'
        content: Message content
        parent_message_id: Parent message ID (for assistant responses)
        processing_time_ms: Processing time in milliseconds

    Returns:
        Message ID
    """
    message_id = str(uuid.uuid4())
    current_time = datetime.utcnow()

    message_record = {
        'conversation_id': conversation_id,
        'timestamp': int(current_time.timestamp()),
        'timestamp_iso': current_time.isoformat() + 'Z',
        'message_id': message_id,
        'user_id': user_id,
        'message_type': message_type,
        'content': content,
        'status': 'completed' if message_type == 'assistant' else 'received',
        'environment': ENVIRONMENT,
        'project': PROJECT_NAME
    }

    if parent_message_id:
        message_record['parent_message_id'] = parent_message_id

    if processing_time_ms:
        message_record['processing_time_ms'] = Decimal(str(processing_time_ms))

    try:
        messages_table.put_item(Item=message_record)
        logger.info(f"Saved {message_type} message {message_id} to conversation {conversation_id}")
    except Exception as e:
        logger.error(f"Failed to save message: {e}")

    return message_id
