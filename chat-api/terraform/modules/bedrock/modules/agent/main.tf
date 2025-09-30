# Agent module for Bedrock Agent with Knowledge Base association
# Based on reverse-engineered configuration from existing deployment

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Bedrock Agent
resource "aws_bedrockagent_agent" "main" {
  agent_name                  = var.agent_name
  agent_resource_role_arn     = var.agent_role_arn
  description                 = var.agent_description
  foundation_model            = var.foundation_model
  instruction                 = var.agent_instruction
  idle_session_ttl_in_seconds = var.idle_session_ttl
  prepare_agent               = true  # Ensure agent is prepared after changes

  # Optional: Configure guardrails
  dynamic "guardrail_configuration" {
    for_each = var.guardrail_configuration != null ? [1] : []
    content {
      guardrail_identifier = var.guardrail_configuration.guardrail_identifier
      guardrail_version    = var.guardrail_configuration.guardrail_version
    }
  }

  # Optional: Configure prompt override
  dynamic "prompt_override_configuration" {
    for_each = var.enable_prompt_override ? [1] : []
    content {
      prompt_configurations {
        base_prompt_template = var.orchestration_prompt_template
        inference_configuration {
          max_length = var.max_response_length
          stop_sequences = var.stop_sequences
          temperature   = var.temperature
          top_k         = var.top_k
          top_p         = var.top_p
        }
        parser_mode           = var.parser_mode
        prompt_creation_mode  = "OVERRIDDEN"  # Override to use custom prompt
        prompt_state         = var.orchestration_prompt_state
        prompt_type          = "ORCHESTRATION"
      }

      # Knowledge Base Response Generation Prompt
      prompt_configurations {
        base_prompt_template = var.kb_response_prompt_template
        inference_configuration {
          max_length = var.max_response_length
          stop_sequences = ["\n\nHuman:"]
          temperature   = 0.0
          top_k         = 250
          top_p         = 1.0
        }
        parser_mode           = "DEFAULT"
        prompt_creation_mode  = "OVERRIDDEN"  # Override to use custom prompt
        prompt_state         = "ENABLED"
        prompt_type          = "KNOWLEDGE_BASE_RESPONSE_GENERATION"
      }

      # Note: Pre-processing and post-processing prompts are not configured
      # They will use AWS defaults with DISABLED state
    }
  }

  tags = merge(var.tags, {
    Name      = var.agent_name
    Purpose   = "Bedrock Agent for Warren Buffett Investment Advice"
    Component = "Bedrock Agent"
  })
}

# Agent Knowledge Base Association
resource "aws_bedrockagent_agent_knowledge_base_association" "main" {
  count               = var.associate_knowledge_base ? 1 : 0
  agent_id            = aws_bedrockagent_agent.main.id
  description         = var.kb_association_description
  knowledge_base_id   = var.knowledge_base_id
  knowledge_base_state = var.knowledge_base_state
}

# Agent Alias
resource "aws_bedrockagent_agent_alias" "main" {
  agent_alias_name = var.agent_alias_name
  agent_id         = aws_bedrockagent_agent.main.id
  description      = var.agent_alias_description

  # Only configure routing when create_agent_version is false
  # When true, routing is handled by the separate agent version resource
  dynamic "routing_configuration" {
    for_each = var.create_agent_version ? [] : [1]
    content {
      agent_version = "DRAFT"
    }
  }

  tags = merge(var.tags, {
    Name      = var.agent_alias_name
    Purpose   = "Development Alias for Bedrock Agent"
    Component = "Bedrock Agent"
  })
}