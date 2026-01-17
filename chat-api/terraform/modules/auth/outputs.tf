# Auth Module Outputs

output "auth_callback_function_arn" {
  description = "ARN of the auth callback Lambda function"
  value       = aws_lambda_function.auth_callback.arn
}

output "auth_callback_function_name" {
  description = "Name of the auth callback Lambda function"
  value       = aws_lambda_function.auth_callback.function_name
}

output "auth_callback_invoke_arn" {
  description = "Invoke ARN of the auth callback Lambda function"
  value       = aws_lambda_function.auth_callback.invoke_arn
}

output "auth_verify_function_arn" {
  description = "ARN of the auth verify Lambda function"
  value       = aws_lambda_function.auth_verify.arn
}

output "auth_verify_function_name" {
  description = "Name of the auth verify Lambda function"
  value       = aws_lambda_function.auth_verify.function_name
}

output "auth_verify_invoke_arn" {
  description = "Invoke ARN of the auth verify Lambda function"
  value       = aws_lambda_function.auth_verify.invoke_arn
}

output "users_table_name" {
  description = "Name of the DynamoDB users table"
  value       = aws_dynamodb_table.users.name
}

output "users_table_arn" {
  description = "ARN of the DynamoDB users table"
  value       = aws_dynamodb_table.users.arn
}

output "jwt_secret_arn" {
  description = "ARN of the JWT secret in AWS Secrets Manager"
  value       = aws_secretsmanager_secret.jwt_secret.arn
}