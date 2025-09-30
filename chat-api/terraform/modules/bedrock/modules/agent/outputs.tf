# Outputs for Agent module

output "agent_id" {
  description = "ID of the Bedrock Agent"
  value       = aws_bedrockagent_agent.main.id
}

output "agent_arn" {
  description = "ARN of the Bedrock Agent"
  value       = aws_bedrockagent_agent.main.agent_arn
}

output "agent_name" {
  description = "Name of the Bedrock Agent"
  value       = aws_bedrockagent_agent.main.agent_name
}

output "agent_prepared_at" {
  description = "Timestamp of when the agent was last prepared"
  value       = aws_bedrockagent_agent.main.prepared_at
}

output "agent_version" {
  description = "Version of the Bedrock Agent"
  value       = aws_bedrockagent_agent.main.agent_version
}

output "agent_alias_id" {
  description = "ID of the agent alias"
  value       = aws_bedrockagent_agent_alias.main.agent_alias_id
}

output "agent_alias_arn" {
  description = "ARN of the agent alias"
  value       = aws_bedrockagent_agent_alias.main.agent_alias_arn
}

output "agent_alias_name" {
  description = "Name of the agent alias"
  value       = aws_bedrockagent_agent_alias.main.agent_alias_name
}

output "knowledge_base_association_id" {
  description = "ID of the knowledge base association (if created)"
  value       = var.associate_knowledge_base ? aws_bedrockagent_agent_knowledge_base_association.main[0].id : null
}

output "knowledge_base_association_state" {
  description = "State of the knowledge base association (if created)"
  value       = var.associate_knowledge_base ? aws_bedrockagent_agent_knowledge_base_association.main[0].knowledge_base_state : null
}