# Outputs for IAM module

output "knowledge_base_role_arn" {
  description = "ARN of the Knowledge Base service role (deprecated)"
  value       = length(aws_iam_role.knowledge_base_role) > 0 ? aws_iam_role.knowledge_base_role[0].arn : ""
}

output "knowledge_base_role_name" {
  description = "Name of the Knowledge Base service role (deprecated)"
  value       = length(aws_iam_role.knowledge_base_role) > 0 ? aws_iam_role.knowledge_base_role[0].name : ""
}

output "agent_role_arn" {
  description = "ARN of the Agent service role"
  value       = aws_iam_role.agent_role.arn
}

output "agent_role_name" {
  description = "Name of the Agent service role"
  value       = aws_iam_role.agent_role.name
}

output "knowledge_base_policy_arn" {
  description = "ARN of the Knowledge Base policy (deprecated)"
  value       = length(aws_iam_policy.knowledge_base_policy) > 0 ? aws_iam_policy.knowledge_base_policy[0].arn : ""
}

output "agent_policy_arn" {
  description = "ARN of the Agent policy"
  value       = aws_iam_policy.agent_policy.arn
}