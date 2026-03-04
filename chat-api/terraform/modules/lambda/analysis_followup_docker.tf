# ============================================================================
# Analysis Follow-Up Lambda - ECR Container Deployment
# Docker-based deployment for SSE streaming via FastAPI + LWA
# Handles follow-up questions with Bedrock converse_stream + tool orchestration
# ============================================================================

# ============================================================================
# ECR Repository
# ============================================================================

resource "aws_ecr_repository" "analysis_followup" {
  name                 = "${var.project_name}/analysis-followup"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(var.common_tags, {
    Name    = "analysis-followup-ecr"
    Service = "followup-streaming"
  })
}

# ECR Repository Policy - Allow Lambda service to pull images
resource "aws_ecr_repository_policy" "analysis_followup" {
  repository = aws_ecr_repository.analysis_followup.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowLambdaPull"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
      }
    ]
  })
}

# Lifecycle policy to keep only the latest version
resource "aws_ecr_lifecycle_policy" "analysis_followup" {
  repository = aws_ecr_repository.analysis_followup.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep only the latest tagged image"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v"]
          countType     = "imageCountMoreThan"
          countNumber   = 1
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Expire untagged images older than 1 day"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ============================================================================
# Lambda Function (Container)
# ============================================================================

resource "aws_lambda_function" "analysis_followup_docker" {
  function_name = "${var.project_name}-${var.environment}-analysis-followup"
  role          = var.lambda_role_arn

  publish      = true
  package_type = "Image"
  image_uri    = "${aws_ecr_repository.analysis_followup.repository_url}:${var.analysis_followup_image_tag}"

  # Bedrock converse_stream can take time with tool orchestration
  timeout     = 60   # 60 seconds
  memory_size = 512  # 512 MB

  ephemeral_storage {
    size = 512 # MB
  }

  environment {
    variables = merge(
      var.common_env_vars,
      lookup(var.function_env_vars, "analysis_followup", {}),
      {
        # Lambda Web Adapter configuration for response streaming
        AWS_LWA_INVOKE_MODE = "RESPONSE_STREAM"
        AWS_LWA_PORT        = "8080"
        PORT                = "8080"
      }
    )
  }

  # X-Ray tracing
  tracing_config {
    mode = "Active"
  }

  tags = merge(var.common_tags, {
    Name    = "analysis-followup-lambda"
    Service = "followup-streaming"
  })

  depends_on = [
    aws_ecr_repository.analysis_followup,
    aws_cloudwatch_log_group.analysis_followup_docker
  ]

  lifecycle {
    ignore_changes = [image_uri]
  }
}

# ============================================================================
# CloudWatch Log Group
# ============================================================================

resource "aws_cloudwatch_log_group" "analysis_followup_docker" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-analysis-followup"
  retention_in_days = var.log_retention_days

  tags = merge(var.common_tags, {
    Name    = "analysis-followup-logs"
    Service = "followup-streaming"
  })
}

# ============================================================================
# Lambda Function URL (for direct SSE streaming access)
# ============================================================================
# SECURITY NOTE: authorization_type is NONE because the FastAPI container
# validates JWT independently via JWTAuthMiddleware. Direct Function URL
# access without a valid JWT returns 401.
# ============================================================================

resource "aws_lambda_function_url" "analysis_followup_docker" {
  function_name      = aws_lambda_function.analysis_followup_docker.function_name
  authorization_type = "NONE"

  cors {
    allow_credentials = true
    allow_origins     = var.cors_allowed_origins
    allow_methods     = ["POST"]
    allow_headers     = ["content-type", "authorization"]
    expose_headers    = ["content-type"]
    max_age           = 86400
  }

  invoke_mode = "RESPONSE_STREAM"
}
