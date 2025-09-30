# Outputs for the complete example

output "configuration_summary" {
  description = "Summary of the deployed Bedrock + Pinecone configuration"
  value       = module.buffett_bedrock_pinecone.configuration_summary
}

output "knowledge_base_id" {
  description = "ID of the deployed Knowledge Base"
  value       = module.buffett_bedrock_pinecone.knowledge_base_id
}

output "agent_id" {
  description = "ID of the deployed Bedrock Agent"
  value       = module.buffett_bedrock_pinecone.agent_id
}

output "agent_alias_id" {
  description = "ID of the agent alias"
  value       = module.buffett_bedrock_pinecone.agent_alias_id
}

output "pinecone_secret_arn" {
  description = "ARN of the Pinecone API key secret"
  value       = module.buffett_bedrock_pinecone.pinecone_secret_arn
}