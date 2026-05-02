# Outputs for Bedrock Agents configuration
# Updated 2025-01: Removed KB, Secrets, Guardrails outputs
# Updated 2025-01: Removed Expert Agents and Supervisor outputs (archived to prediction_ensemble)
# Updated 2026-05: Removed Follow-up Agent + action group outputs
#                  (live follow-up agent uses converse_stream + inline tools, no Bedrock Agent)

# IAM Outputs
output "agent_role_arn" {
  description = "ARN of the Agent service role"
  value       = module.iam.agent_role_arn
}

# ================================================
# REMOVED OUTPUTS
# ================================================
# 2026-05 cleanup:
# - followup_agent_id, followup_agent_alias_id, followup_agent_arn
# - configuration_summary (only referenced followup_agent fields)
#
# 2025-01 cleanup:
# - pinecone_secret_arn/name (Secrets module removed)
# - knowledge_base_role_arn (KB module removed)
# - knowledge_base_id/arn/name/created_at (KB module removed)
# - data_source_id (KB module removed)
# - guardrail_id/arn/name/version/status (Guardrails module removed)
# ================================================
