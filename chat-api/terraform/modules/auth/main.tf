# Auth Module - Google OAuth Authentication

locals {
  function_name = "${var.project_name}-${var.environment}-auth-callback"
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

  global_secondary_index {
    name            = "email-index"
    hash_key        = "email"
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

# Lambda Layer for Google Auth dependencies
resource "aws_lambda_layer_version" "auth_dependencies" {
  filename            = "${path.module}/layers/auth_dependencies.zip"
  layer_name          = "${var.project_name}-${var.environment}-auth-deps"
  compatible_runtimes = ["python3.11"]
  description         = "Google Auth and JWT dependencies"

  lifecycle {
    ignore_changes = [filename]
  }
}


# Auth Callback Lambda Function
resource "aws_lambda_function" "auth_callback" {
  function_name = local.function_name
  role          = var.lambda_role_arn
  handler       = "auth_callback.lambda_handler"
  runtime       = "python3.11"
  timeout       = 30
  memory_size   = 256

  filename         = "../../../../lambda-auth/auth-callback/auth_callback.zip"
  source_code_hash = filebase64sha256("../../../../lambda-auth/auth-callback/auth_callback.zip")

  layers = [aws_lambda_layer_version.auth_dependencies.arn]

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
      Name        = local.function_name
      Environment = var.environment
    }
  )
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "auth_callback" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = 7

  tags = merge(
    var.common_tags,
    {
      Name        = "${local.function_name}-logs"
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
  name        = "${local.function_name}-policy"
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