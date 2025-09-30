# Outputs for IAM module

output "knowledge_base_role_arn" {
  description = "ARN of the Knowledge Base service role"
  value       = aws_iam_role.knowledge_base_role.arn
}

output "knowledge_base_role_name" {
  description = "Name of the Knowledge Base service role"
  value       = aws_iam_role.knowledge_base_role.name
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
  description = "ARN of the Knowledge Base policy"
  value       = aws_iam_policy.knowledge_base_policy.arn
}

output "agent_policy_arn" {
  description = "ARN of the Agent policy"
  value       = aws_iam_policy.agent_policy.arn
}