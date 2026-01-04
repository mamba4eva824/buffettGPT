# Bedrock Guardrails module for implementing safety and compliance controls
# Based on AWS Provider documentation and best practices for 2024-2025

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.25"
    }
  }
}

# Bedrock Guardrail
resource "aws_bedrock_guardrail" "main" {
  name                      = var.guardrail_name
  description               = var.guardrail_description
  blocked_input_messaging   = var.blocked_input_messaging
  blocked_outputs_messaging = var.blocked_outputs_messaging

  # Content Policy Configuration
  dynamic "content_policy_config" {
    for_each = var.enable_content_policy ? [1] : []
    content {
      # Hate content filter
      dynamic "filters_config" {
        for_each = var.content_filters.hate != null ? [var.content_filters.hate] : []
        content {
          input_strength  = filters_config.value.input_strength
          output_strength = filters_config.value.output_strength
          type           = "HATE"
        }
      }

      # Insults content filter
      dynamic "filters_config" {
        for_each = var.content_filters.insults != null ? [var.content_filters.insults] : []
        content {
          input_strength  = filters_config.value.input_strength
          output_strength = filters_config.value.output_strength
          type           = "INSULTS"
        }
      }

      # Sexual content filter
      dynamic "filters_config" {
        for_each = var.content_filters.sexual != null ? [var.content_filters.sexual] : []
        content {
          input_strength  = filters_config.value.input_strength
          output_strength = filters_config.value.output_strength
          type           = "SEXUAL"
        }
      }

      # Violence content filter
      dynamic "filters_config" {
        for_each = var.content_filters.violence != null ? [var.content_filters.violence] : []
        content {
          input_strength  = filters_config.value.input_strength
          output_strength = filters_config.value.output_strength
          type           = "VIOLENCE"
        }
      }

      # Misconduct content filter
      dynamic "filters_config" {
        for_each = var.content_filters.misconduct != null ? [var.content_filters.misconduct] : []
        content {
          input_strength  = filters_config.value.input_strength
          output_strength = filters_config.value.output_strength
          type           = "MISCONDUCT"
        }
      }

      # Prompt attack content filter
      dynamic "filters_config" {
        for_each = var.content_filters.prompt_attack != null ? [var.content_filters.prompt_attack] : []
        content {
          input_strength  = filters_config.value.input_strength
          output_strength = filters_config.value.output_strength
          type           = "PROMPT_ATTACK"
        }
      }
    }
  }

  # Sensitive Information Policy Configuration
  dynamic "sensitive_information_policy_config" {
    for_each = var.enable_sensitive_information_policy ? [1] : []
    content {
      # PII Entities Configuration
      dynamic "pii_entities_config" {
        for_each = var.pii_entities
        content {
          action = pii_entities_config.value.action
          type   = pii_entities_config.value.type
        }
      }

      # Custom Regex Configuration
      dynamic "regexes_config" {
        for_each = var.custom_regexes
        content {
          action      = regexes_config.value.action
          description = regexes_config.value.description
          name        = regexes_config.value.name
          pattern     = regexes_config.value.pattern
        }
      }
    }
  }

  # Topic Policy Configuration
  dynamic "topic_policy_config" {
    for_each = var.enable_topic_policy ? [1] : []
    content {
      dynamic "topics_config" {
        for_each = var.denied_topics
        content {
          name       = topics_config.value.name
          definition = topics_config.value.definition
          examples   = topics_config.value.examples
          type       = "DENY"
        }
      }
    }
  }

  # Word Policy Configuration
  dynamic "word_policy_config" {
    for_each = var.enable_word_policy ? [1] : []
    content {
      # Managed word lists
      dynamic "managed_word_lists_config" {
        for_each = var.managed_word_lists
        content {
          type = managed_word_lists_config.value
        }
      }

      # Custom word lists
      dynamic "words_config" {
        for_each = var.custom_word_filters
        content {
          text = words_config.value
        }
      }
    }
  }

  # Contextual Grounding Policy Configuration (2024-2025 feature)
  dynamic "contextual_grounding_policy_config" {
    for_each = var.enable_contextual_grounding ? [1] : []
    content {
      dynamic "filters_config" {
        for_each = var.contextual_grounding_filters
        content {
          threshold = filters_config.value.threshold
          type      = filters_config.value.type
        }
      }
    }
  }

  tags = merge(var.tags, {
    Name      = var.guardrail_name
    Purpose   = "Bedrock Guardrails for BuffettGPT Investment Advisor"
    Component = "Bedrock Guardrails"
  })
}

# Guardrail Version
resource "aws_bedrock_guardrail_version" "main" {
  count = var.create_version ? 1 : 0

  guardrail_arn = aws_bedrock_guardrail.main.guardrail_arn
  description   = var.version_description

  timeouts {
    create = "5m"
    delete = "5m"
  }

  depends_on = [aws_bedrock_guardrail.main]
}