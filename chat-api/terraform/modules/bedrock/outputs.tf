# Outputs for root Bedrock + Pinecone configuration

# Secrets Manager Outputs
output "pinecone_secret_arn" {
  description = "ARN of the Pinecone API key secret"
  value       = module.secrets.secret_arn
}

output "pinecone_secret_name" {
  description = "Name of the Pinecone API key secret"
  value       = module.secrets.secret_name
}

# IAM Outputs
output "knowledge_base_role_arn" {
  description = "ARN of the Knowledge Base service role"
  value       = module.iam.knowledge_base_role_arn
}

output "agent_role_arn" {
  description = "ARN of the Agent service role"
  value       = module.iam.agent_role_arn
}

# Knowledge Base Outputs
output "knowledge_base_id" {
  description = "ID of the Bedrock Knowledge Base"
  value       = module.knowledge_base.knowledge_base_id
}

output "knowledge_base_arn" {
  description = "ARN of the Bedrock Knowledge Base"
  value       = module.knowledge_base.knowledge_base_arn
}

output "knowledge_base_name" {
  description = "Name of the Bedrock Knowledge Base"
  value       = module.knowledge_base.knowledge_base_name
}

output "knowledge_base_created_at" {
  description = "Time when the Bedrock Knowledge Base was created"
  value       = module.knowledge_base.knowledge_base_created_at
}

output "data_source_id" {
  description = "ID of the data source"
  value       = module.knowledge_base.data_source_id
}

# Agent Outputs
output "agent_id" {
  description = "ID of the Bedrock Agent"
  value       = module.agent.agent_id
}

output "agent_arn" {
  description = "ARN of the Bedrock Agent"
  value       = module.agent.agent_arn
}

output "agent_name" {
  description = "Name of the Bedrock Agent"
  value       = module.agent.agent_name
}

output "agent_version" {
  description = "Version of the Bedrock Agent"
  value       = module.agent.agent_version
}

output "agent_alias_id" {
  description = "ID of the agent alias"
  value       = module.agent.agent_alias_id
}

output "agent_alias_arn" {
  description = "ARN of the agent alias"
  value       = module.agent.agent_alias_arn
}

output "agent_alias_name" {
  description = "Name of the agent alias"
  value       = module.agent.agent_alias_name
}

# Guardrails Outputs
output "guardrail_id" {
  description = "ID of the Bedrock Guardrail"
  value       = var.enable_guardrails ? module.guardrails[0].guardrail_id : null
}

output "guardrail_arn" {
  description = "ARN of the Bedrock Guardrail"
  value       = var.enable_guardrails ? module.guardrails[0].guardrail_arn : null
}

output "guardrail_name" {
  description = "Name of the Bedrock Guardrail"
  value       = var.enable_guardrails ? module.guardrails[0].guardrail_name : null
}

output "guardrail_version" {
  description = "Version of the Bedrock Guardrail"
  value       = var.enable_guardrails ? module.guardrails[0].guardrail_version : null
}

output "guardrail_status" {
  description = "Status of the Bedrock Guardrail"
  value       = var.enable_guardrails ? module.guardrails[0].guardrail_status : null
}

# ================================================
# Expert Agent Outputs (for Ensemble Analysis)
# ================================================

# Debt Expert Agent
output "debt_agent_id" {
  description = "ID of the Debt Expert Agent"
  value       = module.debt_expert_agent.agent_id
}

output "debt_agent_alias_id" {
  description = "Alias ID of the Debt Expert Agent"
  value       = module.debt_expert_agent.agent_alias_id
}

# Cashflow Expert Agent
output "cashflow_agent_id" {
  description = "ID of the Cashflow Expert Agent"
  value       = module.cashflow_expert_agent.agent_id
}

output "cashflow_agent_alias_id" {
  description = "Alias ID of the Cashflow Expert Agent"
  value       = module.cashflow_expert_agent.agent_alias_id
}

# Growth Expert Agent
output "growth_agent_id" {
  description = "ID of the Growth Expert Agent"
  value       = module.growth_expert_agent.agent_id
}

output "growth_agent_alias_id" {
  description = "Alias ID of the Growth Expert Agent"
  value       = module.growth_expert_agent.agent_alias_id
}

# Configuration Summary
output "configuration_summary" {
  description = "Summary of the deployed configuration"
  value = {
    knowledge_base = {
      id         = module.knowledge_base.knowledge_base_id
      name       = module.knowledge_base.knowledge_base_name
      created_at = module.knowledge_base.knowledge_base_created_at
    }
    agent = {
      id         = module.agent.agent_id
      name       = module.agent.agent_name
      version    = module.agent.agent_version
      alias_id   = module.agent.agent_alias_id
      alias_name = module.agent.agent_alias_name
    }
    guardrails = var.enable_guardrails ? {
      id      = module.guardrails[0].guardrail_id
      name    = module.guardrails[0].guardrail_name
      status  = module.guardrails[0].guardrail_status
      version = module.guardrails[0].guardrail_version
    } : null
    pinecone = {
      secret_name = module.secrets.secret_name
      connection  = var.pinecone_connection_string
    }
  }
}