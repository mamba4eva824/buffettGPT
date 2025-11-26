output "action_group_id" {
  description = "The unique identifier of the action group"
  value       = aws_bedrockagent_agent_action_group.this.action_group_id
}

output "action_group_name" {
  description = "The name of the action group"
  value       = aws_bedrockagent_agent_action_group.this.action_group_name
}

output "action_group_state" {
  description = "The state of the action group"
  value       = aws_bedrockagent_agent_action_group.this.action_group_state
}

output "lambda_permission_id" {
  description = "The ID of the Lambda permission resource"
  value       = aws_lambda_permission.bedrock_invoke.id
}
