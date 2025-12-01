# Secrets Management for Lambda Handlers

# ================================================
# Perplexity API Key (for Search Handler)
# ================================================
resource "aws_secretsmanager_secret" "search_api_key" {
  name        = "${var.project_name}-${var.environment}-sonar"
  description = "Perplexity API key for AI search in ${var.project_name}"

  lifecycle {
    prevent_destroy = true
  }

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-${var.environment}-sonar"
      Purpose = "Perplexity API authentication"
    }
  )
}

# Note: Secret value should be populated manually or via CI/CD
# The secret version is intentionally not managed here to prevent
# sensitive values from being stored in Terraform state
#
# To set the secret value manually:
# aws secretsmanager put-secret-value \
#   --secret-id <secret-arn> \
#   --secret-string "your-api-key-here"

# ================================================
# FMP API Key (for Financial Data Fetching)
# ================================================
# This secret was created manually by the user in AWS Secrets Manager
# Secret structure: {"FMP_API_KEY": "<actual-api-key>"}
data "aws_secretsmanager_secret" "fmp_api_key" {
  name = "${var.project_name}-${var.environment}-fmp"
}

data "aws_secretsmanager_secret_version" "fmp_api_key" {
  secret_id = data.aws_secretsmanager_secret.fmp_api_key.id
}
