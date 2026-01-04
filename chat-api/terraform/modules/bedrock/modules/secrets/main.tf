# Secrets Manager module for Pinecone API key
# Creates and manages the Pinecone API key secret for Bedrock Knowledge Base

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.25"
    }
  }
}

# Pinecone API Key Secret
resource "aws_secretsmanager_secret" "pinecone_api_key" {
  name        = var.secret_name
  description = var.secret_description

  # Force delete after 7 days (for dev/testing)
  force_overwrite_replica_secret = true
  recovery_window_in_days        = var.recovery_window_days

  tags = merge(var.tags, {
    Name        = var.secret_name
    Purpose     = "Pinecone API Key for Bedrock Knowledge Base"
    Component   = "Bedrock Knowledge Base"
  })
}

# Pinecone API Key Secret Version - Commented out since secret already exists
# resource "aws_secretsmanager_secret_version" "pinecone_api_key" {
#   secret_id     = aws_secretsmanager_secret.pinecone_api_key.id
#   secret_string = var.pinecone_api_key
#
#   lifecycle {
#     ignore_changes = [secret_string]
#   }
# }