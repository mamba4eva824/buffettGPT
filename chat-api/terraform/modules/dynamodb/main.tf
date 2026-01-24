# DynamoDB Module - Consolidated Table Management
# Conservative cleanup: Removed deprecated RAG chatbot tables
#
# Tables are managed in separate files:
# - conversations.tf: conversations table (ACTIVE)
# - messages.tf: chat_messages table (ACTIVE - re-added for Research history)
# - ml_tables.tf: financial_data_cache, ticker_lookup, forex_cache,
#                 idempotency_cache, metrics_history_cache (ACTIVE)
# - reports_table.tf: investment_reports_v2 (ACTIVE, v1 removed)

# ================================================
# ARCHIVED TABLES (Removed 2025-01)
# ================================================
# The following tables were removed as part of the RAG chatbot
# deprecation. They are no longer used by the current architecture
# (Prediction Ensemble + Investment Research):
#
# - chat_sessions: Replaced by conversations table
# - websocket_connections: WebSocket API kept but table unused
# - enhanced_rate_limits: Rate limiting not used by new architecture
# - anonymous_sessions: Not used by new architecture
#
# NOTE: chat_messages was re-added (2025-01) - required for storing
# Research report JSON data and enabling history retrieval
# ================================================
