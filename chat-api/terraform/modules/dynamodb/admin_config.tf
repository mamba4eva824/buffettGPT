# Admin Config Table - Runtime configuration for admin dashboard
# Stores per-category settings (token_limits, rate_limits, model_config, etc.)

resource "aws_dynamodb_table" "admin_config" {
  name         = "${var.project_name}-${var.environment}-admin-config"
  billing_mode = var.billing_mode

  # Primary key
  hash_key = "config_key"

  attribute {
    name = "config_key"
    type = "S"
  }

  # Encryption at rest
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
      Name        = "${var.project_name}-${var.environment}-admin-config"
      Type        = "AdminConfig"
      Description = "Runtime configuration for admin dashboard"
    }
  )

  lifecycle {
    prevent_destroy = false
  }
}
