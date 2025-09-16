# Chat History Implementation Guide

## Overview
This guide outlines the steps to implement full chat history functionality by adding missing attributes and a new Conversations table to the existing DynamoDB infrastructure.

## Table of Contents
1. [Schema Changes Overview](#schema-changes-overview)
2. [Phase 1: Add Conversations Table](#phase-1-add-conversations-table)
3. [Phase 2: Add Missing Attributes](#phase-2-add-missing-attributes)
4. [Phase 3: Rename session_id to conversation_id](#phase-3-rename-session_id-to-conversation_id)
5. [Phase 4: Update Lambda Functions](#phase-4-update-lambda-functions)
6. [Phase 5: Data Migration](#phase-5-data-migration)
7. [Phase 6: Testing & Validation](#phase-6-testing--validation)

## Schema Changes Overview

### New Table: Conversations
- Organizes chat sessions with meaningful titles
- Enables archiving and better user experience
- Links to messages via conversation_id

### Enhanced Attributes
- **Users Table**: Add subscription_tier and created_at
- **Chat Messages**: Add tokens_used and model tracking
- **Consistent Naming**: Transition from session_id to conversation_id

## Phase 1: Add Conversations Table

### 1.1 Terraform Configuration
Create new table definition in `terraform/modules/dynamodb/conversations.tf`:

```hcl
resource "aws_dynamodb_table" "conversations" {
  name         = "${var.project_name}-${var.environment}-conversations"
  billing_mode = var.billing_mode

  # Primary key
  hash_key  = "conversation_id"

  attribute {
    name = "conversation_id"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "updated_at"
    type = "N"
  }

  # Global Secondary Index for user queries
  global_secondary_index {
    name            = "user-conversations-index"
    hash_key        = "user_id"
    range_key       = "updated_at"
    projection_type = "ALL"
  }

  # Encryption
  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  # Point-in-time recovery
  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-${var.environment}-conversations"
      Type = "Conversations"
    }
  )
}
```

### 1.2 Update Module Outputs
Add to `terraform/modules/dynamodb/outputs.tf`:

```hcl
output "conversations_table_name" {
  description = "Name of the conversations DynamoDB table"
  value       = aws_dynamodb_table.conversations.name
}

output "conversations_table_arn" {
  description = "ARN of the conversations DynamoDB table"
  value       = aws_dynamodb_table.conversations.arn
}
```

## Phase 2: Add Missing Attributes

### 2.1 Users Table Attributes
Since DynamoDB is schemaless, we'll update the Lambda functions to include new attributes when writing:

**New attributes to add:**
- `subscription_tier`: "free" | "basic" | "premium" | "enterprise"
- `created_at`: ISO timestamp of account creation

### 2.2 Chat Messages Table Attributes
**New attributes to add:**
- `tokens_used`: Number of tokens consumed
- `model`: AI model identifier (e.g., "claude-3-sonnet", "gpt-4")

## Phase 3: Rename session_id to conversation_id

### 3.1 Strategy
Since we can't rename DynamoDB keys directly, we'll:
1. Keep existing session_id for backward compatibility
2. Add conversation_id as an alias initially
3. Gradually migrate to conversation_id
4. Eventually deprecate session_id

### 3.2 Migration Approach
Create a migration script `scripts/migrate/session_to_conversation.py`:

```python
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

def migrate_conversations_table():
    """Create conversations from existing sessions."""
    sessions_table = dynamodb.Table('buffett-dev-chat-sessions')
    conversations_table = dynamodb.Table('buffett-dev-conversations')

    # Scan all sessions
    response = sessions_table.scan()
    sessions = response['Items']

    logger.info(f"Found {len(sessions)} sessions to migrate")

    # Group sessions by session_id (since there can be multiple entries per session)
    session_groups = {}
    for session in sessions:
        session_id = session['session_id']
        if session_id not in session_groups:
            session_groups[session_id] = []
        session_groups[session_id].append(session)

    # Create conversation for each unique session
    for session_id, session_entries in session_groups.items():
        # Use the most recent session entry
        latest_session = max(session_entries, key=lambda x: x.get('timestamp', 0))

        conversation = {
            'conversation_id': session_id,  # Use session_id as conversation_id initially
            'user_id': latest_session['user_id'],
            'title': f"Chat from {latest_session.get('created_at', 'Unknown date')}",
            'created_at': latest_session.get('created_at', datetime.utcnow().isoformat()),
            'updated_at': int(datetime.utcnow().timestamp()),
            'message_count': latest_session.get('message_count', 0),
            'is_archived': False,
            'legacy_session_id': session_id  # Keep reference to original
        }

        try:
            conversations_table.put_item(Item=conversation)
            logger.info(f"Created conversation for session {session_id}")
        except Exception as e:
            logger.error(f"Failed to create conversation for session {session_id}: {e}")

    logger.info("Conversation migration completed")

def update_messages_table():
    """Add conversation_id to existing messages."""
    messages_table = dynamodb.Table('buffett-dev-chat-messages')

    # Scan all messages
    response = messages_table.scan()
    messages = response['Items']

    logger.info(f"Found {len(messages)} messages to update")

    with messages_table.batch_writer() as batch:
        for message in messages:
            # Add conversation_id (initially same as session_id)
            message['conversation_id'] = message['session_id']

            # Add placeholder values for new attributes
            if 'tokens_used' not in message:
                message['tokens_used'] = 0
            if 'model' not in message:
                message['model'] = 'bedrock-default'

            batch.put_item(Item=message)

    logger.info("Messages update completed")

def update_users_table():
    """Add missing attributes to users."""
    users_table = dynamodb.Table('buffett-dev-users')

    # Scan all users
    response = users_table.scan()
    users = response['Items']

    logger.info(f"Found {len(users)} users to update")

    for user in users:
        update_expr = []
        expr_attr_values = {}

        # Add subscription_tier if missing
        if 'subscription_tier' not in user:
            update_expr.append('subscription_tier = :tier')
            expr_attr_values[':tier'] = 'free'

        # Add created_at if missing (use updated_at as fallback)
        if 'created_at' not in user:
            update_expr.append('created_at = :created')
            expr_attr_values[':created'] = user.get('updated_at', datetime.utcnow().isoformat())

        if update_expr:
            try:
                users_table.update_item(
                    Key={'user_id': user['user_id']},
                    UpdateExpression='SET ' + ', '.join(update_expr),
                    ExpressionAttributeValues=expr_attr_values
                )
                logger.info(f"Updated user {user['user_id']}")
            except Exception as e:
                logger.error(f"Failed to update user {user['user_id']}: {e}")

    logger.info("Users update completed")

if __name__ == "__main__":
    print("Starting DynamoDB migration for chat history...")

    # Step 1: Create conversations from sessions
    migrate_conversations_table()

    # Step 2: Update messages with new attributes
    update_messages_table()

    # Step 3: Update users with missing attributes
    update_users_table()

    print("Migration completed successfully!")
```

## Phase 4: Update Lambda Functions

### 4.1 Update websocket_connect.py
Add conversation creation when establishing new connections:

```python
# In websocket_connect.py, after session creation
def create_or_update_conversation(session_id, user_id, user_type):
    """Create or update a conversation record."""
    conversations_table = dynamodb.Table(CONVERSATIONS_TABLE)

    conversation_data = {
        'conversation_id': session_id,  # Initially use session_id
        'user_id': user_id,
        'title': f"New conversation",  # Will be updated based on first message
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': int(datetime.utcnow().timestamp()),
        'message_count': 0,
        'is_archived': False,
        'user_type': user_type
    }

    conversations_table.put_item(Item=conversation_data)
```

### 4.2 Update chat_processor.py
Add token tracking and model information:

```python
# In chat_processor.py, when storing AI response
def store_ai_response(session_id, response_content, tokens_used, model_id):
    """Store AI response with token tracking."""
    message_record = {
        'session_id': session_id,
        'conversation_id': session_id,  # Add conversation_id
        'timestamp': int(datetime.utcnow().timestamp()),
        'message_id': str(uuid.uuid4()),
        'message_type': 'assistant',
        'content': response_content,
        'tokens_used': tokens_used,
        'model': model_id,
        'status': 'delivered'
    }

    messages_table.put_item(Item=message_record)

    # Update conversation metadata
    update_conversation_metadata(session_id, tokens_used)
```

### 4.3 Add New Endpoints for Conversation Management
Create `backend/src/handlers/conversations_handler.py`:

```python
"""
Conversations Handler
Manages chat conversations including listing, updating titles, and archiving.
"""

import json
import boto3
import logging
import os
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

dynamodb = boto3.resource('dynamodb')
CONVERSATIONS_TABLE = os.environ['CONVERSATIONS_TABLE']
conversations_table = dynamodb.Table(CONVERSATIONS_TABLE)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle conversation management requests."""

    http_method = event['requestContext']['http']['method']
    path = event['requestContext']['http']['path']

    if http_method == 'GET' and path == '/conversations':
        return list_conversations(event)
    elif http_method == 'PATCH' and '/conversations/' in path:
        return update_conversation(event)
    elif http_method == 'DELETE' and '/conversations/' in path:
        return archive_conversation(event)
    else:
        return create_response(404, {'error': 'Not found'})

def list_conversations(event: Dict[str, Any]) -> Dict[str, Any]:
    """List all conversations for a user."""
    user_id = event['requestContext']['authorizer']['user_id']

    response = conversations_table.query(
        IndexName='user-conversations-index',
        KeyConditionExpression='user_id = :user_id',
        ExpressionAttributeValues={':user_id': user_id},
        ScanIndexForward=False  # Most recent first
    )

    conversations = response.get('Items', [])

    # Filter out archived unless requested
    include_archived = event.get('queryStringParameters', {}).get('include_archived', 'false') == 'true'
    if not include_archived:
        conversations = [c for c in conversations if not c.get('is_archived', False)]

    return create_response(200, {'conversations': conversations})

def update_conversation(event: Dict[str, Any]) -> Dict[str, Any]:
    """Update conversation title or other metadata."""
    conversation_id = event['pathParameters']['conversation_id']
    user_id = event['requestContext']['authorizer']['user_id']
    body = json.loads(event.get('body', '{}'))

    # Verify ownership
    conversation = conversations_table.get_item(
        Key={'conversation_id': conversation_id}
    ).get('Item')

    if not conversation or conversation['user_id'] != user_id:
        return create_response(404, {'error': 'Conversation not found'})

    # Update allowed fields
    update_expr = []
    expr_attr_values = {}

    if 'title' in body:
        update_expr.append('title = :title')
        expr_attr_values[':title'] = body['title']

    if 'is_archived' in body:
        update_expr.append('is_archived = :archived')
        expr_attr_values[':archived'] = body['is_archived']

    if update_expr:
        update_expr.append('updated_at = :updated')
        expr_attr_values[':updated'] = int(datetime.utcnow().timestamp())

        conversations_table.update_item(
            Key={'conversation_id': conversation_id},
            UpdateExpression='SET ' + ', '.join(update_expr),
            ExpressionAttributeValues=expr_attr_values
        )

    return create_response(200, {'message': 'Conversation updated'})

def archive_conversation(event: Dict[str, Any]) -> Dict[str, Any]:
    """Archive (soft delete) a conversation."""
    conversation_id = event['pathParameters']['conversation_id']
    user_id = event['requestContext']['authorizer']['user_id']

    # Verify ownership and archive
    conversations_table.update_item(
        Key={'conversation_id': conversation_id},
        UpdateExpression='SET is_archived = :archived, updated_at = :updated',
        ExpressionAttributeValues={
            ':archived': True,
            ':updated': int(datetime.utcnow().timestamp()),
            ':user': user_id
        },
        ConditionExpression='user_id = :user'
    )

    return create_response(200, {'message': 'Conversation archived'})

def create_response(status_code: int, body: Any = None) -> Dict[str, Any]:
    """Create API Gateway response."""
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(body) if body else ''
    }
```

## Phase 5: Data Migration

### 5.1 Pre-Migration Checklist
- [ ] Backup all DynamoDB tables
- [ ] Test migration script in dev environment
- [ ] Update Lambda function code
- [ ] Deploy Terraform changes

### 5.2 Migration Steps
```bash
# 1. Apply Terraform changes to create new table
cd terraform/environments/dev
terraform plan
terraform apply

# 2. Run migration script
cd ../../scripts/migrate
python3 session_to_conversation.py

# 3. Deploy updated Lambda functions
cd ../build
./package-lambdas.sh
cd ../../terraform/environments/dev
terraform apply
```

### 5.3 Rollback Plan
If issues occur:
1. Lambda functions support both session_id and conversation_id
2. No data is deleted, only added
3. Can revert Lambda code while keeping data changes

## Phase 6: Testing & Validation

### 6.1 Test Scenarios
1. **New User Registration**: Verify subscription_tier and created_at are set
2. **New Conversation**: Verify conversation record is created
3. **Message Flow**: Verify tokens_used and model are tracked
4. **List Conversations**: Verify user can see their conversations
5. **Archive Conversation**: Verify soft delete works

### 6.2 Validation Script
Create `scripts/validate/chat_history_validation.py`:

```python
#!/usr/bin/env python3
"""Validate chat history implementation."""

import boto3
import sys
from datetime import datetime

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

def validate_conversations_table():
    """Validate conversations table exists and has data."""
    table = dynamodb.Table('buffett-dev-conversations')
    response = table.scan(Limit=1)

    if response['Count'] > 0:
        item = response['Items'][0]
        required_fields = ['conversation_id', 'user_id', 'title', 'created_at', 'is_archived']
        missing = [f for f in required_fields if f not in item]

        if missing:
            print(f"❌ Conversations table missing fields: {missing}")
            return False
        print("✅ Conversations table validated")
        return True
    else:
        print("⚠️  Conversations table is empty")
        return True

def validate_messages_attributes():
    """Validate messages have new attributes."""
    table = dynamodb.Table('buffett-dev-chat-messages')
    response = table.scan(Limit=5)

    if response['Count'] > 0:
        for item in response['Items']:
            if 'tokens_used' not in item or 'model' not in item:
                print(f"❌ Messages missing new attributes in {item['message_id']}")
                return False
        print("✅ Messages table validated")
        return True
    return True

def validate_users_attributes():
    """Validate users have new attributes."""
    table = dynamodb.Table('buffett-dev-users')
    response = table.scan(Limit=5)

    if response['Count'] > 0:
        for item in response['Items']:
            if 'subscription_tier' not in item or 'created_at' not in item:
                print(f"❌ Users missing new attributes for {item['user_id']}")
                return False
        print("✅ Users table validated")
        return True
    return True

if __name__ == "__main__":
    print("Validating chat history implementation...")

    all_valid = True
    all_valid &= validate_conversations_table()
    all_valid &= validate_messages_attributes()
    all_valid &= validate_users_attributes()

    if all_valid:
        print("\n✅ All validations passed!")
    else:
        print("\n❌ Some validations failed. Please check the logs above.")
        sys.exit(1)
```

## Environment Variables Update

Add to Lambda environment variables in Terraform:

```hcl
# In terraform/environments/dev/main.tf
lambda_common_env_vars = {
  # ... existing vars ...
  CONVERSATIONS_TABLE = module.dynamodb.conversations_table_name
}
```

## API Endpoints

### New REST Endpoints
- `GET /conversations` - List user's conversations
- `GET /conversations/{id}/messages` - Get messages for a conversation
- `PATCH /conversations/{id}` - Update conversation (title, archive)
- `DELETE /conversations/{id}` - Archive conversation

### WebSocket Updates
- Connection establishment creates conversation record
- Messages include token tracking
- Real-time conversation title updates

## Timeline

### Week 1
- Day 1-2: Create Terraform configs and deploy Conversations table
- Day 3-4: Update Lambda functions with new attributes
- Day 5: Run migration scripts in dev

### Week 2
- Day 1-2: Testing and validation
- Day 3-4: Deploy to staging environment
- Day 5: Production deployment

## Monitoring

Add CloudWatch alarms for:
- Conversations table read/write throttles
- Migration script errors
- Lambda function errors related to new attributes

## Success Criteria

- [ ] All existing sessions migrated to conversations
- [ ] New messages track tokens and model
- [ ] Users can list and manage conversations
- [ ] No disruption to existing chat functionality
- [ ] Performance remains within acceptable limits