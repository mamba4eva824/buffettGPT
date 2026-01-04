# Secrets Management for Lambda Handlers

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
