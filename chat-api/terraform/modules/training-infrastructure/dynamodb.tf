# DynamoDB tables for financial data storage and model training

# Table for raw financial statements from SEC filings
resource "aws_dynamodb_table" "financial_statements_raw" {
  name           = "${var.project_name}-${var.environment}-financial-statements-raw"
  billing_mode   = var.dynamodb_billing_mode
  hash_key       = "company_ticker"
  range_key      = "statement_key"  # Format: YEAR_TYPE (e.g., 2024_10K_INCOME)

  attribute {
    name = "company_ticker"
    type = "S"
  }

  attribute {
    name = "statement_key"
    type = "S"
  }

  attribute {
    name = "filing_year"
    type = "N"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  # Global secondary index for querying by year
  global_secondary_index {
    name            = "filing_year_index"
    hash_key        = "filing_year"
    range_key       = "company_ticker"
    projection_type = "ALL"
  }

  # Global secondary index for querying by creation date
  global_secondary_index {
    name            = "created_at_index"
    hash_key        = "created_at"
    range_key       = "company_ticker"
    projection_type = "KEYS_ONLY"
  }

  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  server_side_encryption {
    enabled = var.enable_encryption
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-financial-statements-raw"
    Type        = "raw-data"
    Environment = var.environment
  })
}

# Table for verified and cleaned financial data
resource "aws_dynamodb_table" "financial_statements_verified" {
  name           = "${var.project_name}-${var.environment}-financial-statements-verified"
  billing_mode   = var.dynamodb_billing_mode
  hash_key       = "company_ticker"
  range_key      = "statement_key"

  attribute {
    name = "company_ticker"
    type = "S"
  }

  attribute {
    name = "statement_key"
    type = "S"
  }

  attribute {
    name = "verification_status"
    type = "S"
  }

  attribute {
    name = "confidence_score"
    type = "N"
  }

  attribute {
    name = "last_verified"
    type = "S"
  }

  # Index for querying by verification status
  global_secondary_index {
    name            = "verification_status_index"
    hash_key        = "verification_status"
    range_key       = "confidence_score"
    projection_type = "ALL"
  }

  # Index for querying by last verification date
  global_secondary_index {
    name            = "last_verified_index"
    hash_key        = "last_verified"
    range_key       = "company_ticker"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  server_side_encryption {
    enabled = var.enable_encryption
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-financial-statements-verified"
    Type        = "verified-data"
    Environment = var.environment
  })
}

# Table for verification audit logs
resource "aws_dynamodb_table" "verification_audit_log" {
  name           = "${var.project_name}-${var.environment}-verification-audit-log"
  billing_mode   = var.dynamodb_billing_mode
  hash_key       = "audit_id"
  range_key      = "timestamp"

  attribute {
    name = "audit_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  attribute {
    name = "company_ticker"
    type = "S"
  }

  attribute {
    name = "verification_type"
    type = "S"
  }

  # Index for querying by company
  global_secondary_index {
    name            = "company_ticker_index"
    hash_key        = "company_ticker"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  # Index for querying by verification type
  global_secondary_index {
    name            = "verification_type_index"
    hash_key        = "verification_type"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  # TTL for automatic cleanup
  ttl {
    enabled        = true
    attribute_name = "expiration_time"
  }

  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  server_side_encryption {
    enabled = var.enable_encryption
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-verification-audit-log"
    Type        = "audit-log"
    Environment = var.environment
  })
}

# Table for prepared training datasets
resource "aws_dynamodb_table" "model_training_datasets" {
  name           = "${var.project_name}-${var.environment}-model-training-datasets"
  billing_mode   = var.dynamodb_billing_mode
  hash_key       = "dataset_id"
  range_key      = "version"

  attribute {
    name = "dataset_id"
    type = "S"
  }

  attribute {
    name = "version"
    type = "S"
  }

  attribute {
    name = "model_type"
    type = "S"
  }

  attribute {
    name = "created_date"
    type = "S"
  }

  attribute {
    name = "training_status"
    type = "S"
  }

  # Index for querying by model type
  global_secondary_index {
    name            = "model_type_index"
    hash_key        = "model_type"
    range_key       = "created_date"
    projection_type = "ALL"
  }

  # Index for querying by training status
  global_secondary_index {
    name            = "training_status_index"
    hash_key        = "training_status"
    range_key       = "created_date"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  server_side_encryption {
    enabled = var.enable_encryption
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-model-training-datasets"
    Type        = "training-data"
    Environment = var.environment
  })
}

# Table for model performance metrics
resource "aws_dynamodb_table" "model_performance_metrics" {
  name           = "${var.project_name}-${var.environment}-model-performance-metrics"
  billing_mode   = var.dynamodb_billing_mode
  hash_key       = "model_id"
  range_key      = "evaluation_timestamp"

  attribute {
    name = "model_id"
    type = "S"
  }

  attribute {
    name = "evaluation_timestamp"
    type = "S"
  }

  attribute {
    name = "model_type"
    type = "S"
  }

  attribute {
    name = "accuracy_score"
    type = "N"
  }

  # Index for querying by model type
  global_secondary_index {
    name            = "model_type_performance_index"
    hash_key        = "model_type"
    range_key       = "accuracy_score"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  server_side_encryption {
    enabled = var.enable_encryption
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-model-performance-metrics"
    Type        = "metrics"
    Environment = var.environment
  })
}

# Outputs for reference in other modules
output "financial_statements_raw_table_name" {
  value = aws_dynamodb_table.financial_statements_raw.name
}

output "financial_statements_raw_table_arn" {
  value = aws_dynamodb_table.financial_statements_raw.arn
}

output "financial_statements_verified_table_name" {
  value = aws_dynamodb_table.financial_statements_verified.name
}

output "financial_statements_verified_table_arn" {
  value = aws_dynamodb_table.financial_statements_verified.arn
}

output "verification_audit_log_table_name" {
  value = aws_dynamodb_table.verification_audit_log.name
}

output "model_training_datasets_table_name" {
  value = aws_dynamodb_table.model_training_datasets.name
}

output "model_performance_metrics_table_name" {
  value = aws_dynamodb_table.model_performance_metrics.name
}