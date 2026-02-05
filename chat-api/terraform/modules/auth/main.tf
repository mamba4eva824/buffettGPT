# Auth Module - Google OAuth Authentication

locals {
  auth_callback_function_name = "${var.project_name}-${var.environment}-auth-callback"
  auth_verify_function_name   = "${var.project_name}-${var.environment}-auth-verify"
}

# DynamoDB Users Table
resource "aws_dynamodb_table" "users" {
  name         = "${var.project_name}-${var.environment}-users"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "email"
    type = "S"
  }

  attribute {
    name = "stripe_customer_id"
    type = "S"
  }

  global_secondary_index {
    name            = "email-index"
    hash_key        = "email"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "stripe-customer-index"
    hash_key        = "stripe_customer_id"
    projection_type = "ALL"
  }

  tags = merge(
    var.common_tags,
    {
      Name        = "${var.project_name}-${var.environment}-users"
      Environment = var.environment
    }
  )
}

# Lambda Layer removed - using AWS Lambda runtime dependencies

# Auth Callback Lambda Function
resource "aws_lambda_function" "auth_callback" {
  function_name = local.auth_callback_function_name
  role          = var.lambda_role_arn
  handler       = "auth_callback.lambda_handler"
  runtime       = "python3.11"
  timeout       = 30
  memory_size   = 256

  filename         = "${var.lambda_package_path}/auth_callback.zip"
  source_code_hash = filebase64sha256("${var.lambda_package_path}/auth_callback.zip")

  # Use the dependencies layer
  layers = [var.dependencies_layer_arn]

  environment {
    variables = {
      GOOGLE_OAUTH_SECRET_ARN = aws_secretsmanager_secret.google_oauth.arn
      JWT_SECRET_ARN          = aws_secretsmanager_secret.jwt_secret.arn
      USERS_TABLE             = aws_dynamodb_table.users.name
      ENVIRONMENT             = var.environment
      PROJECT_NAME            = var.project_name
    }
  }

  tags = merge(
    var.common_tags,
    {
      Name        = local.auth_callback_function_name
      Environment = var.environment
    }
  )
}

# Auth Verify Lambda Function (JWT Authorizer for WebSocket)
resource "aws_lambda_function" "auth_verify" {
  function_name = local.auth_verify_function_name
  role          = var.lambda_role_arn
  handler       = "auth_verify.lambda_handler"
  runtime       = "python3.11"
  timeout       = 30
  memory_size   = 256

  filename         = "${var.lambda_package_path}/auth_verify.zip"
  source_code_hash = filebase64sha256("${var.lambda_package_path}/auth_verify.zip")

  # Use the dependencies layer
  layers = [var.dependencies_layer_arn]

  environment {
    variables = {
      JWT_SECRET_ARN = aws_secretsmanager_secret.jwt_secret.arn
      ENVIRONMENT    = var.environment
      PROJECT_NAME   = var.project_name
    }
  }

  tags = merge(
    var.common_tags,
    {
      Name        = local.auth_verify_function_name
      Environment = var.environment
    }
  )
}

# CloudWatch Log Group for auth_verify
resource "aws_cloudwatch_log_group" "auth_verify" {
  name              = "/aws/lambda/${local.auth_verify_function_name}"
  retention_in_days = 7

  tags = merge(
    var.common_tags,
    {
      Name        = "${local.auth_verify_function_name}-logs"
      Environment = var.environment
    }
  )
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "auth_callback" {
  name              = "/aws/lambda/${local.auth_callback_function_name}"
  retention_in_days = 7

  tags = merge(
    var.common_tags,
    {
      Name        = "${local.auth_callback_function_name}-logs"
      Environment = var.environment
    }
  )
}

# Lambda Permission for API Gateway
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auth_callback.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.api_gateway_execution_arn}/*/*"
}

# IAM Policy for DynamoDB and Secrets Manager access
resource "aws_iam_policy" "auth_lambda_policy" {
  name        = "${local.auth_callback_function_name}-policy"
  description = "IAM policy for auth callback Lambda"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.users.arn,
          "${aws_dynamodb_table.users.arn}/index/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.google_oauth.arn,
          aws_secretsmanager_secret.jwt_secret.arn
        ]
      }
    ]
  })
}

# Attach policy to Lambda role
resource "aws_iam_role_policy_attachment" "auth_lambda_policy" {
  policy_arn = aws_iam_policy.auth_lambda_policy.arn
  role       = split("/", var.lambda_role_arn)[1]
}

# IAM Policy for auth_verify Lambda (Secrets Manager access only)
resource "aws_iam_policy" "auth_verify_lambda_policy" {
  name        = "${local.auth_verify_function_name}-policy"
  description = "IAM policy for auth verify Lambda"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.jwt_secret.arn
        ]
      }
    ]
  })
}

# Attach auth_verify policy to Lambda role
resource "aws_iam_role_policy_attachment" "auth_verify_lambda_policy" {
  policy_arn = aws_iam_policy.auth_verify_lambda_policy.arn
  role       = split("/", var.lambda_role_arn)[1]
}