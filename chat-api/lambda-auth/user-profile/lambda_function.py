"""
User Profile Lambda Function
Retrieves authenticated user's profile information
"""

import json
import os
import boto3
import logging
from datetime import datetime, timezone

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')

# Environment variables
USERS_TABLE = os.environ['USERS_TABLE']
SESSIONS_TABLE = os.environ['SESSIONS_TABLE']

# DynamoDB tables
users_table = dynamodb.Table(USERS_TABLE)
sessions_table = dynamodb.Table(SESSIONS_TABLE)

def lambda_handler(event, context):
    """
    Retrieve authenticated user's profile
    GET /user/profile
    """
    try:
        # Extract user_id from JWT context (set by authorizer)
        user_id = event['requestContext']['authorizer']['user_id']
        session_id = event['requestContext']['authorizer'].get('session_id')
        
        logger.info(f"Retrieving profile for user: {user_id}")
        
        # Handle CORS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Access-Control-Allow-Methods': 'OPTIONS,GET'
                },
                'body': ''
            }
        
        # Get user profile
        response = users_table.get_item(
            Key={'user_id': user_id}
        )
        
        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({'error': 'User not found'})
            }
        
        user_data = response['Item']
        
        # Get current session info if available
        session_info = None
        if session_id:
            session_response = sessions_table.get_item(
                Key={'session_id': session_id}
            )
            if 'Item' in session_response:
                session_info = {
                    'session_id': session_id,
                    'created_at': session_response['Item'].get('created_at'),
                    'last_activity': session_response['Item'].get('last_activity'),
                    'expires_at': session_response['Item'].get('expires_at')
                }
        
        # Build profile response
        profile = {
            'user': {
                'id': user_data['user_id'],
                'email': user_data['email'],
                'name': user_data['name'],
                'picture': user_data.get('picture', ''),
                'subscription_tier': user_data.get('subscription_tier', 'free'),
                'preferences': user_data.get('preferences', {}),
                'created_at': user_data.get('created_at'),
                'updated_at': user_data.get('updated_at'),
                'email_verified': user_data.get('email_verified', False)
            },
            'session': session_info,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'OPTIONS,GET',
                'Content-Type': 'application/json'
            },
            'body': json.dumps(profile)
        }
        
    except Exception as e:
        logger.error(f"Error retrieving user profile: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'error': 'Failed to retrieve user profile'})
        }
