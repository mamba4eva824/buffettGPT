# Example configuration for Bedrock with Guardrails
# This example shows how to deploy the complete Bedrock setup with Guardrails enabled

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Deploy Bedrock with Guardrails enabled
module "bedrock_with_guardrails" {
  source = "../../"

  # Basic Configuration
  aws_region     = var.aws_region
  environment    = var.environment
  project_name   = var.project_name

  # Pinecone Configuration
  pinecone_api_key           = var.pinecone_api_key
  pinecone_connection_string = var.pinecone_connection_string

  # S3 Configuration
  source_bucket_arn = var.source_bucket_arn

  # Guardrails Configuration
  enable_guardrails                     = true
  guardrail_name                        = "warren-buffett-financial-advisor-guardrails"
  guardrail_description                 = "Comprehensive guardrails for Warren Buffett Financial Advisor ensuring responses stay focused on financial topics"
  blocked_input_messaging               = "I can only provide financial advice and investment guidance. Please ask questions related to investment planning, retirement, tax strategies, insurance, estate planning, or financial goal setting."
  blocked_outputs_messaging             = "I cannot provide that type of advice. I'm designed to help with financial planning, investment strategies, retirement planning, tax planning, insurance analysis, estate planning basics, and financial goal setting. Please ask a finance-related question."
  enable_content_policy                 = true
  enable_sensitive_information_policy   = true
  enable_topic_policy                   = true
  enable_word_policy                    = true
  enable_contextual_grounding          = true

  # Agent Configuration with updated instruction
  agent_instruction = <<-EOT
    You are a financial advisor assistant focused exclusively on providing investment and financial guidance based on Warren Buffett's philosophy and wisdom from decades of shareholder letters.

    **Your Role:**
    - Provide investment advice and portfolio management guidance
    - Assist with retirement planning strategies
    - Explain tax planning strategies for investments
    - Help with insurance needs analysis for financial protection
    - Offer estate planning basics related to wealth transfer
    - Support financial goal setting and planning

    **You ONLY provide information about:**
    - Investment planning and portfolio management
    - Retirement planning and strategies
    - Tax planning strategies (investment-related)
    - Insurance needs analysis
    - Estate planning basics
    - Financial goal setting and budgeting

    **You do NOT provide advice on:**
    - Medical issues or health-related topics
    - Legal matters unrelated to finance
    - Personal relationships or counseling
    - Political opinions or endorsements
    - Non-financial topics

    **Guidelines:**
    - Always ground your responses in Warren Buffett's actual teachings from shareholder letters
    - Reference specific examples or companies Buffett has mentioned when relevant
    - Maintain Buffett's characteristic wit and folksy wisdom in your responses
    - If asked about topics outside your scope, politely redirect to financial topics
    - Focus on timeless investment principles that Buffett consistently advocates
    - Be honest about limitations and knowledge cutoff dates

    Your goal is to help users understand and apply Buffett's investment wisdom specifically to their financial decision-making while staying strictly within the bounds of financial advisory topics.
  EOT
}

# Output important information
output "configuration_summary" {
  description = "Complete configuration summary including Guardrails"
  value       = module.bedrock_with_guardrails.configuration_summary
}

output "guardrails_info" {
  description = "Guardrails configuration details"
  value = {
    id      = module.bedrock_with_guardrails.guardrail_id
    arn     = module.bedrock_with_guardrails.guardrail_arn
    name    = module.bedrock_with_guardrails.guardrail_name
    version = module.bedrock_with_guardrails.guardrail_version
    status  = module.bedrock_with_guardrails.guardrail_status
  }
}

output "deployment_instructions" {
  description = "Instructions for deploying this configuration"
  value = <<-EOT

    AWS Bedrock with Guardrails Deployment Complete!

    🛡️  GUARDRAILS ENABLED: Your AI assistant is now protected with comprehensive guardrails

    📋 What was deployed:
    - Bedrock Knowledge Base with Pinecone vector database
    - Bedrock Agent with Warren Buffett investment wisdom
    - Bedrock Guardrails with financial topic restrictions
    - IAM roles with appropriate permissions

    🔒 Guardrails Protection:
    - Content filtering (hate, violence, sexual content, etc.)
    - Topic restrictions (medical, legal, personal relationships blocked)
    - PII protection (SSN, credit cards, addresses blocked)
    - Word filtering (profanity and inappropriate terms blocked)
    - Contextual grounding for factual accuracy

    🎯 Your AI assistant will ONLY provide advice on:
    - Investment planning and portfolio management
    - Retirement planning
    - Tax planning strategies
    - Insurance needs analysis
    - Estate planning basics
    - Financial goal setting

    ⚙️  Next steps:
    1. Test the agent with financial questions
    2. Try asking non-financial questions to see guardrails in action
    3. Review CloudWatch logs for guardrail events
    4. Adjust guardrail settings as needed

    Agent ID: ${module.bedrock_with_guardrails.agent_id}
    Agent Alias: ${module.bedrock_with_guardrails.agent_alias_name}
    Guardrails ID: ${module.bedrock_with_guardrails.guardrail_id}
  EOT
}