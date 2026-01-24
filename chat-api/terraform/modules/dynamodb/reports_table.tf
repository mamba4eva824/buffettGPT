# Investment Reports Tables - stores cached Opus-generated analysis reports
# Part of the Investment Research Feature Add-On
#
# NOTE: investment_reports (v1) table has been REMOVED as part of cleanup.
# Only investment_reports_v2 (section-based schema) is active.

# Investment Reports v2 Table - section-per-item schema for progressive loading
# Each report is stored as 18 items: 1 metadata + 17 sections
resource "aws_dynamodb_table" "investment_reports_v2" {
  name         = "investment-reports-v2-${var.environment}"
  billing_mode = var.billing_mode

  hash_key  = "ticker"
  range_key = "section_id"

  attribute {
    name = "ticker"
    type = "S"
  }

  attribute {
    name = "section_id"
    type = "S"
  }

  attribute {
    name = "part"
    type = "N"
  }

  attribute {
    name = "generated_at"
    type = "S"
  }

  # GSI for querying sections by part (executive=1, detailed=2, realtalk=3)
  global_secondary_index {
    name            = "part-index"
    hash_key        = "ticker"
    range_key       = "part"
    projection_type = "ALL"
  }

  # GSI for querying by generation date (for batch updates/refresh tracking)
  global_secondary_index {
    name            = "generated-at-index"
    hash_key        = "ticker"
    range_key       = "generated_at"
    projection_type = "KEYS_ONLY"
  }

  # TTL for automatic expiration (reports refresh quarterly)
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Match existing security patterns
  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  deletion_protection_enabled = var.enable_deletion_protection

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-investment-reports-v2"
      Purpose = "Section-based investment reports for progressive loading"
      Version = "2.0"
    }
  )
}
