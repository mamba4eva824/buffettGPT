"""
Unified Tool Executor

Merges the follow-up agent's 6 tools and market intel agent's 9 tools into
a single dispatcher with dynamic tool filtering by agent_type.

Tool routing:
  - Follow-up tools (6): getReportSection, getReportRatings, getMetricsHistory,
    getAvailableReports, compareStocks, getFinancialSnapshot
  - Market intel tools (9): screenStocks, getSectorOverview, getTopCompanies,
    getIndexSnapshot, getCompanyProfile, compareCompanies, getMetricTrend,
    getEarningsSurprises, compareSectors
"""

import logging
from typing import Any, Dict, List

from utils.tool_executor import execute_tool as followup_execute

logger = logging.getLogger(__name__)

# Tool name sets for routing
FOLLOWUP_TOOL_NAMES = {
    'getReportSection',
    'getReportRatings',
    'getMetricsHistory',
    'getAvailableReports',
    'compareStocks',
    'getFinancialSnapshot',
}

MARKET_INTEL_TOOL_NAMES = {
    'screenStocks',
    'getSectorOverview',
    'getTopCompanies',
    'getIndexSnapshot',
    'getCompanyProfile',
    'compareCompanies',
    'getMetricTrend',
    'getEarningsSurprises',
    'compareSectors',
    'getHistoricalValuation',
}

# Company tab agent_type values that should get follow-up tools + getCompanyProfile
COMPANY_TAB_TYPES = {
    'growth',
    'profitability',
    'valuation',
    'cashflow',
    'debt',
    'earnings_quality',
    'moat',
    'dashboard',
    'triggers',
}


def _get_followup_tool_definitions() -> Dict:
    """Lazy-import follow-up tool definitions from the handler module."""
    from handlers.analysis_followup import FOLLOWUP_TOOLS
    return FOLLOWUP_TOOLS


def _get_market_intel_tool_definitions() -> Dict:
    """Lazy-import market intel tool definitions from the handler module."""
    from handlers.market_intel_chat import MARKET_INTEL_TOOLS
    return MARKET_INTEL_TOOLS


def _find_tool_spec_by_name(tool_config: Dict, name: str) -> Dict:
    """Extract a single toolSpec entry from a Bedrock Converse API toolConfig dict."""
    for tool in tool_config.get('tools', []):
        spec = tool.get('toolSpec', {})
        if spec.get('name') == name:
            return tool
    return {}


def get_tools_for_context(agent_type: str) -> Dict:
    """
    Return Bedrock Converse API toolConfig with tools filtered by agent_type.

    Args:
        agent_type: The context identifier. One of:
            - A company tab type (growth, profitability, valuation, cashflow,
              debt, earnings_quality, moat, dashboard, triggers):
              Returns all 6 follow-up tools + getCompanyProfile from market intel.
            - 'market-intelligence': Returns all 9 market intel tools.
            - Any other value: Returns all 15 tools.

    Returns:
        A Bedrock Converse API toolConfig dict: {"tools": [{"toolSpec": {...}}, ...]}
    """
    followup_defs = _get_followup_tool_definitions()
    market_intel_defs = _get_market_intel_tool_definitions()

    if agent_type in COMPANY_TAB_TYPES:
        # All follow-up tools + getCompanyProfile from market intel
        tools = list(followup_defs.get('tools', []))
        company_profile_spec = _find_tool_spec_by_name(market_intel_defs, 'getCompanyProfile')
        if company_profile_spec:
            tools.append(company_profile_spec)
        return {"tools": tools}

    elif agent_type == 'market-intelligence':
        return dict(market_intel_defs)

    else:
        # Default: all 15 tools
        tools = list(followup_defs.get('tools', []))
        tools.extend(market_intel_defs.get('tools', []))
        return {"tools": tools}


def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route a tool call to the correct underlying executor.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Parameters for the tool

    Returns:
        Tool result dict with success/error status
    """
    if tool_name in FOLLOWUP_TOOL_NAMES:
        return followup_execute(tool_name, tool_input)

    if tool_name in MARKET_INTEL_TOOL_NAMES:
        from utils.market_intel_tools import execute_tool as market_intel_execute
        return market_intel_execute(tool_name, tool_input)

    logger.warning(f"Unknown tool requested: {tool_name}")
    return {
        "success": False,
        "error": f"Unknown tool: {tool_name}"
    }
