# S3 Module - Models Bucket for ML Models
# Stores XGBoost ensemble models for financial analysis

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# S3 bucket for ML models
resource "aws_s3_bucket" "models" {
  bucket = "${var.project_name}-${var.environment}-models"

  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-${var.environment}-models"
    Purpose = "ML model storage"
  })
}

# Enable versioning for model rollback capability
resource "aws_s3_bucket_versioning" "models" {
  bucket = aws_s3_bucket.models.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "models" {
  bucket = aws_s3_bucket.models.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Server-side encryption with AWS managed keys
resource "aws_s3_bucket_server_side_encryption_configuration" "models" {
  bucket = aws_s3_bucket.models.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}
