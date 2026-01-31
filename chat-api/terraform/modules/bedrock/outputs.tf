# Outputs for Bedrock Agents configuration
# Updated 2025-01: Removed KB, Secrets, Guardrails outputs
# Updated 2025-01: Removed Expert Agents and Supervisor outputs (archived to prediction_ensemble)

# IAM Outputs
output "agent_role_arn" {
  description = "ARN of the Agent service role"
  value       = module.iam.agent_role_arn
}

# ================================================
# Follow-up Agent Outputs (Investment Research)
# ================================================
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
