# Outputs for Secrets Manager module

output "secret_arn" {
  description = "ARN of the Pinecone API key secret"
  value       = aws_secretsmanager_secret.pinecone_api_key.arn
}

output "secret_name" {
  description = "Name of the Pinecone API key secret"
  value       = aws_secretsmanager_secret.pinecone_api_key.name
}

output "secret_id" {
  description = "ID of the Pinecone API key secret"
  value       = aws_secretsmanager_secret.pinecone_api_key.id
}