# Outputs for Guardrails example

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

output "agent_info" {
  description = "Agent configuration details"
  value = {
    id         = module.bedrock_with_guardrails.agent_id
    arn        = module.bedrock_with_guardrails.agent_arn
    name       = module.bedrock_with_guardrails.agent_name
    status     = module.bedrock_with_guardrails.agent_status
    alias_id   = module.bedrock_with_guardrails.agent_alias_id
    alias_name = module.bedrock_with_guardrails.agent_alias_name
  }
}

output "knowledge_base_info" {
  description = "Knowledge Base configuration details"
  value = {
    id     = module.bedrock_with_guardrails.knowledge_base_id
    arn    = module.bedrock_with_guardrails.knowledge_base_arn
    name   = module.bedrock_with_guardrails.knowledge_base_name
    status = module.bedrock_with_guardrails.knowledge_base_status
  }
}

output "deployment_instructions" {
  description = "Instructions for deploying and testing this configuration"
  value = <<-EOT

    🎉 AWS BEDROCK WITH GUARDRAILS DEPLOYED SUCCESSFULLY!

    🛡️  GUARDRAILS PROTECTION ACTIVE
    Your Warren Buffett Financial Advisor is now protected with comprehensive guardrails:

    📋 DEPLOYED RESOURCES:
    ├── Knowledge Base: ${module.bedrock_with_guardrails.knowledge_base_name}
    ├── Agent: ${module.bedrock_with_guardrails.agent_name}
    ├── Agent Alias: ${module.bedrock_with_guardrails.agent_alias_name}
    └── Guardrails: ${module.bedrock_with_guardrails.guardrail_name}

    🔒 GUARDRAILS FEATURES:
    ✅ Content Filtering (hate, violence, sexual content)
    ✅ Topic Restrictions (medical, legal, personal topics blocked)
    ✅ PII Protection (SSN, credit cards, addresses)
    ✅ Word Filtering (profanity and competitors)
    ✅ Contextual Grounding (factual accuracy)

    🎯 APPROVED TOPICS:
    ✅ Investment planning and portfolio management
    ✅ Retirement planning strategies
    ✅ Tax planning for investments
    ✅ Insurance needs analysis
    ✅ Estate planning basics
    ✅ Financial goal setting

    ❌ BLOCKED TOPICS:
    ❌ Medical advice and health topics
    ❌ Legal advice unrelated to finance
    ❌ Personal relationship counseling
    ❌ Political opinions
    ❌ Inappropriate or harmful content

    🧪 TESTING YOUR DEPLOYMENT:

    1. Test approved financial questions:
       "How should I diversify my portfolio according to Buffett?"
       "What's Buffett's advice on retirement planning?"
       "How do I evaluate a stock like Buffett?"

    2. Test blocked content (should be filtered):
       "Can you give me medical advice?"
       "Help me with relationship problems"
       "What's your political opinion?"

    3. Monitor guardrail activity:
       - Check CloudWatch logs for guardrail events
       - Review blocked inputs/outputs in console

    📊 KEY IDENTIFIERS:
    Agent ID: ${module.bedrock_with_guardrails.agent_id}
    Guardrails ID: ${module.bedrock_with_guardrails.guardrail_id}
    Knowledge Base ID: ${module.bedrock_with_guardrails.knowledge_base_id}

    🔧 NEXT STEPS:
    1. Integrate agent with your application using the Agent ID
    2. Test thoroughly with various input types
    3. Adjust guardrail settings if needed
    4. Monitor performance and user interactions

    Happy investing with your protected Warren Buffett AI advisor! 📈
  EOT
}