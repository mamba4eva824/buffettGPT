# Outputs for Bedrock Agents configuration
# Updated 2025-01: Removed KB, Secrets, Guardrails outputs

# IAM Outputs
output "agent_role_arn" {
  description = "ARN of the Agent service role"
  value       = module.iam.agent_role_arn
}

# ================================================
# Primary Agent Outputs (Supervisor)
# ================================================
output "agent_id" {
  description = "ID of the primary Bedrock Agent (supervisor)"
  value       = module.supervisor_agent.agent_id
}

output "agent_arn" {
  description = "ARN of the primary Bedrock Agent (supervisor)"
  value       = module.supervisor_agent.agent_arn
}

output "agent_name" {
  description = "Name of the primary Bedrock Agent (supervisor)"
  value       = module.supervisor_agent.agent_name
}

output "agent_version" {
  description = "Version of the primary Bedrock Agent (supervisor)"
  value       = module.supervisor_agent.agent_version
}

output "agent_alias_id" {
  description = "ID of the primary agent alias (supervisor)"
  value       = module.supervisor_agent.agent_alias_id
}

output "agent_alias_arn" {
  description = "ARN of the primary agent alias (supervisor)"
  value       = module.supervisor_agent.agent_alias_arn
}

output "agent_alias_name" {
  description = "Name of the primary agent alias (supervisor)"
  value       = module.supervisor_agent.agent_alias_name
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

# Supervisor Agent
output "supervisor_agent_id" {
  description = "ID of the Supervisor Agent"
  value       = module.supervisor_agent.agent_id
}

output "supervisor_agent_alias_id" {
  description = "Alias ID of the Supervisor Agent"
  value       = module.supervisor_agent.agent_alias_id
}

output "supervisor_agent_arn" {
  description = "ARN of the Supervisor Agent"
  value       = module.supervisor_agent.agent_arn
}

# Follow-up Agent
output "followup_agent_id" {
  description = "ID of the Follow-up Agent"
  value       = module.followup_agent.agent_id
}

output "followup_agent_alias_id" {
  description = "Alias ID of the Follow-up Agent"
  value       = module.followup_agent.agent_alias_id
}

output "followup_agent_arn" {
  description = "ARN of the Follow-up Agent"
  value       = module.followup_agent.agent_arn
}

# ================================================
# Configuration Summary
# ================================================
output "configuration_summary" {
  description = "Summary of the deployed Bedrock agents configuration"
  value = {
    supervisor_agent = {
      id         = module.supervisor_agent.agent_id
      name       = module.supervisor_agent.agent_name
      version    = module.supervisor_agent.agent_version
      alias_id   = module.supervisor_agent.agent_alias_id
      alias_name = module.supervisor_agent.agent_alias_name
    }
    expert_agents = {
      debt     = module.debt_expert_agent.agent_id
      cashflow = module.cashflow_expert_agent.agent_id
      growth   = module.growth_expert_agent.agent_id
    }
    followup_agent = {
      id       = module.followup_agent.agent_id
      alias_id = module.followup_agent.agent_alias_id
    }
  }
}

# ================================================
# REMOVED OUTPUTS (2025-01 Cleanup)
# ================================================
# The following outputs were removed as part of RAG chatbot deprecation:
# - pinecone_secret_arn/name (Secrets module removed)
# - knowledge_base_role_arn (KB module removed)
# - knowledge_base_id/arn/name/created_at (KB module removed)
# - data_source_id (KB module removed)
# - guardrail_id/arn/name/version/status (Guardrails module removed)
# ================================================
