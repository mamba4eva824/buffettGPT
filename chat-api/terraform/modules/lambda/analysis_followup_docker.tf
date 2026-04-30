# ============================================================================
# Analysis Follow-up Lambda - ECR Container Deployment
# Docker-based deployment for SSE streaming via FastAPI + Lambda Web Adapter
# Python zip runtime cannot serialize generators for RESPONSE_STREAM,
# so token-by-token streaming requires the LWA pattern.
# ============================================================================
# Gated by var.create_analysis_followup_docker. When false, the legacy zip
# Lambda in main.tf (lambda_configs) + function_urls.tf is used instead.
# ============================================================================

# ============================================================================
# ECR Repository
# ============================================================================

resource "aws_ecr_repository" "analysis_followup" {
  count                = var.create_analysis_followup_docker ? 1 : 0
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
    Service = "followup-chat-streaming"
  })
}

# ECR Repository Policy - Allow Lambda service to pull images
resource "aws_ecr_repository_policy" "analysis_followup" {
  count      = var.create_analysis_followup_docker ? 1 : 0
  repository = aws_ecr_repository.analysis_followup[0].name

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
  count      = var.create_analysis_followup_docker ? 1 : 0
  repository = aws_ecr_repository.analysis_followup[0].name

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
  count         = var.create_analysis_followup_docker ? 1 : 0
  function_name = "${var.project_name}-${var.environment}-analysis-followup"
  role          = var.lambda_role_arn

  publish      = true
  package_type = "Image"
  image_uri    = "${aws_ecr_repository.analysis_followup[0].repository_url}:${var.analysis_followup_image_tag}"

  timeout                        = 60
  memory_size                    = 256
  reserved_concurrent_executions = 10

  ephemeral_storage {
    size = 512
  }

  environment {
    variables = merge(
      var.common_env_vars,
      lookup(var.function_env_vars, "analysis_followup", {}),
      {
        AWS_LWA_INVOKE_MODE = "RESPONSE_STREAM"
        AWS_LWA_PORT        = "8080"
        PORT                = "8080"
      }
    )
  }

  tracing_config {
    mode = "Active"
  }

  tags = merge(var.common_tags, {
    Name    = "analysis-followup-lambda"
    Service = "followup-chat-streaming"
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
  count             = var.create_analysis_followup_docker ? 1 : 0
  name              = "/aws/lambda/${var.project_name}-${var.environment}-analysis-followup"
  retention_in_days = var.log_retention_days

  tags = merge(var.common_tags, {
    Name    = "analysis-followup-logs"
    Service = "followup-chat-streaming"
  })
}

# ============================================================================
# Lambda Function URL (direct streaming access)
# ============================================================================
# CORS allow_origins preserved literally from the current AWS state
# (localhost:3000/5173/8000) so local dev flows keep working unchanged.
# JWT is validated inside the FastAPI container.
# ============================================================================

resource "aws_lambda_function_url" "analysis_followup_docker" {
  count              = var.create_analysis_followup_docker ? 1 : 0
  function_name      = aws_lambda_function.analysis_followup_docker[0].function_name
  authorization_type = "NONE"
  invoke_mode        = "RESPONSE_STREAM"

  cors {
    allow_credentials = true
    allow_origins = [
      "http://localhost:3000",
      "http://localhost:5173",
      "http://localhost:8000",
    ]
    allow_methods  = ["POST"]
    allow_headers  = ["content-type", "authorization"]
    expose_headers = ["content-type"]
    max_age        = 86400
  }
}
