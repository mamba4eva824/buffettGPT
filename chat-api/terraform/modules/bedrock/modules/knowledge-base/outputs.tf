# Outputs for Knowledge Base module

output "knowledge_base_id" {
  description = "ID of the Bedrock Knowledge Base"
  value       = aws_bedrockagent_knowledge_base.main.id
}

output "knowledge_base_arn" {
  description = "ARN of the Bedrock Knowledge Base"
  value       = aws_bedrockagent_knowledge_base.main.arn
}

output "knowledge_base_name" {
  description = "Name of the Bedrock Knowledge Base"
  value       = aws_bedrockagent_knowledge_base.main.name
}

output "knowledge_base_created_at" {
  description = "Time when the knowledge base was created"
  value       = aws_bedrockagent_knowledge_base.main.created_at
}

output "data_source_id" {
  description = "ID of the data source (if created)"
  value       = var.create_data_source ? aws_bedrockagent_data_source.main[0].data_source_id : null
}

output "data_source_name" {
  description = "Name of the data source (if created)"
  value       = var.create_data_source ? aws_bedrockagent_data_source.main[0].name : null
}

