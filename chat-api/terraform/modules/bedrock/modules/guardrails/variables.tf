# Variables for Bedrock Guardrails module

variable "guardrail_name" {
  description = "Name of the Bedrock Guardrail"
  type        = string
  default     = "buffetgpt-advisor-guardrails"
}

variable "guardrail_description" {
  description = "Description of the Bedrock Guardrail"
  type        = string
  default     = "Guardrails for BuffetGPT Financial Advisor - ensures responses stay focused on financial advice and investment topics"
}

variable "blocked_input_messaging" {
  description = "Message to return when input is blocked"
  type        = string
  default     = "I can only provide financial advice and investment guidance. Please ask questions related to investment planning, retirement, tax strategies, insurance, estate planning, or financial goal setting."
}

variable "blocked_outputs_messaging" {
  description = "Message to return when output is blocked"
  type        = string
  default     = "I cannot provide that type of advice. I'm designed to help with financial planning, investment strategies, retirement planning, tax planning, insurance analysis, estate planning basics, and financial goal setting. Please ask a finance-related question."
}

# Content Policy Configuration
variable "enable_content_policy" {
  description = "Enable content policy filters"
  type        = bool
  default     = true
}

variable "content_filters" {
  description = "Configuration for content filters"
  type = object({
    hate = optional(object({
      input_strength  = string
      output_strength = string
    }))
    insults = optional(object({
      input_strength  = string
      output_strength = string
    }))
    sexual = optional(object({
      input_strength  = string
      output_strength = string
    }))
    violence = optional(object({
      input_strength  = string
      output_strength = string
    }))
    misconduct = optional(object({
      input_strength  = string
      output_strength = string
    }))
    prompt_attack = optional(object({
      input_strength  = string
      output_strength = string
    }))
  })
  default = {
    hate = {
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    insults = {
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    sexual = {
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    violence = {
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    misconduct = {
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    prompt_attack = {
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
  }
}

# Sensitive Information Policy Configuration
variable "enable_sensitive_information_policy" {
  description = "Enable sensitive information policy"
  type        = bool
  default     = true
}

variable "pii_entities" {
  description = "PII entities to filter"
  type = list(object({
    action = string
    type   = string
  }))
  default = []
}

variable "custom_regexes" {
  description = "Custom regex patterns for sensitive information"
  type = list(object({
    action      = string
    description = string
    name        = string
    pattern     = string
  }))
  default = []
}

# Topic Policy Configuration
variable "enable_topic_policy" {
  description = "Enable topic policy to deny specific topics"
  type        = bool
  default     = true
}

variable "denied_topics" {
  description = "Topics to deny in conversations"
  type = list(object({
    name       = string
    definition = string
    examples   = list(string)
  }))
  default = [
    {
      name       = "medical-advice"
      definition = "Medical advice, health recommendations, diagnosis, or treatment suggestions"
      examples = [
        "Should I take this medication?",
        "What's wrong with my health?",
        "How do I treat this condition?",
        "Is this symptom serious?"
      ]
    },
    {
      name       = "legal-advice"
      definition = "Legal advice unrelated to financial planning, including litigation, contracts, or legal proceedings"
      examples = [
        "Should I sue someone?",
        "How do I write a contract?",
        "What are my legal rights in this situation?",
        "How do I file a lawsuit?"
      ]
    },
    {
      name       = "personal-relationships"
      definition = "Personal relationship advice, dating, marriage counseling, or family disputes"
      examples = [
        "How do I fix my marriage?",
        "Should I break up with my partner?",
        "How do I deal with family drama?",
        "Dating advice needed"
      ]
    },
    {
      name       = "political-opinions"
      definition = "Political endorsements, partisan opinions, or controversial political topics"
      examples = [
        "Which political party should I vote for?",
        "What's your opinion on this politician?",
        "Should I support this political cause?",
        "Tell me about political conspiracies"
      ]
    },
    {
      name       = "inappropriate-content"
      definition = "Requests for inappropriate, illegal, or harmful content"
      examples = [
        "How to commit fraud",
        "Illegal investment schemes",
        "How to avoid paying taxes illegally",
        "Inappropriate financial advice"
      ]
    }
  ]
}

# Word Policy Configuration
variable "enable_word_policy" {
  description = "Enable word policy filters"
  type        = bool
  default     = true
}

variable "managed_word_lists" {
  description = "Managed word lists to apply"
  type        = list(string)
  default     = ["PROFANITY"]
}

variable "custom_word_filters" {
  description = "Custom words to filter"
  type        = list(string)
  default = [
    # Competitor financial services
    "other-advisor-name",
    "competitor-firm",
    # Inappropriate financial terms
    "get-rich-quick",
    "guaranteed-returns",
    "risk-free-investment"
  ]
}

# Contextual Grounding Policy Configuration (2024-2025 feature)
variable "enable_contextual_grounding" {
  description = "Enable contextual grounding policy for factual accuracy"
  type        = bool
  default     = false
}

variable "contextual_grounding_filters" {
  description = "Contextual grounding filters configuration"
  type = list(object({
    threshold = number
    type      = string
  }))
  default = [
    {
      threshold = 0.75
      type      = "GROUNDING"
    },
    {
      threshold = 0.8
      type      = "RELEVANCE"
    }
  ]
}

# Version Configuration
variable "create_version" {
  description = "Whether to create a version of the guardrail"
  type        = bool
  default     = true
}

variable "version_description" {
  description = "Description for the guardrail version"
  type        = string
  default     = "Initial version of Warren Buffett Financial Advisor Guardrails"
}

# Tags
variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}