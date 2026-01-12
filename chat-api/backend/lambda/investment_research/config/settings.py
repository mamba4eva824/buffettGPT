"""
Configuration settings for Investment Research Lambda.

Environment variables:
- ENVIRONMENT: dev/staging/prod (default: dev)
- PROJECT_NAME: Project identifier (default: buffett-chat-api)
- LOG_LEVEL: Logging level (default: INFO)
- INVESTMENT_REPORTS_TABLE: DynamoDB table name for cached reports
"""
import os
from datetime import datetime

# Environment
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# AWS Region
AWS_REGION = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))

# DynamoDB - v1 table (single blob storage)
INVESTMENT_REPORTS_TABLE = os.environ.get(
    'INVESTMENT_REPORTS_TABLE',
    f'investment-reports-{ENVIRONMENT}'
)

# DynamoDB - v2 table (section-per-item storage for progressive loading)
# Note: Terraform sets INVESTMENT_REPORTS_V2_TABLE, but we also support the alternative naming
INVESTMENT_REPORTS_TABLE_V2 = os.environ.get(
    'INVESTMENT_REPORTS_V2_TABLE',  # Terraform naming
    os.environ.get('INVESTMENT_REPORTS_TABLE_V2', f'investment-reports-v2-{ENVIRONMENT}')  # Fallback
)

# Default fiscal year for report lookups
DEFAULT_FISCAL_YEAR = datetime.now().year

# Lambda Web Adapter settings (for reference)
LWA_PORT = int(os.environ.get('PORT', os.environ.get('AWS_LWA_PORT', '8080')))
