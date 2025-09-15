# Phase 4: Security & Authentication Implementation Guide
## Warren Buffett Financial Advisor Chat API

### Executive Summary

This guide provides a comprehensive implementation strategy for Phase 4, focusing on security and authentication using Google OAuth 2.0 as the primary authentication mechanism. The implementation replaces the complex AWS Cognito setup with Google OAuth while maintaining enterprise-grade security standards and includes JWT authorization, input validation, WAF protection, and comprehensive security monitoring.

### Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│  Google OAuth    │────▶│   API Gateway   │
│  (React/Next)   │     │     Server       │     │  (HTTP + WS)    │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                           │
                                ┌──────────────────────────┴────────────────────────────┐
                                │                                                       │
                    ┌───────────▼──────────┐                           ┌───────────────▼──────────────┐
                    │   Custom Authorizer   │                           │        WAF Rules             │
                    │   (JWT Validation)    │                           │   (Rate Limiting, DDoS)      │
                    └───────────┬──────────┘                           └──────────────────────────────┘
                                │
                    ┌───────────▼──────────┐
                    │    Lambda Functions   │
                    │  - Auth Verification  │
                    │  - User Management    │
                    │  - Session Handler    │
                    └───────────┬──────────┘
                                │
                    ┌───────────▼──────────┐
                    │    DynamoDB Tables    │
                    │  - Users              │
                    │  - Sessions           │
                    │  - Security Logs     │
                    └──────────────────────┘
```

### Table of Contents

1. [Phase 4A: Google OAuth Setup](#phase-4a-google-oauth-setup)
2. [Phase 4B: AWS Infrastructure & JWT Authorization](#phase-4b-aws-infrastructure--jwt-authorization)
3. [Phase 4C: WebSocket Authentication Integration](#phase-4c-websocket-authentication-integration)
4. [Phase 4D: Input Validation & Sanitization](#phase-4d-input-validation--sanitization)
5. [Phase 4E: WAF Configuration](#phase-4e-waf-configuration)
6. [Phase 4F: Security Monitoring & Alerting](#phase-4f-security-monitoring--alerting)
7. [Phase 4G: Testing & Validation](#phase-4g-testing--validation)
8. [Migration & Rollback Strategy](#migration--rollback-strategy)

---

## Phase 4A: Google OAuth Setup

### Infrastructure Directory Structure

```
📁 buffett_chat_api/
├── 📁 chat-api/
│   ├── 📁 auth/
│   │   ├── main.tf                    # Auth infrastructure
│   │   ├── variables.tf               # Auth variables
│   │   ├── outputs.tf                 # Auth outputs
│   │   ├── google-oauth.tf            # Google OAuth specific config
│   │   ├── jwt-authorizer.tf          # JWT custom authorizer
│   │   └── dynamodb-auth.tf           # Auth-related DynamoDB tables
│   ├── 📁 lambda-auth/
│   │   ├── 📁 auth-verify/
│   │   │   ├── lambda_function.py     # Google token verification
│   │   │   └── requirements.txt
│   │   ├── 📁 jwt-authorizer/
│   │   │   ├── lambda_function.py     # JWT validation for API Gateway
│   │   │   └── requirements.txt
│   │   ├── 📁 user-profile/
│   │   │   ├── lambda_function.py     # User profile management
│   │   │   └── requirements.txt
│   │   └── 📁 session-manager/
│   │       ├── lambda_function.py     # Session management
│   │       └── requirements.txt
│   └── 📁 security/
│       ├── waf.tf                     # WAF configuration
│       ├── security-monitoring.tf      # Security monitoring
│       └── input-validation.tf         # Input validation rules
```

### Google Cloud Console Configuration

#### 1. Create Google OAuth Application

```bash
# Navigate to Google Cloud Console
# https://console.cloud.google.com/

# Create new project or select existing
Project Name: buffett-financial-advisor
Project ID: buffett-advisor-prod

# Enable required APIs
- Google+ API
- Google Identity Toolkit API
```1

#### 2. Configure OAuth 2.0 Credentials

```yaml
Application Type: Web Application
Name: Buffett Financial Advisor Chat

Authorized JavaScript Origins:
  Development:
    - http://localhost:3000
    - http://localhost:5173
  Staging:
    - https://staging.buffett-advisor.com
  Production:
    - https://buffett-advisor.com
    - https://www.buffett-advisor.com

Authorized Redirect URIs:
  Development:
    - http://localhost:3000/auth/callback
    - http://localhost:5173/auth/callback
  Staging:
    - https://staging.buffett-advisor.com/auth/callback
  Production:
    - https://buffett-advisor.com/auth/callback
    - https://www.buffett-advisor.com/auth/callback
```

#### 3. Environment Configuration

```bash
# terraform.tfvars
google_client_id     = "123456789-abcdefgh.apps.googleusercontent.com"
google_client_secret = "GOCSPX-xxxxxxxxxxxxxxxxxxxx"  # Store in AWS Secrets Manager
jwt_secret          = "your-256-bit-secret-key"        # Generate securely
```

---

## Phase 4B: AWS Infrastructure & JWT Authorization

### Main Authentication Infrastructure (auth/main.tf)

```terraform
# Phase 4: Authentication Infrastructure
# ======================================

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ================================================
# Authentication DynamoDB Tables
# ================================================

resource "aws_dynamodb_table" "users" {
  name           = "${var.project_name}-${var.environment}-users"
  billing_mode   = var.dynamodb_billing_mode
  hash_key       = "user_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "email"
    type = "S"
  }

  global_secondary_index {
    name            = "email-index"
    hash_key        = "email"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.environment == "prod" ? true : false
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.auth_encryption_key.arn
  }

  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-users"
    Purpose = "User profile storage"
    Phase   = "Phase 4"
  })
}

resource "aws_dynamodb_table" "sessions" {
  name           = "${var.project_name}-${var.environment}-sessions"
  billing_mode   = var.dynamodb_billing_mode
  hash_key       = "session_id"

  attribute {
    name = "session_id"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  global_secondary_index {
    name            = "user-sessions-index"
    hash_key        = "user_id"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.auth_encryption_key.arn
  }

  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-sessions"
    Purpose = "Session management with TTL"
    Phase   = "Phase 4"
  })
}

resource "aws_dynamodb_table" "security_events" {
  name           = "${var.project_name}-${var.environment}-security-events"
  billing_mode   = var.dynamodb_billing_mode
  hash_key       = "event_id"
  range_key      = "timestamp"

  attribute {
    name = "event_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "N"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "event_type"
    type = "S"
  }

  global_secondary_index {
    name            = "user-events-index"
    hash_key        = "user_id"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "event-type-index"
    hash_key        = "event_type"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-security-events"
    Purpose = "Security event logging and audit trail"
    Phase   = "Phase 4"
  })
}

# ================================================
# KMS Key for Authentication Data Encryption
# ================================================

resource "aws_kms_key" "auth_encryption_key" {
  description             = "KMS key for authentication data encryption"
  deletion_window_in_days = var.environment == "prod" ? 30 : 7
  enable_key_rotation     = true

  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-auth-key"
    Purpose = "Authentication data encryption"
    Phase   = "Phase 4"
  })
}

resource "aws_kms_alias" "auth_encryption_key_alias" {
  name          = "alias/${var.project_name}-${var.environment}-auth"
  target_key_id = aws_kms_key.auth_encryption_key.key_id
}

# ================================================
# Secrets Manager for Sensitive Auth Data
# ================================================

resource "aws_secretsmanager_secret" "google_oauth_credentials" {
  name = "${var.project_name}-${var.environment}-google-oauth"
  
  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-google-oauth"
    Purpose = "Google OAuth credentials"
    Phase   = "Phase 4"
  })
}

resource "aws_secretsmanager_secret_version" "google_oauth_credentials" {
  secret_id = aws_secretsmanager_secret.google_oauth_credentials.id
  secret_string = jsonencode({
    client_id     = var.google_client_id
    client_secret = var.google_client_secret
  })
}

resource "aws_secretsmanager_secret" "jwt_secret" {
  name = "${var.project_name}-${var.environment}-jwt-secret"
  
  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-jwt-secret"
    Purpose = "JWT signing secret"
    Phase   = "Phase 4"
  })
}

resource "aws_secretsmanager_secret_version" "jwt_secret" {
  secret_id     = aws_secretsmanager_secret.jwt_secret.id
  secret_string = var.jwt_secret
}

# ================================================
# Lambda Functions for Authentication
# ================================================

# IAM Role for Auth Lambda Functions
resource "aws_iam_role" "auth_lambda_role" {
  name = "${var.project_name}-${var.environment}-auth-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-auth-lambda-role"
    Purpose = "Role for authentication Lambda functions"
    Phase   = "Phase 4"
  })
}

# IAM Policy for Auth Lambda Functions
resource "aws_iam_policy" "auth_lambda_policy" {
  name        = "${var.project_name}-${var.environment}-auth-lambda-policy"
  description = "Policy for authentication Lambda functions"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.users.arn,
          aws_dynamodb_table.sessions.arn,
          aws_dynamodb_table.security_events.arn,
          "${aws_dynamodb_table.users.arn}/index/*",
          "${aws_dynamodb_table.sessions.arn}/index/*",
          "${aws_dynamodb_table.security_events.arn}/index/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.google_oauth_credentials.arn,
          aws_secretsmanager_secret.jwt_secret.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = [
          aws_kms_key.auth_encryption_key.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "auth_lambda_policy_attachment" {
  role       = aws_iam_role.auth_lambda_role.name
  policy_arn = aws_iam_policy.auth_lambda_policy.arn
}

# Google OAuth Verification Lambda
data "archive_file" "auth_verify_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda-auth/auth-verify"
  output_path = "${path.module}/../lambda-auth/auth-verify.zip"
}

resource "aws_lambda_function" "auth_verify" {
  filename         = data.archive_file.auth_verify_zip.output_path
  function_name    = "${var.project_name}-${var.environment}-auth-verify"
  role            = aws_iam_role.auth_lambda_role.arn
  handler         = "lambda_function.lambda_handler"
  runtime         = "python3.11"
  timeout         = 30
  memory_size     = 512
  source_code_hash = data.archive_file.auth_verify_zip.output_base64sha256

  environment {
    variables = {
      GOOGLE_CLIENT_ID_SECRET = aws_secretsmanager_secret.google_oauth_credentials.name
      JWT_SECRET_NAME         = aws_secretsmanager_secret.jwt_secret.name
      USERS_TABLE            = aws_dynamodb_table.users.name
      SESSIONS_TABLE         = aws_dynamodb_table.sessions.name
      SECURITY_EVENTS_TABLE  = aws_dynamodb_table.security_events.name
      ENVIRONMENT            = var.environment
      PROJECT_NAME           = var.project_name
    }
  }

  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-auth-verify"
    Purpose = "Google OAuth token verification"
    Phase   = "Phase 4"
  })
}

# JWT Authorizer Lambda for API Gateway
data "archive_file" "jwt_authorizer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda-auth/jwt-authorizer"
  output_path = "${path.module}/../lambda-auth/jwt-authorizer.zip"
}

resource "aws_lambda_function" "jwt_authorizer" {
  filename         = data.archive_file.jwt_authorizer_zip.output_path
  function_name    = "${var.project_name}-${var.environment}-jwt-authorizer"
  role            = aws_iam_role.auth_lambda_role.arn
  handler         = "lambda_function.lambda_handler"
  runtime         = "python3.11"
  timeout         = 10
  memory_size     = 256
  source_code_hash = data.archive_file.jwt_authorizer_zip.output_base64sha256

  environment {
    variables = {
      JWT_SECRET_NAME       = aws_secretsmanager_secret.jwt_secret.name
      SESSIONS_TABLE        = aws_dynamodb_table.sessions.name
      SECURITY_EVENTS_TABLE = aws_dynamodb_table.security_events.name
      ENVIRONMENT           = var.environment
    }
  }

  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-jwt-authorizer"
    Purpose = "JWT validation for API Gateway"
    Phase   = "Phase 4"
  })
}

# Lambda permission for API Gateway to invoke authorizer
resource "aws_lambda_permission" "api_gateway_authorizer" {
  statement_id  = "AllowAPIGatewayInvokeAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.jwt_authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "arn:aws:execute-api:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*/*"
}

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "auth_verify_logs" {
  name              = "/aws/lambda/${aws_lambda_function.auth_verify.function_name}"
  retention_in_days = var.log_retention_days

  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-auth-verify-logs"
    Purpose = "Auth verification Lambda logs"
    Phase   = "Phase 4"
  })
}

resource "aws_cloudwatch_log_group" "jwt_authorizer_logs" {
  name              = "/aws/lambda/${aws_lambda_function.jwt_authorizer.function_name}"
  retention_in_days = var.log_retention_days

  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-jwt-authorizer-logs"
    Purpose = "JWT authorizer Lambda logs"
    Phase   = "Phase 4"
  })
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}
```

### JWT Authorizer Lambda Function (lambda-auth/jwt-authorizer/lambda_function.py)

```python
import json
import os
import jwt
import time
import boto3
from datetime import datetime
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
secrets_client = boto3.client('secretsmanager')
dynamodb = boto3.resource('dynamodb')

# Environment variables
JWT_SECRET_NAME = os.environ['JWT_SECRET_NAME']
SESSIONS_TABLE = os.environ['SESSIONS_TABLE']
SECURITY_EVENTS_TABLE = os.environ['SECURITY_EVENTS_TABLE']
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')

# Cache for JWT secret
jwt_secret_cache = None
jwt_secret_cache_time = 0
JWT_SECRET_CACHE_TTL = 300  # 5 minutes

def get_jwt_secret():
    """Get JWT secret from Secrets Manager with caching"""
    global jwt_secret_cache, jwt_secret_cache_time
    
    current_time = time.time()
    if jwt_secret_cache and (current_time - jwt_secret_cache_time) < JWT_SECRET_CACHE_TTL:
        return jwt_secret_cache
    
    try:
        response = secrets_client.get_secret_value(SecretId=JWT_SECRET_NAME)
        jwt_secret_cache = response['SecretString']
        jwt_secret_cache_time = current_time
        return jwt_secret_cache
    except Exception as e:
        logger.error(f"Error retrieving JWT secret: {str(e)}")
        raise Exception('Unable to retrieve JWT secret')

def log_security_event(event_type, user_id=None, details=None, success=True):
    """Log security events to DynamoDB"""
    try:
        security_table = dynamodb.Table(SECURITY_EVENTS_TABLE)
        event_id = f"{event_type}_{int(time.time() * 1000)}_{os.urandom(4).hex()}"
        
        item = {
            'event_id': event_id,
            'timestamp': int(time.time() * 1000),
            'event_type': event_type,
            'success': success,
            'environment': ENVIRONMENT,
            'details': details or {},
            'ttl': int(time.time()) + (90 * 24 * 60 * 60)  # 90 days retention
        }
        
        if user_id:
            item['user_id'] = user_id
        
        security_table.put_item(Item=item)
    except Exception as e:
        logger.error(f"Error logging security event: {str(e)}")

def lambda_handler(event, context):
    """
    API Gateway Custom Authorizer for JWT validation
    Supports both HTTP API and WebSocket API
    """
    try:
        # Extract token based on event type
        token = None
        method_arn = None
        
        # Check if this is a WebSocket request
        if 'methodArn' in event:
            # REST API or WebSocket $connect
            method_arn = event['methodArn']
            
            # Try to get token from different sources
            if 'authorizationToken' in event:
                token = event['authorizationToken']
            elif 'headers' in event:
                # WebSocket connection might have token in headers
                auth_header = event['headers'].get('Authorization') or event['headers'].get('authorization')
                if auth_header:
                    token = auth_header
            elif 'queryStringParameters' in event:
                # WebSocket might pass token as query parameter
                token = event['queryStringParameters'].get('token')
        
        # HTTP API format
        elif 'headers' in event and 'authorization' in event['headers']:
            token = event['headers']['authorization']
            method_arn = event['routeArn'] if 'routeArn' in event else event['methodArn']
        
        if not token:
            logger.warning("No authorization token provided")
            log_security_event('jwt_validation_failed', details={'error': 'No token provided'}, success=False)
            raise Exception('Unauthorized')
        
        # Remove 'Bearer ' prefix if present
        if token.startswith('Bearer '):
            token = token[7:]
        
        # Get JWT secret
        jwt_secret = get_jwt_secret()
        
        # Verify JWT token
        try:
            payload = jwt.decode(token, jwt_secret, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired")
            log_security_event('jwt_validation_failed', details={'error': 'Token expired'}, success=False)
            raise Exception('Unauthorized - Token expired')
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {str(e)}")
            log_security_event('jwt_validation_failed', details={'error': 'Invalid token'}, success=False)
            raise Exception('Unauthorized - Invalid token')
        
        # Extract user information
        user_id = payload.get('user_id')
        session_id = payload.get('session_id')
        
        if not user_id or not session_id:
            logger.warning("Token missing required claims")
            log_security_event('jwt_validation_failed', user_id=user_id, 
                             details={'error': 'Missing claims'}, success=False)
            raise Exception('Unauthorized - Invalid token claims')
        
        # Verify session is still valid
        sessions_table = dynamodb.Table(SESSIONS_TABLE)
        try:
            response = sessions_table.get_item(Key={'session_id': session_id})
            if 'Item' not in response:
                logger.warning(f"Session not found: {session_id}")
                log_security_event('session_validation_failed', user_id=user_id,
                                 details={'session_id': session_id}, success=False)
                raise Exception('Unauthorized - Invalid session')
            
            session = response['Item']
            
            # Verify session belongs to user
            if session['user_id'] != user_id:
                logger.warning("Session user mismatch")
                log_security_event('session_validation_failed', user_id=user_id,
                                 details={'error': 'User mismatch'}, success=False)
                raise Exception('Unauthorized - Invalid session')
            
            # Update last activity
            sessions_table.update_item(
                Key={'session_id': session_id},
                UpdateExpression='SET last_activity = :activity',
                ExpressionAttributeValues={
                    ':activity': datetime.utcnow().isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"Error validating session: {str(e)}")
            raise Exception('Unauthorized')
        
        # Log successful validation
        log_security_event('jwt_validation_success', user_id=user_id, success=True)
        
        # Generate policy
        policy = generate_policy(user_id, 'Allow', method_arn)
        
        # Add context for downstream services
        policy['context'] = {
            'user_id': user_id,
            'session_id': session_id,
            'email': session.get('email', ''),
            'subscription_tier': session.get('subscription_tier', 'free')
        }
        
        return policy
        
    except Exception as e:
        logger.error(f"Authorization error: {str(e)}")
        raise Exception('Unauthorized')

def generate_policy(principal_id, effect, resource):
    """Generate API Gateway policy"""
    policy = {
        'principalId': principal_id
    }
    
    if effect and resource:
        policy['policyDocument'] = {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': 'execute-api:Invoke',
                    'Effect': effect,
                    'Resource': resource
                }
            ]
        }
    
    return policy
```

### Google OAuth Verification Lambda (lambda-auth/auth-verify/lambda_function.py)

```python
import json
import os
import jwt
import uuid
import time
import boto3
from datetime import datetime, timedelta
from google.auth.transport import requests
from google.oauth2 import id_token
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
secrets_client = boto3.client('secretsmanager')

# Environment variables
GOOGLE_CLIENT_ID_SECRET = os.environ['GOOGLE_CLIENT_ID_SECRET']
JWT_SECRET_NAME = os.environ['JWT_SECRET_NAME']
USERS_TABLE = os.environ['USERS_TABLE']
SESSIONS_TABLE = os.environ['SESSIONS_TABLE']
SECURITY_EVENTS_TABLE = os.environ['SECURITY_EVENTS_TABLE']
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat')

# Cache for secrets
secrets_cache = {}
secrets_cache_time = {}
SECRETS_CACHE_TTL = 300  # 5 minutes

def get_secret(secret_name):
    """Get secret from Secrets Manager with caching"""
    current_time = time.time()
    
    if secret_name in secrets_cache and (current_time - secrets_cache_time.get(secret_name, 0)) < SECRETS_CACHE_TTL:
        return secrets_cache[secret_name]
    
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret_value = response['SecretString']
        
        # Try to parse as JSON, otherwise return as string
        try:
            secret_value = json.loads(secret_value)
        except json.JSONDecodeError:
            pass
        
        secrets_cache[secret_name] = secret_value
        secrets_cache_time[secret_name] = current_time
        return secret_value
    except Exception as e:
        logger.error(f"Error retrieving secret {secret_name}: {str(e)}")
        raise

def log_security_event(event_type, user_id=None, details=None, success=True):
    """Log security events to DynamoDB"""
    try:
        security_table = dynamodb.Table(SECURITY_EVENTS_TABLE)
        event_id = f"{event_type}_{int(time.time() * 1000)}_{os.urandom(4).hex()}"
        
        item = {
            'event_id': event_id,
            'timestamp': int(time.time() * 1000),
            'event_type': event_type,
            'success': success,
            'environment': ENVIRONMENT,
            'project': PROJECT_NAME,
            'details': details or {},
            'ttl': int(time.time()) + (90 * 24 * 60 * 60)  # 90 days retention
        }
        
        if user_id:
            item['user_id'] = user_id
        
        security_table.put_item(Item=item)
    except Exception as e:
        logger.error(f"Error logging security event: {str(e)}")

def lambda_handler(event, context):
    """Handle Google OAuth authentication requests"""
    try:
        # Parse request
        body = json.loads(event.get('body', '{}'))
        google_token = body.get('token')
        
        if not google_token:
            log_security_event('auth_failed', details={'error': 'No token provided'}, success=False)
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Access-Control-Allow-Methods': 'OPTIONS,POST'
                },
                'body': json.dumps({'error': 'Google token is required'})
            }
        
        # Get Google client ID
        google_secrets = get_secret(GOOGLE_CLIENT_ID_SECRET)
        google_client_id = google_secrets['client_id'] if isinstance(google_secrets, dict) else google_secrets
        
        # Verify Google token
        try:
            idinfo = id_token.verify_oauth2_token(google_token, requests.Request(), google_client_id)
            
            # Verify the issuer
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise ValueError('Invalid issuer')
            
            user_info = {
                'user_id': idinfo['sub'],
                'email': idinfo['email'],
                'name': idinfo.get('name', ''),
                'picture': idinfo.get('picture', ''),
                'email_verified': idinfo.get('email_verified', False)
            }
            
        except ValueError as e:
            logger.warning(f"Google token verification failed: {str(e)}")
            log_security_event('google_auth_failed', details={'error': str(e)}, success=False)
            return {
                'statusCode': 401,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Invalid Google token'})
            }
        
        # Create or update user
        user_data = create_or_update_user(user_info)
        
        # Create session
        session_data = create_user_session(user_data['user_id'], user_data['email'])
        
        # Generate JWT token
        jwt_secret = get_secret(JWT_SECRET_NAME)
        jwt_token = generate_jwt_token(user_data['user_id'], session_data['session_id'], jwt_secret)
        
        # Log successful authentication
        log_security_event('auth_success', user_id=user_data['user_id'], success=True)
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'OPTIONS,POST'
            },
            'body': json.dumps({
                'token': jwt_token,
                'user': {
                    'id': user_data['user_id'],
                    'email': user_data['email'],
                    'name': user_data['name'],
                    'picture': user_data.get('picture', ''),
                    'subscription_tier': user_data.get('subscription_tier', 'free'),
                    'preferences': user_data.get('preferences', {})
                },
                'session': {
                    'id': session_data['session_id'],
                    'expires_at': session_data['expires_at']
                }
            })
        }
        
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        log_security_event('auth_error', details={'error': str(e)}, success=False)
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Internal server error'})
        }

def create_or_update_user(user_info):
    """Create new user or update existing user in DynamoDB"""
    users_table = dynamodb.Table(USERS_TABLE)
    
    user_data = {
        'user_id': user_info['user_id'],
        'email': user_info['email'],
        'name': user_info['name'],
        'picture': user_info['picture'],
        'email_verified': user_info['email_verified'],
        'updated_at': datetime.utcnow().isoformat(),
        'subscription_tier': 'free',
        'preferences': {
            'risk_tolerance': 'moderate',
            'investment_goals': [],
            'notifications_enabled': True,
            'theme': 'light'
        }
    }
    
    # Check if user exists
    try:
        response = users_table.get_item(Key={'user_id': user_info['user_id']})
        if 'Item' in response:
            # User exists, preserve certain fields
            existing_user = response['Item']
            user_data['created_at'] = existing_user.get('created_at', user_data['updated_at'])
            user_data['subscription_tier'] = existing_user.get('subscription_tier', 'free')
            user_data['preferences'] = existing_user.get('preferences', user_data['preferences'])
        else:
            # New user
            user_data['created_at'] = user_data['updated_at']
            log_security_event('new_user_created', user_id=user_info['user_id'], success=True)
    except Exception as e:
        logger.error(f"Error checking existing user: {str(e)}")
        user_data['created_at'] = user_data['updated_at']
    
    # Save user
    users_table.put_item(Item=user_data)
    
    return user_data

def create_user_session(user_id, email):
    """Create a new user session"""
    sessions_table = dynamodb.Table(SESSIONS_TABLE)
    
    session_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=7)  # 7 day expiration
    
    session_data = {
        'session_id': session_id,
        'user_id': user_id,
        'email': email,
        'created_at': datetime.utcnow().isoformat(),
        'expires_at': int(expires_at.timestamp()),  # Unix timestamp for TTL
        'last_activity': datetime.utcnow().isoformat(),
        'ip_address': None,  # Can be populated from API Gateway context
        'user_agent': None   # Can be populated from headers
    }
    
    sessions_table.put_item(Item=session_data)
    
    return session_data

def generate_jwt_token(user_id, session_id, jwt_secret):
    """Generate JWT token for authenticated user"""
    payload = {
        'user_id': user_id,
        'session_id': session_id,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(days=7)
    }
    
    return jwt.encode(payload, jwt_secret, algorithm='HS256')
```

### Requirements for Auth Lambda Functions

```txt
# lambda-auth/auth-verify/requirements.txt
google-auth==2.23.4
google-auth-oauthlib==1.1.0
google-auth-httplib2==0.1.1
PyJWT==2.8.0
boto3==1.34.0

# lambda-auth/jwt-authorizer/requirements.txt
PyJWT==2.8.0
boto3==1.34.0
```

---

## Phase 4C: WebSocket Authentication Integration

### Updated WebSocket API Configuration (websocket-api-auth.tf)

```terraform
# Phase 4: WebSocket API Authentication Updates
# ============================================

# Update the existing WebSocket API routes to use JWT authorization

# JWT Authorizer for WebSocket API
resource "aws_apigatewayv2_authorizer" "websocket_jwt_authorizer" {
  api_id                            = aws_apigatewayv2_api.chat_websocket_api.id
  authorizer_type                   = "REQUEST"
  authorizer_uri                    = aws_lambda_function.jwt_authorizer.invoke_arn
  identity_sources                  = ["route.request.querystring.token"]
  name                             = "${var.project_name}-${var.environment}-websocket-jwt-auth"
  authorizer_payload_format_version = "2.0"
  enable_simple_responses          = true

  authorizer_result_ttl_in_seconds = 300  # Cache auth results for 5 minutes
}

# Lambda permission for WebSocket API to invoke authorizer
resource "aws_lambda_permission" "websocket_api_authorizer" {
  statement_id  = "AllowWebSocketAPIInvokeAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.jwt_authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.chat_websocket_api.execution_arn}/*/*"
}

# Update $connect route to use JWT authorization
resource "aws_apigatewayv2_route" "websocket_connect_route_auth" {
  api_id    = aws_apigatewayv2_api.chat_websocket_api.id
  route_key = "$connect"
  target    = "integrations/${aws_apigatewayv2_integration.websocket_connect_integration.id}"

  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.websocket_jwt_authorizer.id
}

# Update the WebSocket connect Lambda to handle authenticated connections
resource "aws_lambda_function" "websocket_connect_auth" {
  filename         = data.archive_file.websocket_connect_zip.output_path
  function_name    = aws_lambda_function.websocket_connect.function_name
  role            = aws_iam_role.websocket_lambda_role.arn
  handler         = "lambda_function.lambda_handler"
  runtime         = "python3.11"
  timeout         = 30
  memory_size     = 512
  source_code_hash = data.archive_file.websocket_connect_zip.output_base64sha256

  environment {
    variables = merge(
      aws_lambda_function.websocket_connect.environment[0].variables,
      {
        AUTH_ENABLED = "true"
        USERS_TABLE  = aws_dynamodb_table.users.name
      }
    )
  }
}
```

### Updated WebSocket Connect Handler with Authentication

```python
# backend/src/websocket_connect.py - Updated version with authentication

import json
import os
import boto3
import logging
from datetime import datetime
import uuid

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
connections_table = dynamodb.Table(os.environ['CONNECTIONS_TABLE'])
sessions_table = dynamodb.Table(os.environ['CHAT_SESSIONS_TABLE'])
users_table = dynamodb.Table(os.environ.get('USERS_TABLE'))
security_events_table = dynamodb.Table(os.environ.get('SECURITY_EVENTS_TABLE'))

AUTH_ENABLED = os.environ.get('AUTH_ENABLED', 'false').lower() == 'true'

def log_security_event(event_type, connection_id, user_id=None, details=None):
    """Log security events for WebSocket connections"""
    if not security_events_table:
        return
        
    try:
        event_id = f"ws_{event_type}_{int(datetime.utcnow().timestamp() * 1000)}"
        security_events_table.put_item(
            Item={
                'event_id': event_id,
                'timestamp': int(datetime.utcnow().timestamp() * 1000),
                'event_type': f'websocket_{event_type}',
                'connection_id': connection_id,
                'user_id': user_id,
                'details': details or {},
                'ttl': int(datetime.utcnow().timestamp()) + (90 * 24 * 60 * 60)
            }
        )
    except Exception as e:
        logger.error(f"Error logging security event: {str(e)}")

def lambda_handler(event, context):
    """
    Handle WebSocket $connect route with authentication
    """
    connection_id = event['requestContext']['connectionId']
    domain_name = event['requestContext']['domainName']
    stage = event['requestContext']['stage']
    
    try:
        # Extract authentication information from authorizer context
        user_id = None
        session_id = None
        user_email = None
        subscription_tier = 'free'
        
        if AUTH_ENABLED and 'authorizer' in event['requestContext']:
            auth_context = event['requestContext']['authorizer']
            user_id = auth_context.get('user_id')
            session_id = auth_context.get('session_id')
            user_email = auth_context.get('email')
            subscription_tier = auth_context.get('subscription_tier', 'free')
            
            if not user_id:
                logger.error("No user_id in authorizer context")
                log_security_event('connect_auth_failed', connection_id, 
                                 details={'error': 'No user_id in context'})
                return {
                    'statusCode': 401,
                    'body': json.dumps({'error': 'Unauthorized'})
                }
        
        # Get query parameters
        query_params = event.get('queryStringParameters', {}) or {}
        
        # For backward compatibility, allow user_id from query params if auth is disabled
        if not AUTH_ENABLED and not user_id:
            user_id = query_params.get('user_id')
            if not user_id:
                user_id = f"anonymous_{uuid.uuid4().hex[:8]}"
        
        # Create or get chat session
        chat_session_id = query_params.get('session_id')
        
        if not chat_session_id:
            # Create new chat session
            chat_session_id = str(uuid.uuid4())
            sessions_table.put_item(
                Item={
                    'session_id': chat_session_id,
                    'user_id': user_id,
                    'created_at': datetime.utcnow().isoformat(),
                    'last_activity': datetime.utcnow().isoformat(),
                    'connection_id': connection_id,
                    'message_count': 0,
                    'subscription_tier': subscription_tier
                }
            )
            logger.info(f"Created new chat session: {chat_session_id}")
        else:
            # Verify session belongs to user if auth is enabled
            if AUTH_ENABLED:
                try:
                    session_response = sessions_table.get_item(
                        Key={'session_id': chat_session_id}
                    )
                    if 'Item' in session_response:
                        session_user_id = session_response['Item'].get('user_id')
                        if session_user_id != user_id:
                            logger.error(f"Session {chat_session_id} does not belong to user {user_id}")
                            log_security_event('connect_session_mismatch', connection_id, 
                                             user_id=user_id,
                                             details={'session_id': chat_session_id})
                            return {
                                'statusCode': 403,
                                'body': json.dumps({'error': 'Session access denied'})
                            }
                except Exception as e:
                    logger.error(f"Error verifying session: {str(e)}")
        
        # Store connection information with authentication details
        connection_item = {
            'connection_id': connection_id,
            'user_id': user_id,
            'session_id': chat_session_id,
            'connected_at': datetime.utcnow().isoformat(),
            'last_activity': datetime.utcnow().isoformat(),
            'endpoint': f"https://{domain_name}/{stage}",
            'status': 'connected',
            'subscription_tier': subscription_tier
        }
        
        if AUTH_ENABLED:
            connection_item.update({
                'auth_session_id': session_id,
                'user_email': user_email,
                'authenticated': True
            })
        
        connections_table.put_item(Item=connection_item)
        
        # Log successful connection
        logger.info(f"WebSocket connected: {connection_id} for user: {user_id}")
        log_security_event('connect_success', connection_id, user_id=user_id,
                         details={'session_id': chat_session_id, 'authenticated': AUTH_ENABLED})
        
        # Send welcome message
        apigw_management = boto3.client(
            'apigatewaymanagementapi',
            endpoint_url=f"https://{domain_name}/{stage}"
        )
        
        welcome_message = {
            'type': 'connection',
            'status': 'connected',
            'connection_id': connection_id,
            'session_id': chat_session_id,
            'user_id': user_id,
            'authenticated': AUTH_ENABLED,
            'subscription_tier': subscription_tier,
            'message': f"Welcome to {os.environ.get('PROJECT_NAME', 'Buffett Chat')}! You are now connected.",
            'timestamp': datetime.utcnow().isoformat()
        }
        
        try:
            apigw_management.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps(welcome_message)
            )
        except Exception as e:
            logger.error(f"Error sending welcome message: {str(e)}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Connected successfully',
                'connection_id': connection_id,
                'session_id': chat_session_id
            })
        }
        
    except Exception as e:
        logger.error(f"Error in connect handler: {str(e)}")
        log_security_event('connect_error', connection_id, 
                         details={'error': str(e)})
        
        # Clean up connection if it was created
        try:
            connections_table.delete_item(
                Key={'connection_id': connection_id}
            )
        except:
            pass
        
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }
```

---

## Phase 4D: Input Validation & Sanitization

### Input Validation Lambda Layer (lambda-auth/validation-layer/validation.py)

```python
import re
import json
import html
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger()

class InputValidator:
    """Comprehensive input validation and sanitization for chat messages"""
    
    # Validation rules
    MAX_MESSAGE_LENGTH = 4000
    MAX_SESSION_ID_LENGTH = 128
    MAX_USER_ID_LENGTH = 128
    MAX_MESSAGE_ID_LENGTH = 128
    
    # Regex patterns for validation
    PATTERNS = {
        'session_id': re.compile(r'^[a-zA-Z0-9\-_]{1,128}$'),
        'user_id': re.compile(r'^[a-zA-Z0-9\-_@.]{1,128}$'),
        'message_id': re.compile(r'^[a-zA-Z0-9\-_]{1,128}$'),
        'email': re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'),
        'url': re.compile(r'^https?://[^\s<>"{}|\\^`\[\]]+$'),
        'alphanumeric': re.compile(r'^[a-zA-Z0-9\s\-_]+$'),
    }
    
    # Dangerous patterns to block
    DANGEROUS_PATTERNS = [
        re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),
        re.compile(r'javascript:', re.IGNORECASE),
        re.compile(r'on\w+\s*=', re.IGNORECASE),  # Event handlers
        re.compile(r'<iframe[^>]*>', re.IGNORECASE),
        re.compile(r'<object[^>]*>', re.IGNORECASE),
        re.compile(r'<embed[^>]*>', re.IGNORECASE),
        re.compile(r'<link[^>]*>', re.IGNORECASE),
        re.compile(r'<meta[^>]*>', re.IGNORECASE),
    ]
    
    # SQL injection patterns
    SQL_INJECTION_PATTERNS = [
        re.compile(r"('\s*(OR|AND)\s*'?\w*'\s*=\s*')", re.IGNORECASE),
        re.compile(r'(;\s*DROP\s+TABLE)', re.IGNORECASE),
        re.compile(r'(;\s*DELETE\s+FROM)', re.IGNORECASE),
        re.compile(r'(;\s*UPDATE\s+\w+\s+SET)', re.IGNORECASE),
        re.compile(r'(UNION\s+SELECT)', re.IGNORECASE),
    ]
    
    @classmethod
    def validate_message(cls, message: str) -> Dict[str, Any]:
        """Validate and sanitize a chat message"""
        result = {
            'valid': True,
            'sanitized': message,
            'errors': [],
            'warnings': []
        }
        
        # Check message length
        if not message:
            result['valid'] = False
            result['errors'].append('Message cannot be empty')
            return result
            
        if len(message) > cls.MAX_MESSAGE_LENGTH:
            result['valid'] = False
            result['errors'].append(f'Message exceeds maximum length of {cls.MAX_MESSAGE_LENGTH} characters')
            return result
        
        # Check for dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if pattern.search(message):
                result['warnings'].append('Potentially dangerous content detected and removed')
                message = pattern.sub('', message)
        
        # Check for SQL injection attempts
        for pattern in cls.SQL_INJECTION_PATTERNS:
            if pattern.search(message):
                result['valid'] = False
                result['errors'].append('Invalid characters or patterns detected')
                logger.warning(f"SQL injection attempt detected: {pattern.pattern}")
                return result
        
        # HTML escape the message
        result['sanitized'] = html.escape(message)
        
        return result
    
    @classmethod
    def validate_session_id(cls, session_id: str) -> bool:
        """Validate session ID format"""
        if not session_id:
            return False
        return bool(cls.PATTERNS['session_id'].match(session_id))
    
    @classmethod
    def validate_user_id(cls, user_id: str) -> bool:
        """Validate user ID format"""
        if not user_id:
            return False
        return bool(cls.PATTERNS['user_id'].match(user_id))
    
    @classmethod
    def validate_email(cls, email: str) -> bool:
        """Validate email format"""
        if not email:
            return False
        return bool(cls.PATTERNS['email'].match(email.lower()))
    
    @classmethod
    def sanitize_json_input(cls, data: Dict[str, Any], allowed_fields: List[str]) -> Dict[str, Any]:
        """Sanitize JSON input by removing unexpected fields and validating values"""
        sanitized = {}
        
        for field in allowed_fields:
            if field in data:
                value = data[field]
                
                # Recursively sanitize nested dictionaries
                if isinstance(value, dict):
                    sanitized[field] = cls.sanitize_json_input(value, list(value.keys()))
                # Sanitize string values
                elif isinstance(value, str):
                    sanitized[field] = html.escape(value)
                # Keep other types as-is (numbers, booleans, etc.)
                else:
                    sanitized[field] = value
        
        return sanitized
    
    @classmethod
    def validate_action(cls, action: str, allowed_actions: List[str]) -> bool:
        """Validate WebSocket action"""
        return action in allowed_actions
    
    @classmethod
    def validate_and_sanitize_websocket_message(cls, message: Dict[str, Any]) -> Dict[str, Any]:
        """Comprehensive validation for WebSocket messages"""
        result = {
            'valid': True,
            'sanitized': {},
            'errors': []
        }
        
        # Define allowed fields and actions
        allowed_fields = ['action', 'message', 'message_id', 'session_id', 'metadata']
        allowed_actions = ['message', 'ping', 'typing', 'stop_typing']
        
        # Sanitize input
        sanitized = cls.sanitize_json_input(message, allowed_fields)
        
        # Validate action
        action = sanitized.get('action')
        if not action:
            result['valid'] = False
            result['errors'].append('Action is required')
        elif not cls.validate_action(action, allowed_actions):
            result['valid'] = False
            result['errors'].append(f'Invalid action. Allowed actions: {", ".join(allowed_actions)}')
        
        # Validate message content for 'message' action
        if action == 'message':
            message_content = sanitized.get('message')
            if not message_content:
                result['valid'] = False
                result['errors'].append('Message content is required for message action')
            else:
                message_validation = cls.validate_message(message_content)
                if not message_validation['valid']:
                    result['valid'] = False
                    result['errors'].extend(message_validation['errors'])
                else:
                    sanitized['message'] = message_validation['sanitized']
        
        # Validate message_id if provided
        message_id = sanitized.get('message_id')
        if message_id and not cls.PATTERNS['message_id'].match(str(message_id)):
            result['valid'] = False
            result['errors'].append('Invalid message_id format')
        
        result['sanitized'] = sanitized
        return result

# Export for use in Lambda functions
def validate_input(event_type: str, data: Any) -> Dict[str, Any]:
    """Main validation function for Lambda handlers"""
    
    if event_type == 'websocket_message':
        return InputValidator.validate_and_sanitize_websocket_message(data)
    elif event_type == 'chat_message':
        return InputValidator.validate_message(data)
    elif event_type == 'session_id':
        return {
            'valid': InputValidator.validate_session_id(data),
            'sanitized': data if InputValidator.validate_session_id(data) else None,
            'errors': [] if InputValidator.validate_session_id(data) else ['Invalid session ID format']
        }
    elif event_type == 'user_id':
        return {
            'valid': InputValidator.validate_user_id(data),
            'sanitized': data if InputValidator.validate_user_id(data) else None,
            'errors': [] if InputValidator.validate_user_id(data) else ['Invalid user ID format']
        }
    elif event_type == 'email':
        return {
            'valid': InputValidator.validate_email(data),
            'sanitized': data.lower() if InputValidator.validate_email(data) else None,
            'errors': [] if InputValidator.validate_email(data) else ['Invalid email format']
        }
    else:
        return {
            'valid': False,
            'sanitized': None,
            'errors': [f'Unknown validation type: {event_type}']
        }
```

### Updated WebSocket Message Handler with Validation

```python
# backend/src/websocket_message.py - Updated with input validation

import json
import os
import boto3
import logging
from datetime import datetime
import sys

# Add validation layer to path
sys.path.append('/opt')
from validation import validate_input

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ... (existing imports and setup)

def lambda_handler(event, context):
    """
    Handle WebSocket message route with input validation
    """
    connection_id = event['requestContext']['connectionId']
    domain_name = event['requestContext']['domainName']
    stage = event['requestContext']['stage']
    
    try:
        # Parse and validate the incoming message
        body = json.loads(event.get('body', '{}'))
        
        # Validate and sanitize input
        validation_result = validate_input('websocket_message', body)
        
        if not validation_result['valid']:
            logger.warning(f"Invalid message from {connection_id}: {validation_result['errors']}")
            
            # Send error response
            error_response = {
                'type': 'error',
                'error': 'Invalid message format',
                'details': validation_result['errors'],
                'timestamp': datetime.utcnow().isoformat()
            }
            
            apigw_management = boto3.client(
                'apigatewaymanagementapi',
                endpoint_url=f"https://{domain_name}/{stage}"
            )
            
            apigw_management.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps(error_response)
            )
            
            return {'statusCode': 400}
        
        # Use sanitized input
        body = validation_result['sanitized']
        action = body.get('action')
        
        # ... (rest of the handler logic with sanitized input)
```

---

## Phase 4E: WAF Configuration

### WAF Configuration (security/waf.tf)

```terraform
# Phase 4: AWS WAF Configuration
# ==============================

# WAF Web ACL for API Gateway protection
resource "aws_wafv2_web_acl" "api_protection" {
  name  = "${var.project_name}-${var.environment}-api-protection"
  scope = "REGIONAL"
  
  default_action {
    allow {}
  }
  
  # Rate limiting rule
  rule {
    name     = "RateLimitRule"
    priority = 1
    
    action {
      block {}
    }
    
    statement {
      rate_based_statement {
        limit              = var.environment == "prod" ? 2000 : 500
        aggregate_key_type = "IP"
        
        scope_down_statement {
          not_statement {
            statement {
              ip_set_reference_statement {
                arn = aws_wafv2_ip_set.allowed_ips.arn
              }
            }
          }
        }
      }
    }
    
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-rate-limit"
      sampled_requests_enabled   = true
    }
  }
  
  # Geo-blocking rule (optional)
  rule {
    name     = "GeoBlockingRule"
    priority = 2
    
    action {
      block {}
    }
    
    statement {
      geo_match_statement {
        country_codes = var.blocked_countries  # e.g., ["CN", "RU", "KP"]
      }
    }
    
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-geo-block"
      sampled_requests_enabled   = true
    }
  }
  
  # SQL injection protection
  rule {
    name     = "SQLInjectionRule"
    priority = 3
    
    action {
      block {}
    }
    
    statement {
      or_statement {
        statement {
          sqli_match_statement {
            field_to_match {
              body {}
            }
            text_transformation {
              priority = 1
              type     = "URL_DECODE"
            }
            text_transformation {
              priority = 2
              type     = "HTML_ENTITY_DECODE"
            }
          }
        }
        statement {
          sqli_match_statement {
            field_to_match {
              single_header {
                name = "authorization"
              }
            }
            text_transformation {
              priority = 1
              type     = "URL_DECODE"
            }
          }
        }
      }
    }
    
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-sql-injection"
      sampled_requests_enabled   = true
    }
  }
  
  # XSS protection
  rule {
    name     = "XSSProtectionRule"
    priority = 4
    
    action {
      block {}
    }
    
    statement {
      xss_match_statement {
        field_to_match {
          body {}
        }
        text_transformation {
          priority = 1
          type     = "URL_DECODE"
        }
        text_transformation {
          priority = 2
          type     = "HTML_ENTITY_DECODE"
        }
      }
    }
    
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-xss-protection"
      sampled_requests_enabled   = true
    }
  }
  
  # Size constraint rule
  rule {
    name     = "SizeConstraintRule"
    priority = 5
    
    action {
      block {}
    }
    
    statement {
      size_constraint_statement {
        field_to_match {
          body {}
        }
        comparison_operator = "GT"
        size                = 8192  # 8KB limit
        text_transformation {
          priority = 1
          type     = "NONE"
        }
      }
    }
    
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-size-constraint"
      sampled_requests_enabled   = true
    }
  }
  
  # AWS Managed Rules - Core Rule Set
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 10
    
    override_action {
      none {}
    }
    
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
        
        # Exclude specific rules if needed
        excluded_rule {
          name = "SizeRestrictions_BODY"
        }
      }
    }
    
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-common-rules"
      sampled_requests_enabled   = true
    }
  }
  
  # AWS Managed Rules - Known Bad Inputs
  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 11
    
    override_action {
      none {}
    }
    
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }
    
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-bad-inputs"
      sampled_requests_enabled   = true
    }
  }
  
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.project_name}-waf"
    sampled_requests_enabled   = true
  }
  
  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-waf"
    Purpose = "API Gateway protection"
    Phase   = "Phase 4"
  })
}

# IP set for allowed IPs (optional whitelist)
resource "aws_wafv2_ip_set" "allowed_ips" {
  name               = "${var.project_name}-${var.environment}-allowed-ips"
  scope              = "REGIONAL"
  ip_address_version = "IPV4"
  addresses          = var.allowed_ip_addresses  # Define in variables
  
  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-allowed-ips"
    Purpose = "Whitelisted IP addresses"
    Phase   = "Phase 4"
  })
}

# Associate WAF with HTTP API Gateway
resource "aws_wafv2_web_acl_association" "http_api_waf" {
  resource_arn = aws_apigatewayv2_stage.chat_http_stage.arn
  web_acl_arn  = aws_wafv2_web_acl.api_protection.arn
}

# Associate WAF with WebSocket API Gateway
resource "aws_wafv2_web_acl_association" "websocket_api_waf" {
  resource_arn = aws_apigatewayv2_stage.chat_websocket_stage.arn
  web_acl_arn  = aws_wafv2_web_acl.api_protection.arn
}

# WAF logging configuration
resource "aws_cloudwatch_log_group" "waf_logs" {
  name              = "/aws/wafv2/${var.project_name}-${var.environment}"
  retention_in_days = var.log_retention_days
  
  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-waf-logs"
    Purpose = "WAF request logs"
    Phase   = "Phase 4"
  })
}

resource "aws_wafv2_web_acl_logging_configuration" "waf_logging" {
  resource_arn            = aws_wafv2_web_acl.api_protection.arn
  log_destination_configs = [aws_cloudwatch_log_group.waf_logs.arn]
  
  redacted_fields {
    single_header {
      name = "authorization"
    }
  }
  
  redacted_fields {
    single_header {
      name = "cookie"
    }
  }
}
```

---

## Phase 4F: Security Monitoring & Alerting

### Security Monitoring Configuration (security/security-monitoring.tf)

```terraform
# Phase 4: Security Monitoring and Alerting
# ========================================

# SNS Topic for Security Alerts
resource "aws_sns_topic" "security_alerts" {
  name = "${var.project_name}-${var.environment}-security-alerts"
  
  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-security-alerts"
    Purpose = "Security incident notifications"
    Phase   = "Phase 4"
  })
}

resource "aws_sns_topic_subscription" "security_alerts_email" {
  topic_arn = aws_sns_topic.security_alerts.arn
  protocol  = "email"
  endpoint  = var.security_alert_email
}

# CloudWatch Metric Filters for Security Events

# Failed authentication attempts
resource "aws_cloudwatch_log_metric_filter" "auth_failures" {
  name           = "${var.project_name}-${var.environment}-auth-failures"
  log_group_name = aws_cloudwatch_log_group.auth_verify_logs.name
  pattern        = "[timestamp, request_id, level=ERROR, message, error_type=auth_failed, ...]"
  
  metric_transformation {
    name      = "AuthenticationFailures"
    namespace = "${var.project_name}/Security"
    value     = "1"
    
    dimensions = {
      Environment = var.environment
    }
  }
}

# SQL injection attempts
resource "aws_cloudwatch_log_metric_filter" "sql_injection_attempts" {
  name           = "${var.project_name}-${var.environment}-sql-injection"
  log_group_name = aws_cloudwatch_log_group.waf_logs.name
  pattern        = "{ $.ruleId = \"SQLInjectionRule\" && $.action = \"BLOCK\" }"
  
  metric_transformation {
    name      = "SQLInjectionAttempts"
    namespace = "${var.project_name}/Security"
    value     = "1"
    
    dimensions = {
      Environment = var.environment
    }
  }
}

# XSS attempts
resource "aws_cloudwatch_log_metric_filter" "xss_attempts" {
  name           = "${var.project_name}-${var.environment}-xss-attempts"
  log_group_name = aws_cloudwatch_log_group.waf_logs.name
  pattern        = "{ $.ruleId = \"XSSProtectionRule\" && $.action = \"BLOCK\" }"
  
  metric_transformation {
    name      = "XSSAttempts"
    namespace = "${var.project_name}/Security"
    value     = "1"
    
    dimensions = {
      Environment = var.environment
    }
  }
}

# Rate limit violations
resource "aws_cloudwatch_log_metric_filter" "rate_limit_violations" {
  name           = "${var.project_name}-${var.environment}-rate-limits"
  log_group_name = aws_cloudwatch_log_group.waf_logs.name
  pattern        = "{ $.ruleId = \"RateLimitRule\" && $.action = \"BLOCK\" }"
  
  metric_transformation {
    name      = "RateLimitViolations"
    namespace = "${var.project_name}/Security"
    value     = "1"
    
    dimensions = {
      Environment = var.environment
    }
  }
}

# CloudWatch Alarms

# High rate of authentication failures
resource "aws_cloudwatch_metric_alarm" "high_auth_failures" {
  alarm_name          = "${var.project_name}-${var.environment}-high-auth-failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "AuthenticationFailures"
  namespace           = "${var.project_name}/Security"
  period              = "300"
  statistic           = "Sum"
  threshold           = "10"
  alarm_description   = "High rate of authentication failures detected"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]
  
  dimensions = {
    Environment = var.environment
  }
  
  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-high-auth-failures-alarm"
    Purpose = "Security monitoring"
    Phase   = "Phase 4"
  })
}

# SQL injection detection
resource "aws_cloudwatch_metric_alarm" "sql_injection_alarm" {
  alarm_name          = "${var.project_name}-${var.environment}-sql-injection-detected"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "SQLInjectionAttempts"
  namespace           = "${var.project_name}/Security"
  period              = "60"
  statistic           = "Sum"
  threshold           = "0"
  alarm_description   = "SQL injection attempt detected"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]
  treat_missing_data  = "notBreaching"
  
  dimensions = {
    Environment = var.environment
  }
  
  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-sql-injection-alarm"
    Purpose = "Security monitoring"
    Phase   = "Phase 4"
  })
}

# XSS detection
resource "aws_cloudwatch_metric_alarm" "xss_alarm" {
  alarm_name          = "${var.project_name}-${var.environment}-xss-detected"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "XSSAttempts"
  namespace           = "${var.project_name}/Security"
  period              = "60"
  statistic           = "Sum"
  threshold           = "0"
  alarm_description   = "XSS attempt detected"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]
  treat_missing_data  = "notBreaching"
  
  dimensions = {
    Environment = var.environment
  }
  
  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-xss-alarm"
    Purpose = "Security monitoring"
    Phase   = "Phase 4"
  })
}

# DDoS/Rate limit alarm
resource "aws_cloudwatch_metric_alarm" "rate_limit_alarm" {
  alarm_name          = "${var.project_name}-${var.environment}-rate-limit-violations"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "RateLimitViolations"
  namespace           = "${var.project_name}/Security"
  period              = "300"
  statistic           = "Sum"
  threshold           = "100"
  alarm_description   = "High rate of rate limit violations detected"
  alarm_actions       = [aws_sns_topic.security_alerts.arn]
  
  dimensions = {
    Environment = var.environment
  }
  
  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-rate-limit-alarm"
    Purpose = "Security monitoring"
    Phase   = "Phase 4"
  })
}

# Security Dashboard
resource "aws_cloudwatch_dashboard" "security_dashboard" {
  dashboard_name = "${var.project_name}-${var.environment}-security"
  
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["${var.project_name}/Security", "AuthenticationFailures", { stat = "Sum" }],
            [".", "SQLInjectionAttempts", { stat = "Sum" }],
            [".", "XSSAttempts", { stat = "Sum" }],
            [".", "RateLimitViolations", { stat = "Sum" }]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "Security Events"
        }
      },
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/WAF", "BlockedRequests", { stat = "Sum" }],
            [".", "AllowedRequests", { stat = "Sum" }]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "WAF Activity"
        }
      }
    ]
  })
}
```

---

## Phase 4G: Testing & Validation

### Security Test Suite

```python
# tests/test_security.py

import pytest
import json
import jwt
import time
from datetime import datetime, timedelta
import requests
from typing import Dict, Any

class TestSecurityImplementation:
    """Comprehensive security testing for Phase 4"""
    
    def __init__(self, config: Dict[str, Any]):
        self.api_url = config['api_url']
        self.websocket_url = config['websocket_url']
        self.google_client_id = config['google_client_id']
        self.test_jwt_secret = config['test_jwt_secret']
    
    def test_google_oauth_flow(self):
        """Test Google OAuth authentication flow"""
        # This would typically use a test Google account
        # For automated testing, you might mock the Google response
        
        mock_google_token = "mock_google_token_for_testing"
        
        response = requests.post(
            f"{self.api_url}/auth/google",
            json={"token": mock_google_token},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert "session" in data
        
        # Verify JWT structure
        decoded = jwt.decode(data["token"], options={"verify_signature": False})
        assert "user_id" in decoded
        assert "session_id" in decoded
        assert "exp" in decoded
    
    def test_jwt_authorization(self):
        """Test JWT authorization for protected endpoints"""
        # Generate a valid JWT
        valid_token = self._generate_test_jwt(valid=True)
        
        # Test with valid token
        response = requests.get(
            f"{self.api_url}/protected/endpoint",
            headers={"Authorization": f"Bearer {valid_token}"}
        )
        assert response.status_code == 200
        
        # Test with invalid token
        invalid_token = "invalid.jwt.token"
        response = requests.get(
            f"{self.api_url}/protected/endpoint",
            headers={"Authorization": f"Bearer {invalid_token}"}
        )
        assert response.status_code == 401
        
        # Test with expired token
        expired_token = self._generate_test_jwt(expired=True)
        response = requests.get(
            f"{self.api_url}/protected/endpoint",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == 401
    
    def test_input_validation(self):
        """Test input validation and sanitization"""
        test_cases = [
            # XSS attempts
            {
                "message": "<script>alert('xss')</script>Hello",
                "expected_sanitized": "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;Hello"
            },
            # SQL injection attempts
            {
                "message": "'; DROP TABLE users; --",
                "should_fail": True
            },
            # Message length
            {
                "message": "x" * 5000,  # Exceeds 4000 char limit
                "should_fail": True
            },
            # Valid message
            {
                "message": "What's Warren Buffett's advice on value investing?",
                "should_pass": True
            }
        ]
        
        for test_case in test_cases:
            response = self._send_chat_message(test_case["message"])
            
            if test_case.get("should_fail"):
                assert response["status"] == "error"
            elif test_case.get("should_pass"):
                assert response["status"] == "success"
            else:
                assert response["sanitized"] == test_case["expected_sanitized"]
    
    def test_waf_protection(self):
        """Test WAF rules and protection"""
        # Test rate limiting
        for i in range(100):  # Send many requests quickly
            response = requests.get(f"{self.api_url}/test")
            if response.status_code == 429:  # Rate limited
                print(f"Rate limited after {i} requests")
                break
        
        # Test SQL injection blocking
        sql_injection_payload = {
            "query": "' OR '1'='1"
        }
        response = requests.post(
            f"{self.api_url}/search",
            json=sql_injection_payload
        )
        assert response.status_code in [400, 403]  # Blocked by WAF
        
        # Test XSS blocking
        xss_payload = {
            "content": "<img src=x onerror=alert('xss')>"
        }
        response = requests.post(
            f"{self.api_url}/submit",
            json=xss_payload
        )
        assert response.status_code in [400, 403]  # Blocked by WAF
    
    def test_websocket_authentication(self):
        """Test WebSocket connection with authentication"""
        import websocket
        
        # Test connection without token (should fail)
        try:
            ws = websocket.WebSocket()
            ws.connect(f"{self.websocket_url}")
            assert False, "Connection should have failed without auth"
        except Exception as e:
            assert "401" in str(e) or "Unauthorized" in str(e)
        
        # Test connection with valid token
        valid_token = self._generate_test_jwt(valid=True)
        ws = websocket.WebSocket()
        ws.connect(f"{self.websocket_url}?token={valid_token}")
        
        # Should receive welcome message
        welcome = json.loads(ws.recv())
        assert welcome["type"] == "connection"
        assert welcome["authenticated"] == True
        
        ws.close()
    
    def test_security_monitoring(self):
        """Test security event logging and monitoring"""
        # Trigger various security events
        events_to_trigger = [
            # Failed authentication
            {"action": "auth_fail", "expected_log": "auth_failed"},
            # SQL injection attempt
            {"action": "sql_inject", "expected_log": "sql_injection_blocked"},
            # XSS attempt
            {"action": "xss_attempt", "expected_log": "xss_blocked"},
            # Rate limit violation
            {"action": "rate_limit", "expected_log": "rate_limit_exceeded"}
        ]
        
        for event in events_to_trigger:
            # Trigger the event
            self._trigger_security_event(event["action"])
            
            # Verify it was logged (this would check CloudWatch/DynamoDB)
            assert self._verify_security_log(event["expected_log"])
    
    def _generate_test_jwt(self, valid=True, expired=False):
        """Generate test JWT tokens"""
        if not valid:
            return "invalid.jwt.token"
        
        payload = {
            "user_id": "test_user_123",
            "session_id": "test_session_456",
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() - timedelta(hours=1) if expired else datetime.utcnow() + timedelta(hours=1)
        }
        
        return jwt.encode(payload, self.test_jwt_secret, algorithm="HS256")
    
    def _send_chat_message(self, message: str) -> Dict[str, Any]:
        """Send a chat message through the API"""
        # Implementation would send actual API request
        pass
    
    def _trigger_security_event(self, event_type: str):
        """Trigger specific security events for testing"""
        # Implementation would trigger various security events
        pass
    
    def _verify_security_log(self, event_type: str) -> bool:
        """Verify security event was logged"""
        # Implementation would check CloudWatch logs or DynamoDB
        pass

# Test runner
if __name__ == "__main__":
    config = {
        "api_url": "https://your-api.execute-api.region.amazonaws.com/stage",
        "websocket_url": "wss://your-ws-api.execute-api.region.amazonaws.com/stage",
        "google_client_id": "your-google-client-id",
        "test_jwt_secret": "test-secret-for-jwt"
    }
    
    tester = TestSecurityImplementation(config)
    
    # Run all tests
    tester.test_google_oauth_flow()
    tester.test_jwt_authorization()
    tester.test_input_validation()
    tester.test_waf_protection()
    tester.test_websocket_authentication()
    tester.test_security_monitoring()
    
    print("All security tests passed!")
```

---

## Migration & Rollback Strategy

### Phase 4 Deployment Steps

```bash
#!/bin/bash
# deploy-phase4.sh

set -e

echo "Deploying Phase 4: Security & Authentication"

# Step 1: Deploy authentication infrastructure
cd chat-api/auth
terraform init
terraform plan -var-file=../../terraform.tfvars
terraform apply -var-file=../../terraform.tfvars -auto-approve

# Step 2: Deploy Lambda functions
cd ../lambda-auth
for dir in */; do
    cd "$dir"
    pip install -r requirements.txt -t .
    zip -r "../${dir%/}.zip" .
    cd ..
done

# Step 3: Update existing infrastructure with auth
cd ..
terraform apply -target=aws_apigatewayv2_authorizer.websocket_jwt_authorizer -auto-approve
terraform apply -target=aws_apigatewayv2_route.websocket_connect_route_auth -auto-approve

# Step 4: Deploy WAF
cd security
terraform apply -var-file=../../terraform.tfvars -auto-approve

# Step 5: Run security tests
cd ../../tests
python test_security.py

echo "Phase 4 deployment complete!"
```

### Rollback Procedure

```bash
#!/bin/bash
# rollback-phase4.sh

set -e

echo "Rolling back Phase 4 changes"

# Step 1: Remove WAF associations
cd chat-api/security
terraform destroy -target=aws_wafv2_web_acl_association.http_api_waf -auto-approve
terraform destroy -target=aws_wafv2_web_acl_association.websocket_api_waf -auto-approve

# Step 2: Revert WebSocket routes to no auth
cd ..
terraform apply -target=aws_apigatewayv2_route.websocket_connect_route -var="authorization_type=NONE" -auto-approve

# Step 3: Remove auth infrastructure (if needed)
cd auth
terraform destroy -var-file=../../terraform.tfvars -auto-approve

echo "Rollback complete!"
```

---

## Cost Analysis

### Estimated Monthly Costs

#### Development Environment
- **Lambda Functions**: ~$5/month (auth functions)
- **DynamoDB Tables**: ~$10/month (on-demand)
- **WAF**: $5/month + $0.60 per million requests
- **Secrets Manager**: $0.40 per secret/month
- **KMS**: $1/month per key
- **Total**: ~$25-30/month

#### Production Environment (100K users/month)
- **Lambda Functions**: ~$50/month
- **DynamoDB Tables**: ~$100/month (provisioned)
- **WAF**: $5/month + $60/month (request volume)
- **Secrets Manager**: $1.20/month (3 secrets)
- **KMS**: $3/month (3 keys)
- **CloudWatch**: ~$20/month
- **Total**: ~$240-250/month

### Cost Optimization Strategies

1. **Use DynamoDB On-Demand** for unpredictable traffic
2. **Implement caching** for JWT validation (5-minute TTL)
3. **Use Lambda Reserved Concurrency** only for critical functions
4. **Enable WAF rate limiting** to prevent abuse
5. **Set appropriate log retention** periods

---

## Security Best Practices Checklist

### Authentication & Authorization
- ✅ Google OAuth 2.0 implementation
- ✅ JWT token generation and validation
- ✅ Session management with TTL
- ✅ WebSocket authentication integration
- ✅ Secure token storage in Secrets Manager

### Input Validation & Sanitization
- ✅ Message content validation
- ✅ XSS protection
- ✅ SQL injection prevention
- ✅ Size constraints
- ✅ Format validation for IDs

### Infrastructure Security
- ✅ WAF protection for APIs
- ✅ Rate limiting
- ✅ DDoS protection
- ✅ Encryption at rest (KMS)
- ✅ Encryption in transit (TLS)

### Monitoring & Alerting
- ✅ Security event logging
- ✅ CloudWatch metrics and alarms
- ✅ SNS notifications for incidents
- ✅ Security dashboard
- ✅ Audit trail in DynamoDB

### Compliance & Privacy
- ✅ PII data protection
- ✅ GDPR considerations
- ✅ Data retention policies
- ✅ User consent handling
- ✅ Right to deletion support

---

## Conclusion

Phase 4 successfully implements a comprehensive security and authentication system using Google OAuth 2.0, providing enterprise-grade protection while maintaining simplicity and cost-effectiveness. The implementation includes:

1. **Robust Authentication**: Google OAuth with JWT tokens
2. **Authorization**: Custom JWT authorizer for all APIs
3. **Input Validation**: Comprehensive sanitization layer
4. **WAF Protection**: Advanced threat protection
5. **Security Monitoring**: Real-time alerting and logging

The system is designed to scale from development to production environments with minimal changes, and includes comprehensive testing and rollback procedures to ensure safe deployment.

### Next Steps

1. Deploy Phase 4 to staging environment
2. Conduct security penetration testing
3. Train team on security monitoring procedures
4. Plan migration path to AWS Cognito for future scaling
5. Implement additional security features as needed

For questions or issues during implementation, refer to the troubleshooting guide in the Google OAuth Implementation Guide or contact the architecture team.
