# Rate Limiting Module
# Placeholder for rate limiting configuration
# The actual rate limiting is handled by the enhanced_rate_limits table in dynamodb module

locals {
  resource_prefix = "${var.project_name}-${var.environment}"
}

# Rate limiting configuration is managed through DynamoDB module
# This module serves as a placeholder for future rate limiting enhancements