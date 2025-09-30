# Outputs for Bedrock Guardrails module

output "guardrail_arn" {
  description = "ARN of the created Bedrock Guardrail"
  value       = aws_bedrock_guardrail.main.guardrail_arn
}

output "guardrail_id" {
  description = "ID of the created Bedrock Guardrail"
  value       = aws_bedrock_guardrail.main.guardrail_id
}

output "guardrail_name" {
  description = "Name of the created Bedrock Guardrail"
  value       = aws_bedrock_guardrail.main.name
}

output "guardrail_version" {
  description = "Version of the created Bedrock Guardrail"
  value       = var.create_version ? aws_bedrock_guardrail_version.main[0].version : null
}

output "guardrail_version_arn" {
  description = "ARN of the created Bedrock Guardrail Version"
  value       = var.create_version ? aws_bedrock_guardrail_version.main[0].guardrail_arn : null
}

output "guardrail_status" {
  description = "Status of the Bedrock Guardrail"
  value       = aws_bedrock_guardrail.main.status
}

output "created_at" {
  description = "Timestamp when the guardrail was created"
  value       = aws_bedrock_guardrail.main.created_at
}

