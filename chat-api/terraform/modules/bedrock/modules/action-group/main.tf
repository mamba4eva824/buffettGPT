terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.25"
    }
  }
}

# Action Group - Connects Bedrock Agent to Lambda function
resource "aws_bedrockagent_agent_action_group" "this" {
  agent_id             = var.agent_id
  agent_version        = var.agent_version
  action_group_name    = var.action_group_name
  description          = var.description
  skip_resource_in_use_check = var.skip_resource_in_use_check

  # Action Group Executor - Lambda function
  action_group_executor {
    lambda = var.lambda_arn
  }

  # API Schema - OpenAPI 3.0 specification
  api_schema {
    payload = var.api_schema_content
  }

  # Parent Action Group Signature (optional)
  # Used when this action group extends another
  parent_action_group_signature = var.parent_action_group_signature
}

# Lambda Permission - Allow Bedrock to invoke the Lambda function
resource "aws_lambda_permission" "bedrock_invoke" {
  statement_id  = var.lambda_permission_statement_id
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "bedrock.amazonaws.com"

  # Source ARN - Specific agent only
  source_arn = var.agent_arn
}
