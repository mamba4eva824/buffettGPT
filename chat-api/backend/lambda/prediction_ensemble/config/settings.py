"""
Configuration settings loaded from environment variables.
Supports both legacy single-agent mode and supervisor orchestration mode.
"""
import os
from typing import Dict, Any, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Environment
# ─────────────────────────────────────────────────────────────────────────────
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# ─────────────────────────────────────────────────────────────────────────────
# AWS Configuration
# ─────────────────────────────────────────────────────────────────────────────
BEDROCK_REGION = os.environ.get('BEDROCK_REGION', 'us-east-1')

# ─────────────────────────────────────────────────────────────────────────────
# DynamoDB Tables
# ─────────────────────────────────────────────────────────────────────────────
CHAT_MESSAGES_TABLE = os.environ.get('CHAT_MESSAGES_TABLE', 'buffett-dev-chat-messages')
CONVERSATIONS_TABLE = os.environ.get('CONVERSATIONS_TABLE', 'buffett-dev-conversations')

# ─────────────────────────────────────────────────────────────────────────────
# JWT Configuration
# ─────────────────────────────────────────────────────────────────────────────
JWT_SECRET_ARN = os.environ.get('JWT_SECRET_ARN')

# ─────────────────────────────────────────────────────────────────────────────
# ML Models Configuration
# ─────────────────────────────────────────────────────────────────────────────
MODEL_S3_BUCKET = os.environ.get('ML_MODELS_BUCKET', os.environ.get('MODEL_S3_BUCKET', 'buffett-dev-models'))
MODEL_S3_PREFIX = os.environ.get('MODEL_S3_PREFIX', 'ensemble/v1')
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-5-sonnet-20241022-v2:0')

# Direct model ID for supervisor synthesis (uses converse_stream for true token streaming)
SUPERVISOR_MODEL_ID = os.environ.get(
    'SUPERVISOR_MODEL_ID',
    'us.anthropic.claude-haiku-4-5-20251001-v1:0'
)

# ─────────────────────────────────────────────────────────────────────────────
# Expert Agents Configuration (Haiku 4.5)
# ─────────────────────────────────────────────────────────────────────────────
EXPERT_AGENT_CONFIG: Dict[str, Dict[str, Any]] = {
    'debt': {
        'agent_id': os.environ.get('DEBT_AGENT_ID'),
        'agent_alias': os.environ.get('DEBT_AGENT_ALIAS'),
        'model': 'us.anthropic.claude-haiku-4-5-20251001-v1:0',
        'description': 'Debt and leverage analysis expert'
    },
    'cashflow': {
        'agent_id': os.environ.get('CASHFLOW_AGENT_ID'),
        'agent_alias': os.environ.get('CASHFLOW_AGENT_ALIAS'),
        'model': 'us.anthropic.claude-haiku-4-5-20251001-v1:0',
        'description': 'Cash flow and capital allocation expert'
    },
    'growth': {
        'agent_id': os.environ.get('GROWTH_AGENT_ID'),
        'agent_alias': os.environ.get('GROWTH_AGENT_ALIAS'),
        'model': 'us.anthropic.claude-haiku-4-5-20251001-v1:0',
        'description': 'Growth and profitability expert'
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Supervisor Agent Configuration (Sonnet 4.5)
# Note: Knowledge base temporarily disabled
# ─────────────────────────────────────────────────────────────────────────────
SUPERVISOR_AGENT_CONFIG: Dict[str, Any] = {
    'agent_id': os.environ.get('SUPERVISOR_AGENT_ID'),
    'agent_alias': os.environ.get('SUPERVISOR_AGENT_ALIAS'),
    'model': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',
    'description': 'Supervisor agent - synthesizes expert analyses with Buffett principles',
    'has_knowledge_base': False
}

# ─────────────────────────────────────────────────────────────────────────────
# Legacy Agent Config (for backward compatibility)
# ─────────────────────────────────────────────────────────────────────────────
AGENT_CONFIG = EXPERT_AGENT_CONFIG  # Alias for legacy code

# ─────────────────────────────────────────────────────────────────────────────
# Feature Flags
# ─────────────────────────────────────────────────────────────────────────────
SUPERVISOR_ENABLED = os.environ.get('SUPERVISOR_ENABLED', 'false').lower() == 'true'
ORCHESTRATION_MODE = os.environ.get('ORCHESTRATION_MODE', 'single')  # 'single', 'parallel', 'supervisor'
USE_VALUE_INVESTOR_FORMAT = os.environ.get('USE_VALUE_INVESTOR_FORMAT', 'true').lower() == 'true'

# Action group mode toggle for expert agents
# True: Agents call action groups with skip_inference=true (hybrid mode - action groups provide metrics only)
# False: Pre-computed mode (everything passed in user message, no action group calls)
USE_ACTION_GROUP_MODE = os.environ.get('USE_ACTION_GROUP_MODE', 'true').lower() == 'true'


def get_agent_config(agent_type: str) -> Optional[Dict[str, Any]]:
    """Get configuration for a specific agent type."""
    if agent_type == 'supervisor':
        return SUPERVISOR_AGENT_CONFIG
    return EXPERT_AGENT_CONFIG.get(agent_type)


def is_agent_configured(agent_type: str) -> bool:
    """Check if an agent is properly configured."""
    config = get_agent_config(agent_type)
    if not config:
        return False
    return bool(config.get('agent_id') and config.get('agent_alias'))
