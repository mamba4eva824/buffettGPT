# Secrets Management for Search Handler

# Store Perplexity API key in AWS Secrets Manager
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
