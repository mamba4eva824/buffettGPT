# ============================================================================
# Investment Research Lambda - ECR Container Deployment
# Docker-based deployment for cached report streaming via FastAPI + LWA
# Serves v2 section-based reports from DynamoDB
# ============================================================================

# ============================================================================
# ECR Repository
# ============================================================================

resource "aws_ecr_repository" "investment_research" {
  name                 = "${var.project_name}/investment-research"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(var.common_tags, {
    Name    = "investment-research-ecr"
    Service = "report-streaming"
  })
}

# ECR Repository Policy - Allow Lambda service to pull images
resource "aws_ecr_repository_policy" "investment_research" {
  repository = aws_ecr_repository.investment_research.name

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
resource "aws_ecr_lifecycle_policy" "investment_research" {
  repository = aws_ecr_repository.investment_research.name

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

resource "aws_lambda_function" "investment_research_docker" {
  function_name = "${var.project_name}-${var.environment}-investment-research"
  role          = var.lambda_role_arn

  publish      = true
  package_type = "Image"
  image_uri    = "${aws_ecr_repository.investment_research.repository_url}:${var.investment_research_image_tag}"

  # Performance configuration (lighter than prediction_ensemble - no ML)
  timeout     = 30   # 30 seconds (just DynamoDB reads + streaming)
  memory_size = 512  # 512 MB (no ML models)

  ephemeral_storage {
    size = 512 # MB
  }

  environment {
    variables = merge(
      var.common_env_vars,
      lookup(var.function_env_vars, "investment_research", {}),
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
    Name    = "investment-research-lambda"
    Service = "report-streaming"
  })

  # Ensure image exists before deploying
  depends_on = [
    aws_ecr_repository.investment_research,
    aws_cloudwatch_log_group.investment_research_docker
  ]

  # Lifecycle to prevent replacement on version changes
  lifecycle {
    ignore_changes = [image_uri]
  }
}

# ============================================================================
# CloudWatch Log Group
# ============================================================================

resource "aws_cloudwatch_log_group" "investment_research_docker" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-investment-research"
  retention_in_days = var.log_retention_days

  tags = merge(var.common_tags, {
    Name    = "investment-research-logs"
    Service = "report-streaming"
  })
}

# ============================================================================
# Lambda Function URL (for direct streaming access)
# ============================================================================
# Function URL with RESPONSE_STREAM for Lambda Web Adapter compatibility.
# Primary access is through REST API Gateway for centralized auth.
#
# SECURITY NOTE: authorization_type is NONE because this is an HTTP_PROXY target
# for the REST API Gateway, which handles JWT auth via its TOKEN authorizer.
# The FastAPI container ALSO validates JWT independently via JWTAuthMiddleware
# (lambda/investment_research/app.py:181,353) with 32-char secret validation,
# so direct Function URL access without a valid JWT returns 401.
# See docs/api/SECURITY_REVIEW.md CRIT-2 for full analysis.
# ============================================================================

resource "aws_lambda_function_url" "investment_research_docker" {
  function_name      = aws_lambda_function.investment_research_docker.function_name
  authorization_type = "NONE"

  cors {
    allow_credentials = true
    allow_origins     = var.cors_allowed_origins
    allow_methods     = ["*"]
    allow_headers     = ["content-type", "authorization"]
    expose_headers    = ["content-type"]
    max_age           = 86400
  }

  invoke_mode = "RESPONSE_STREAM"
}

# ============================================================================
# Outputs (defined in outputs.tf)
# ============================================================================
