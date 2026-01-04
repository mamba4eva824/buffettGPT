# ============================================================================
# Prediction Ensemble Lambda - ECR Container Deployment
# Docker-based deployment for ML inference (numpy/scikit-learn dependencies)
# ============================================================================

# ============================================================================
# ECR Repository
# ============================================================================

resource "aws_ecr_repository" "prediction_ensemble" {
  name                 = "${var.project_name}/prediction-ensemble"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(var.common_tags, {
    Name    = "prediction-ensemble-ecr"
    Service = "ml-inference"
  })
}

# Lifecycle policy to keep only the latest version
# Previous versions can be restored from Docker Desktop if needed
resource "aws_ecr_lifecycle_policy" "prediction_ensemble" {
  repository = aws_ecr_repository.prediction_ensemble.name

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
          tagStatus  = "untagged"
          countType  = "sinceImagePushed"
          countUnit  = "days"
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

resource "aws_lambda_function" "prediction_ensemble_docker" {
  function_name = "${var.project_name}-${var.environment}-prediction-ensemble"
  role          = var.lambda_role_arn

  publish      = true
  package_type = "Image"
  image_uri    = "${aws_ecr_repository.prediction_ensemble.repository_url}:${var.prediction_ensemble_image_tag}"

  # Performance configuration
  timeout     = 120  # 2 minutes (model load + inference + Bedrock streaming)
  memory_size = 1024 # 1 GB

  ephemeral_storage {
    size = 512 # MB
  }

  environment {
    variables = merge(
      var.common_env_vars,
      lookup(var.function_env_vars, "prediction_ensemble", {}),
      {
        # Model configuration
        ML_MODELS_BUCKET = var.model_s3_bucket
        MODEL_S3_PREFIX  = "ensemble/v1"

        # Lambda Web Adapter configuration for response streaming
        AWS_LWA_INVOKE_MODE = "RESPONSE_STREAM"
        AWS_LWA_PORT        = "8080"
        PORT                = "8080"
        # Route Bedrock action group events to /events endpoint (BedrockAgentMiddleware)
        AWS_LWA_PASS_THROUGH_PATH = "/events"

        # Bedrock Runtime model for ConverseStream
        BEDROCK_MODEL_ID = var.bedrock_model_id
      }
    )
  }

  # X-Ray tracing
  tracing_config {
    mode = "Active"
  }

  tags = merge(var.common_tags, {
    Name    = "prediction-ensemble-lambda"
    Service = "ml-inference"
  })

  # Ensure image exists before deploying
  depends_on = [
    aws_ecr_repository.prediction_ensemble,
    aws_cloudwatch_log_group.prediction_ensemble_docker
  ]

  # Lifecycle to prevent replacement on version changes
  lifecycle {
    ignore_changes = [image_uri]
  }
}

# ============================================================================
# CloudWatch Log Group
# ============================================================================

resource "aws_cloudwatch_log_group" "prediction_ensemble_docker" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-prediction-ensemble"
  retention_in_days = var.log_retention_days

  tags = merge(var.common_tags, {
    Name    = "prediction-ensemble-logs"
    Service = "ml-inference"
  })
}

# ============================================================================
# Lambda Function URL (Backup - for direct streaming if needed)
# ============================================================================
# Function URL with RESPONSE_STREAM for Lambda Web Adapter compatibility.
# Primary access is through REST API Gateway for centralized auth.
# ============================================================================

resource "aws_lambda_function_url" "prediction_ensemble_docker" {
  function_name      = aws_lambda_function.prediction_ensemble_docker.function_name
  authorization_type = "NONE"  # JWT validation done in Lambda code

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
# Outputs
# ============================================================================

output "prediction_ensemble_docker_function_arn" {
  description = "ARN of the prediction ensemble Docker Lambda function"
  value       = aws_lambda_function.prediction_ensemble_docker.arn
}

output "prediction_ensemble_docker_function_name" {
  description = "Name of the prediction ensemble Docker Lambda function"
  value       = aws_lambda_function.prediction_ensemble_docker.function_name
}

output "prediction_ensemble_ecr_repository_url" {
  description = "URL of the prediction ensemble ECR repository"
  value       = aws_ecr_repository.prediction_ensemble.repository_url
}

output "prediction_ensemble_docker_function_url" {
  description = "Function URL for the prediction ensemble Docker Lambda"
  value       = aws_lambda_function_url.prediction_ensemble_docker.function_url
}
