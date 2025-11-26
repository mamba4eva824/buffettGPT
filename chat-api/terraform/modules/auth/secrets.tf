# Secrets Management for Auth Module

# Store Google OAuth credentials in AWS Secrets Manager
resource "aws_secretsmanager_secret" "google_oauth" {
  name        = "${var.project_name}-${var.environment}-google-oauth-v2"
  description = "Google OAuth credentials for ${var.project_name}"

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-${var.environment}-google-oauth-v2"
    }
  )
}

resource "aws_secretsmanager_secret_version" "google_oauth" {
  secret_id     = aws_secretsmanager_secret.google_oauth.id
  secret_string = jsonencode({
    client_id     = var.google_client_id
    client_secret = var.google_client_secret
  })

  # Lifecycle to prevent accidental updates in production
  lifecycle {
    ignore_changes = [secret_string]
  }
}

# Store JWT Secret in AWS Secrets Manager
resource "aws_secretsmanager_secret" "jwt_secret" {
  name        = "${var.project_name}-${var.environment}-jwt-secret-v2"
  description = "JWT signing secret for ${var.project_name}"

  tags = merge(
    var.common_tags,
    {
      Name = "${var.project_name}-${var.environment}-jwt-secret-v2"
    }
  )
}

resource "aws_secretsmanager_secret_version" "jwt_secret" {
  secret_id     = aws_secretsmanager_secret.jwt_secret.id
  secret_string = var.jwt_secret

  # Lifecycle to prevent accidental updates in production
  lifecycle {
    ignore_changes = [secret_string]
  }
}