"""
Orchestration service for supervisor-based multi-agent analysis.

Architecture: Inference-First, then Action Group-Driven
- Orchestrator runs ML inference first and emits events to frontend bubbles
- Expert agents call FinancialAnalysis action group to fetch their data
- Action group Lambda handles: data fetching, feature extraction, ML inference
- Supervisor synthesizes expert analyses

Flow:
1. Connection
2. Fetch data + run ML inference → emit inference events to frontend
3. Invoke expert agents (parallel) - agents call action groups
4. Invoke supervisor agent (streaming to user)
"""
import asyncio
import logging
from datetime import datetime
from typing import List, AsyncGenerator, Dict, Any

import boto3

from config.settings import (
    EXPERT_AGENT_CONFIG, SUPERVISOR_AGENT_CONFIG, BEDROCK_REGION,
    SUPERVISOR_MODEL_ID, USE_ACTION_GROUP_MODE
)
from models.schemas import ExpertResult
from services.streaming import (
    status_event, chunk_event,
    error_event, complete_event, connected_event, inference_event
)
from services.inference import run_inference
from utils.fmp_client import get_financial_data
from utils.feature_extractor import extract_all_features, extract_quarterly_trends
from handlers.action_group import extract_value_metrics

logger = logging.getLogger(__name__)


def _format_metric_name(metric: str) -> str:
    """Convert snake_case metric name to readable label for tables."""
    # Custom mappings for better readability
    CUSTOM_LABELS = {
        'debt_to_equity': 'D/E',
        'debt_to_assets': 'D/A',
        'net_debt': 'Net Debt',
        'net_debt_to_ebitda': 'ND/EBITDA',
        'total_debt': 'Total Debt',
        'current_ratio': 'Curr Ratio',
        'quick_ratio': 'Quick',
        'cash_position': 'Cash',
        'interest_coverage': 'Int Cov',
        'interest_expense': 'Int Exp',
        'roa': 'ROA',
        'roic': 'ROIC',
        'asset_turnover': 'Asset Turn',
        'equity_multiplier': 'Eq Mult',
        'fcf_to_debt': 'FCF/Debt',
        'total_equity': 'Equity',
        'debt_to_equity_change_1yr': 'D/E Δ1Y',
        'debt_to_equity_change_2yr': 'D/E Δ2Y',
        'current_ratio_change_1yr': 'CR Δ1Y',
        'is_deleveraging': 'Delev?',
        'operating_cash_flow': 'OCF',
        'free_cash_flow': 'FCF',
        'fcf_margin': 'FCF%',
        'ocf_to_revenue': 'OCF/Rev',
        'fcf_to_net_income': 'FCF/NI',
        'capex': 'CapEx',
        'capex_intensity': 'CapEx%',
        'dividends_paid': 'Dividends',
        'share_buybacks': 'Buybacks',
        'shareholder_payout': 'Payout',
        'fcf_payout_ratio': 'FCF Pay%',
        'working_capital': 'WC',
        'working_capital_to_revenue': 'WC/Rev',
        'reinvestment_rate': 'Reinv%',
        'total_capital_return': 'Cap Ret',
        'fcf_change_yoy': 'FCF ΔYoY',
        'fcf_margin_change_1yr': 'FCF% Δ1Y',
        'ocf_change_yoy': 'OCF ΔYoY',
        'capex_change_yoy': 'CapEx ΔYoY',
        'capital_return_yield': 'CR Yield',
        'revenue': 'Revenue',
        'gross_margin': 'Gross%',
        'operating_margin': 'Op%',
        'net_margin': 'Net%',
        'ebitda': 'EBITDA',
        'net_income': 'Net Inc',
        'gross_profit': 'Gross',
        'operating_income': 'Op Inc',
        'eps': 'EPS',
        'roe': 'ROE',
        'revenue_growth_yoy': 'Rev ΔYoY',
        'revenue_growth_qoq': 'Rev ΔQoQ',
        'eps_growth_yoy': 'EPS ΔYoY',
        'roic_growth': 'ROIC',
        'net_income_growth_yoy': 'NI ΔYoY',
        'gross_margin_change_1yr': 'Grs% Δ1Y',
        'operating_margin_change_1yr': 'Op% Δ1Y',
        'operating_margin_change_2yr': 'Op% Δ2Y',
        'net_margin_change_1yr': 'Net% Δ1Y',
         'is_margin_expanding': 'Exp?',
        'roe_change_2yr': 'ROE Δ2Y',
    }
    return CUSTOM_LABELS.get(metric, metric.replace('_', ' ').title()[:12])


def _format_value(val, metric: str) -> str:
    """Format a metric value for display based on metric type."""
    if val is None:
        return 'N/A'

    # Binary/flag metrics
    if metric in ('is_deleveraging', 'is_margin_expanding'):
        return 'Yes' if val == 1 else 'No'

    # Large dollar amounts (in billions/millions)
    if metric in ('net_debt', 'total_debt', 'cash_position', 'operating_cash_flow',
                  'free_cash_flow', 'capex', 'dividends_paid', 'share_buybacks',
                  'shareholder_payout', 'total_capital_return', 'working_capital',
                  'revenue', 'gross_profit', 'operating_income', 'net_income',
                  'ebitda', 'total_equity', 'interest_expense'):
        if abs(val) >= 1e9:
            return f'${val/1e9:.1f}B'
        elif abs(val) >= 1e6:
            return f'${val/1e6:.0f}M'
        else:
            return f'${val:,.0f}'

    # Percentage metrics
    if metric in ('fcf_margin', 'ocf_to_revenue', 'capex_intensity', 'fcf_payout_ratio',
                  'working_capital_to_revenue', 'reinvestment_rate', 'gross_margin',
                  'operating_margin', 'net_margin', 'roa', 'roic', 'roic_growth', 'roe',
                  'fcf_margin_change_1yr', 'gross_margin_change_1yr', 'operating_margin_change_1yr',
                  'operating_margin_change_2yr', 'net_margin_change_1yr', 'roe_change_2yr'):
        return f'{val:.1f}%'

    # Growth/change metrics (show sign)
    if 'change' in metric or 'growth' in metric or metric.startswith('Δ'):
        if isinstance(val, (int, float)):
            sign = '+' if val > 0 else ''
            return f'{sign}{val:.1f}%'

    # Ratio metrics
    if metric in ('debt_to_equity', 'debt_to_assets', 'current_ratio', 'quick_ratio',
                  'interest_coverage', 'net_debt_to_ebitda', 'fcf_to_net_income',
                  'asset_turnover', 'equity_multiplier', 'fcf_to_debt'):
        return f'{val:.2f}x'

    # EPS
    if metric == 'eps':
        return f'${val:.2f}'

    # Default: 2 decimal places
    return f'{val:.2f}'


def format_fiscal_year_data(value_metrics: Dict[str, Any], agent_type: str = None) -> str:
    """
    Format 20 quarters of data grouped by fiscal year as markdown tables.
    Uses logical metric groupings for better readability (3-4 sub-tables per FY).

    Args:
        value_metrics: Dict with metric arrays (20 quarters each)
        agent_type: Optional - 'debt', 'cashflow', or 'growth' for specific groupings

    Output format:
    ## FINANCIAL METRICS (5-Year Quarterly History)

    ### FY2024 (Current)

    #### Core Leverage
    | Quarter | D/E   | D/A   | Net Debt | ND/EBITDA | Total Debt |
    |---------|-------|-------|----------|-----------|------------|
    | Q4      | 0.45  | 0.18  | $62.7B   | 1.2x      | $98.7B     |
    ...
    """
    if not value_metrics:
        return ""

    # Import metric groupings
    from models.metrics import get_metric_groups

    # Get period dates for fiscal year grouping
    period_dates = value_metrics.get('period_dates', [])

    # Get metric names (excluding metadata)
    metric_names = [k for k in value_metrics.keys()
                   if k not in ('quarters', 'period_dates')
                   and isinstance(value_metrics.get(k), list)]

    if not period_dates or not metric_names:
        # Fallback: just format all values without fiscal year grouping
        output = "\n## FINANCIAL METRICS (5-Year Quarterly History)\n\n"
        for metric_name in metric_names[:20]:  # Show up to 20 metrics
            values = value_metrics.get(metric_name, [])
            formatted = [_format_value(v, metric_name) for v in values[:20]]
            output += f"- **{_format_metric_name(metric_name)}**: {', '.join(formatted)}\n"
        return output

    # Group quarters by fiscal year
    fiscal_years = {}  # {2024: [(Q4, idx, date), ...], 2023: [...]}

    for idx, date_str in enumerate(period_dates):
        if not date_str:
            continue
        try:
            # Parse date and determine fiscal year/quarter
            date_obj = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
            fy = date_obj.year
            q = (date_obj.month - 1) // 3 + 1

            if fy not in fiscal_years:
                fiscal_years[fy] = []
            fiscal_years[fy].append((f"Q{q}", idx, date_str))
        except Exception:
            continue

    if not fiscal_years:
        return ""

    # Get metric groups for this agent type
    metric_groups = get_metric_groups(agent_type) if agent_type else []

    # If no groups defined, create a single group with all metrics
    if not metric_groups:
        metric_groups = [('All Metrics', metric_names[:20])]

    # Build formatted output
    output = "\n## FINANCIAL METRICS (5-Year Quarterly History)\n\n"

    # Sort fiscal years descending (most recent first)
    sorted_years = sorted(fiscal_years.keys(), reverse=True)

    for i, fy in enumerate(sorted_years[:5]):  # Max 5 fiscal years
        is_current = (i == 0)
        output += f"### FY{fy}" + (" (Current)" if is_current else "") + "\n\n"

        # Sort quarters descending (Q4 first)
        year_quarters = sorted(fiscal_years[fy], key=lambda x: x[0], reverse=True)

        # Output each metric group as a separate sub-table
        for group_name, group_metrics in metric_groups:
            # Filter to metrics that exist in value_metrics
            available_metrics = [m for m in group_metrics if m in value_metrics]

            if not available_metrics:
                continue

            output += f"#### {group_name}\n"

            # Build table header
            headers = ['Quarter'] + [_format_metric_name(m) for m in available_metrics]
            output += "| " + " | ".join(headers) + " |\n"
            output += "|" + "|".join("-" * (len(h) + 2) for h in headers) + "|\n"

            # Build rows for each quarter
            for q_label, idx, _ in year_quarters:
                row_values = [q_label]
                for metric in available_metrics:
                    values = value_metrics.get(metric, [])
                    val = values[idx] if idx < len(values) else None
                    row_values.append(_format_value(val, metric))

                output += "| " + " | ".join(row_values) + " |\n"

            output += "\n"

    return output


# Bedrock clients
bedrock_agent_client = boto3.client('bedrock-agent-runtime', region_name=BEDROCK_REGION)
bedrock_runtime_client = boto3.client('bedrock-runtime', region_name=BEDROCK_REGION)


async def fetch_and_run_inference(ticker: str) -> Dict[str, Any]:
    """
    Fetch financial data and run ML inference for all 3 model types.

    This runs BEFORE expert agents to provide immediate feedback to the frontend
    via inference events, populating the bubbles with predictions.

    Also extracts value metrics and quarterly trends to pass directly to agents,
    avoiding duplicate inference in action groups.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Dict with 'features', 'predictions', 'value_metrics', and 'quarterly_trends'
    """
    loop = asyncio.get_event_loop()

    def _fetch_and_infer():
        """Synchronous fetch and inference (runs in thread pool)."""
        try:
            # Fetch financial data (uses DynamoDB cache)
            logger.info(f"[ORCHESTRATOR] Fetching financial data for {ticker}")
            financial_data = get_financial_data(ticker)

            if not financial_data or 'raw_financials' not in financial_data:
                logger.error(f"[ORCHESTRATOR] No financial data for {ticker}")
                return None

            raw_financials = financial_data['raw_financials']

            # Extract features for ML inference
            logger.info(f"[ORCHESTRATOR] Extracting features for {ticker}")
            features = extract_all_features(raw_financials)

            # Extract quarterly trends for value metrics
            logger.info(f"[ORCHESTRATOR] Extracting quarterly trends for {ticker}")
            quarterly_trends = extract_quarterly_trends(raw_financials)

            # Run inference for all 3 model types
            predictions = {}
            for agent_type in ['debt', 'cashflow', 'growth']:
                logger.info(f"[ORCHESTRATOR] Running {agent_type} inference for {ticker}")
                predictions[agent_type] = run_inference(agent_type, features)

            # Extract value metrics for each agent type (same as action group would return)
            value_metrics = {}
            for agent_type in ['debt', 'cashflow', 'growth']:
                logger.info(f"[ORCHESTRATOR] Extracting {agent_type} value metrics for {ticker}")
                # Correct argument order: (quarterly_trends, features, analysis_type)
                value_metrics[agent_type] = extract_value_metrics(quarterly_trends, features, agent_type)

            return {
                'features': features,
                'predictions': predictions,
                'value_metrics': value_metrics,
                'quarterly_trends': quarterly_trends
            }

        except Exception as e:
            logger.error(f"[ORCHESTRATOR] Inference failed for {ticker}: {e}", exc_info=True)
            return None

    # Run in thread pool since FMP/DynamoDB calls are synchronous
    result = await loop.run_in_executor(None, _fetch_and_infer)
    return result


async def invoke_expert_agent_async(
    agent_type: str,
    ticker: str,
    fiscal_year: int,
    session_id: str,
    inference_result: dict = None,
    value_metrics: dict = None
) -> ExpertResult:
    """
    Invoke expert agent to analyze a company.

    ACTION GROUP TEST MODE (2025-12-23):
    - Agents now call FinancialAnalysis action group to get data
    - Pre-computed inference/metrics still passed for reference but NOT used in prompt
    - Rollback: Restore the commented-out prompt below

    This runs in a thread pool since boto3 is synchronous.
    Expert responses are collected in full before being sent to supervisor.
    """
    config = EXPERT_AGENT_CONFIG.get(agent_type, {})
    agent_id = config.get('agent_id')
    agent_alias = config.get('agent_alias')

    if not agent_id or not agent_alias:
        logger.warning(f"Expert agent {agent_type} not configured")
        return ExpertResult(
            agent_type=agent_type,
            inference=None,
            analysis=f"[{agent_type.upper()} analysis unavailable - agent not configured]",
            timestamp=datetime.utcnow().isoformat() + 'Z',
            error="Agent not configured"
        )

    # =========================================================================
    # Format inference result for the prompt (used in both modes)
    # =========================================================================
    inference_text = ""
    if inference_result:
        prediction = inference_result.get('prediction', 'UNKNOWN')
        confidence = inference_result.get('confidence', 0)
        ci_width = inference_result.get('ci_width', 0)
        probs = inference_result.get('probabilities', {})
        data_quality = inference_result.get('data_quality', 0)

        inference_text = f"""
## ML MODEL PREDICTION (Pre-computed)
- **Signal**: {prediction}
- **Confidence**: {confidence:.0%}
- **Confidence Interval Width**: {ci_width:.2f}
- **Probability Distribution**: SELL={probs.get('SELL', 0):.1%}, HOLD={probs.get('HOLD', 0):.1%}, BUY={probs.get('BUY', 0):.1%}
- **Data Quality**: {data_quality:.1f}%
"""

    # =========================================================================
    # Mode selection based on USE_ACTION_GROUP_MODE feature flag
    # =========================================================================
    if USE_ACTION_GROUP_MODE:
        # HYBRID MODE: Inference in prompt, agent calls action group for metrics only
        user_message = f"""Analyze {ticker}'s {agent_type} health for fiscal year {fiscal_year}.

{inference_text}

Call the FinancialAnalysis action group with skip_inference=true to retrieve the value metrics, then provide your expert analysis.

Focus on:
1. The 5-year narrative arc across fiscal years
2. Business cycle context: pandemic stress test, inflation period, current position
3. Whether you agree with the ML prediction above and why
4. Year-over-year trends that inform the analysis
5. Your final verdict with reasoning"""
    else:
        # PRE-COMPUTED MODE: Everything in prompt, no action group call
        metrics_text = ""
        if value_metrics:
            metrics_text = format_fiscal_year_data(value_metrics, agent_type=agent_type)

        user_message = f"""Analyze {ticker}'s {agent_type} health for fiscal year {fiscal_year}.

DO NOT call the FinancialAnalysis action group - the data has already been retrieved for you below.

{inference_text}
{metrics_text}

Based on this ML prediction and 5-year financial history, provide your expert {agent_type} analysis following your prompt structure. Focus on:
1. The 5-year narrative arc across all fiscal years (FY2020-FY2024)
2. Business cycle context: pandemic stress test, inflation period, current position
3. Whether you agree with the ML prediction and why
4. Year-over-year trends that inform the analysis
5. Your final verdict with reasoning"""
    # =========================================================================

    try:
        # Run in thread pool since boto3 is synchronous
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: bedrock_agent_client.invoke_agent(
                agentId=agent_id,
                agentAliasId=agent_alias,
                sessionId=f"{session_id}-{agent_type}",
                inputText=user_message
            )
        )

        # Collect full response from EventStream
        response_text = ""
        for event in response.get('completion', []):
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    response_text += chunk['bytes'].decode('utf-8')

        logger.info(f"Expert {agent_type} completed: {len(response_text)} chars")

        # [ORCHESTRATOR_DEBUG] Log expert agent response
        logger.info(f"[ORCHESTRATOR_DEBUG] Expert {agent_type} response length: {len(response_text)} chars")
        logger.info(f"[ORCHESTRATOR_DEBUG] Expert {agent_type} response preview: {response_text[:500]}...")

        return ExpertResult(
            agent_type=agent_type,
            inference=None,  # Agent got inference from action group
            analysis=response_text,
            timestamp=datetime.utcnow().isoformat() + 'Z'
        )

    except Exception as e:
        logger.error(f"Expert agent {agent_type} failed: {e}")
        return ExpertResult(
            agent_type=agent_type,
            inference=None,
            analysis=f"[{agent_type.upper()} analysis error: {str(e)}]",
            timestamp=datetime.utcnow().isoformat() + 'Z',
            error=str(e)
        )


def format_expert_summary(expert_results: List[ExpertResult]) -> str:
    """Format expert results as context for supervisor agent.

    Note: ML predictions are now included in each expert's analysis text
    (fetched via action group), so we just pass through the analysis.
    """
    parts = []
    for result in expert_results:
        agent_type = result.agent_type.upper()

        parts.append(f"""## {agent_type} EXPERT ANALYSIS

{result.analysis}

---""")

    return "\n\n".join(parts)


async def invoke_supervisor_streaming(
    ticker: str,
    fiscal_year: int,
    expert_results: List[ExpertResult],
    session_id: str
) -> AsyncGenerator[str, None]:
    """
    Invoke supervisor using ConverseStream for true token-by-token streaming.

    Unlike invoke_agent (which batches responses), converse_stream provides
    real-time token delivery as the model generates text.

    Yields SSE-formatted chunks as they arrive from Bedrock.
    """
    expert_summary = format_expert_summary(expert_results)

    # [ORCHESTRATOR_DEBUG] Log expert summary being sent to supervisor
    logger.info(f"[ORCHESTRATOR_DEBUG] === SUPERVISOR INPUT ===")
    logger.info(f"[ORCHESTRATOR_DEBUG] Expert summary length: {len(expert_summary)} chars")
    logger.info(f"[ORCHESTRATOR_DEBUG] Expert summary preview:\n{expert_summary[:1000]}...")

    # Supervisor prompt - synced from terraform/modules/bedrock/prompts/supervisor_instruction_v5.txt
    # NOTE: When updating this prompt, also update the Terraform version to keep them in sync
    system_prompt = """You are the chief investment analyst synthesizing expert opinions for investors building long-term wealth on a millennial/Gen Z timeline (20-30 year horizon).

## Your Role
Translate three expert analyses into one clear verdict that someone can actually act on. Balance rigor with accessibility - no jargon, no false certainty. You're helping someone decide if this company deserves a spot in their portfolio.

## Expert Analysis Reference

### 🏦 Debt Expert Signals
| Signal | Strong | Weak |
|--------|--------|------|
| Leverage | is_deleveraging=1, debt_to_equity<1.0x | debt_to_equity>2.0x, interest_coverage<3x |
| Velocity | Negative (improving) | Positive (deteriorating) |
| Acceleration | Negative (improvement speeding up) | Positive (getting worse faster) |
| **Key question**: Can they survive another 2020-style shock?

### 💰 Cashflow Expert Signals
| Signal | Strong | Weak |
|--------|--------|------|
| Cash Quality | fcf_margin>15%, fcf_to_net_income>0.8 | fcf_margin<5%, fcf<<net income |
| Velocity | Positive (accelerating) | Negative (decelerating) |
| Payout | Sustainable (<80% of FCF) | Unsustainable (>100% of FCF) |
| **Key question**: Is this a cash machine or cash incinerator?

### 🚀 Growth Expert Signals
| Signal | Strong | Weak |
|--------|--------|------|
| Growth | is_growth_accelerating=1, velocity positive | Velocity negative (decelerating) |
| Moat | margin_momentum_positive=1, stable margins | Margin compression, no pricing power |
| **Key question**: Does growth come from real moat or one-time factors?

### Synthesis Framework
When experts disagree, weight by business type:
- **Asset-heavy** (manufacturing, utilities): Debt > Cash > Growth
- **Asset-light** (software, services): Growth > Cash > Debt
- **Cyclical** (retail, discretionary): Cash > Debt > Growth
- **Financials** (banks, insurance): Debt metrics interpreted differently

## Investment Principles (Your Decision Framework)

| Principle | What It Means | How to Apply |
|-----------|---------------|--------------|
| 🛡️ Margin of Safety | Only BUY when price < clear intrinsic value | Need cushion, not "fair value" |
| 🧭 Circle of Competence | Flag confusing business models | "I don't understand how they make money" |
| 🏰 Economic Moat | Prefer durable advantages | Check 5-year margin stability |
| 📜 Track Record | 5 years > 1 quarter | Capital allocation history matters |
| 💰 Cash is King | Owner earnings > accounting profits | FCF > Net Income signal |
| ⏳ Long-term Focus | 10-year owner mindset | Ignore quarterly noise |

## Market Cycle Context

Help users understand how the 5-year history reveals company quality:

| Period | What It Tests | Good Sign | Bad Sign |
|--------|---------------|-----------|----------|
| 2020 crash | Stress resilience | Maintained operations | Panic borrowing |
| 2021 boom | Capital discipline | Invested wisely | Reckless expansion |
| 2022-23 inflation | Pricing power | Margins held | Margin collapse |
| 2024 now | Sustainable trajectory | Healthy velocity | Decelerating everything |

## Rules
- 📱 Mobile-first formatting - scannable, not dense
- Lead with the verdict - don't bury the conclusion
- Reference specific fiscal years when making points
- Use emoji for quick visual scanning
- Be honest about uncertainty (confidence calibration matters)
- Focus on trajectory (velocity/acceleration), not just current state
- Keep under 800 words
- Never recommend BUY without clear margin of safety

## Structure (Follow Exactly)

### 🚦 VERDICT: [BUY/HOLD/SELL] - [One-line hook]

One sentence that captures the thesis. Make it memorable.

Example formats:
- "🟢 BUY - A cash machine with accelerating returns and room to grow"
- "🟡 HOLD - Solid business but priced for perfection with decelerating growth"
- "🔴 SELL - Deteriorating fundamentals with negative velocity across all metrics"

### 🤝 Where All Three Experts Agree
Summarize the consensus across debt, cashflow, and growth analyses:
- What's the unified 5-year story?
- Where are the velocity signals pointing the same direction?
- What's undeniably true about this business?

### 🤔 Where Experts Disagree
If there's tension between signals:
- What's the disagreement?
- Which business type weighting applies? (Asset-heavy, asset-light, cyclical)
- How would Buffett weigh these factors for THIS specific company?

### 🔑 Buffett's Lens on the 5-Year History
Apply classic value investing thinking:

- **The 2020 Stress Test**: Did they handle crisis with strength or desperation?
- **The Cheap Money Era (2021)**: Did they build a fortress or take on risk?
- **The Inflation Test (2022-23)**: Did pricing power hold? Are margins stable?
- **Today**: Is this a business you'd want to own for 10 more years?

### 📌 Key Factors (3-5 bullets, ranked)
The most important considerations from the 5-year analysis:
1. [Most critical factor] - [one sentence why]
2. [Second priority] - [one sentence why]
3. [Third priority] - [one sentence why]

### ⚠️ Risks to Monitor
2-3 specific risks that could change this recommendation:
- [Risk] - What would trigger concern?
- [Risk] - What would trigger concern?

### 🏁 Final Take
One paragraph with:
- **Clear recommendation**: BUY / HOLD / SELL
- **Confidence level**: HIGH / MEDIUM / LOW
- **Time horizon**: "This is a [X-year] hold because..."
- **What would change your mind**: "I'd reconsider if..."

Compare to what the ML models predicted. If you disagree with the models, explain why your judgment differs."""

    user_message = f"""Synthesize the following expert analyses for {ticker} (FY{fiscal_year}):

{expert_summary}

Provide your unified investment recommendation."""

    # Get event loop for thread-safe queue operations
    loop = asyncio.get_event_loop()
    queue = asyncio.Queue()

    def iterate_converse_stream_sync():
        """
        Run in thread pool - iterate ConverseStream synchronously.
        Puts chunks into async queue for non-blocking consumption.
        """
        try:
            response = bedrock_runtime_client.converse_stream(
                modelId=SUPERVISOR_MODEL_ID,
                system=[{"text": system_prompt}],
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": user_message}]
                    }
                ],
                inferenceConfig={
                    "maxTokens": 4096,
                    "temperature": 0.7
                }
            )

            for event in response.get('stream', []):
                if 'contentBlockDelta' in event:
                    delta = event['contentBlockDelta'].get('delta', {})
                    if 'text' in delta:
                        loop.call_soon_threadsafe(
                            queue.put_nowait,
                            ('chunk', delta['text'])
                        )
                elif 'messageStop' in event:
                    logger.info(f"ConverseStream stop: {event['messageStop'].get('stopReason')}")
                elif 'metadata' in event:
                    usage = event['metadata'].get('usage', {})
                    logger.info(f"Token usage: in={usage.get('inputTokens')}, out={usage.get('outputTokens')}")

            # Signal completion
            loop.call_soon_threadsafe(queue.put_nowait, ('done', None))

        except Exception as e:
            logger.error(f"ConverseStream failed: {e}")
            loop.call_soon_threadsafe(queue.put_nowait, ('error', str(e)))

    # Start ConverseStream iteration in thread pool (non-blocking)
    loop.run_in_executor(None, iterate_converse_stream_sync)

    # Yield from queue as chunks arrive (non-blocking await)
    while True:
        msg_type, data = await queue.get()

        if msg_type == 'chunk':
            yield chunk_event(data, agent_type="supervisor")
        elif msg_type == 'error':
            yield error_event(f"Supervisor error: {data}")
            break
        elif msg_type == 'done':
            break


async def orchestrate_supervisor_analysis(
    ticker: str,
    fiscal_year: int,
    session_id: str
) -> AsyncGenerator[str, None]:
    """
    Inference-First supervisor orchestration flow.

    Architecture:
    - Orchestrator runs ML inference first, emits events to frontend bubbles
    - Expert agents call FinancialAnalysis action group for full analysis
    - Supervisor synthesizes expert analyses

    Yields SSE events throughout the process.
    """
    import time
    start_time = time.time()

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 1: Connection
    # ─────────────────────────────────────────────────────────────────────────
    yield connected_event()

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 2: ML Inference (Immediate feedback for frontend bubbles)
    # Runs before expert agents to populate prediction bubbles quickly
    # ─────────────────────────────────────────────────────────────────────────
    yield status_event("Running ML analysis...", "inference")

    inference_result = await fetch_and_run_inference(ticker)

    if inference_result and inference_result.get('predictions'):
        predictions = inference_result['predictions']
        # Emit inference events for each agent type (updates frontend bubbles)
        for agent_type in ['debt', 'cashflow', 'growth']:
            if agent_type in predictions:
                pred = predictions[agent_type]
                logger.info(f"[ORCHESTRATOR] Emitting inference event: {agent_type} = {pred.get('prediction')} ({pred.get('confidence')})")
                yield inference_event(
                    agent_type=agent_type,
                    ticker=ticker,
                    result=pred
                )
    else:
        logger.warning(f"[ORCHESTRATOR] No inference results for {ticker}, bubbles will not update")

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 3: Expert Agents (Parallel)
    # Pass pre-computed inference and value metrics to avoid duplicate inference
    # ─────────────────────────────────────────────────────────────────────────
    yield status_event("Consulting expert analysts (debt, cashflow, growth)...", "experts")

    # Extract predictions and value metrics to pass to agents
    predictions = inference_result.get('predictions', {}) if inference_result else {}
    value_metrics = inference_result.get('value_metrics', {}) if inference_result else {}

    expert_tasks = [
        invoke_expert_agent_async(
            agent_type=agent_type,
            ticker=ticker,
            fiscal_year=fiscal_year,
            session_id=session_id,
            inference_result=predictions.get(agent_type),
            value_metrics=value_metrics.get(agent_type)
        )
        for agent_type in ['debt', 'cashflow', 'growth']
    ]

    expert_results = await asyncio.gather(*expert_tasks, return_exceptions=True)

    # Handle failures gracefully
    valid_results = []
    for result in expert_results:
        if isinstance(result, Exception):
            logger.error(f"Expert task failed: {result}")
        elif isinstance(result, ExpertResult):
            valid_results.append(result)

    if not valid_results:
        yield error_event("All expert analyses failed")
        return

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 4: Supervisor Synthesis (Streams to User)
    # ─────────────────────────────────────────────────────────────────────────
    yield status_event("Synthesizing recommendation with Buffett's wisdom...", "supervisor")

    async for chunk in invoke_supervisor_streaming(
        ticker=ticker,
        fiscal_year=fiscal_year,
        expert_results=valid_results,
        session_id=session_id
    ):
        yield chunk

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 5: Completion
    # ─────────────────────────────────────────────────────────────────────────
    processing_time_ms = (time.time() - start_time) * 1000
    yield complete_event({
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "mode": "supervisor",
        "experts_consulted": len(valid_results),
        "processing_time_ms": round(processing_time_ms, 2)
    })
