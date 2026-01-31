#!/usr/bin/env python3
"""
Interactive Ensemble Testing for Claude Code

This module is designed to be run directly in Claude Code for interactive testing.
It outputs formatted prompts and data that you can then ask Claude Code to analyze.

Usage in Claude Code:
  1. Run: python chat-api/backend/prediction_ensemble_local/interactive.py AAPL
  2. Copy the output for each agent
  3. Ask Claude Code to act as that agent and provide analysis

Example workflow:
  $ python chat-api/backend/prediction_ensemble_local/interactive.py AAPL --agent debt
  $ python chat-api/backend/prediction_ensemble_local/interactive.py AAPL --version 6  # simplified prompts
  $ python chat-api/backend/prediction_ensemble_local/interactive.py AAPL --compare    # A/B test both versions

  Then ask Claude Code:
  "Act as the debt expert agent and provide your analysis based on the data above"
"""

import argparse
import importlib.util
import os
import sys
from datetime import datetime
from pathlib import Path

# Add paths for imports
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir / 'lambda' / 'prediction_ensemble'))

# Prompt version registry
PROMPT_VERSIONS = {
    5: {
        'debt': 'value_investor_debt_v5.txt',
        'cashflow': 'value_investor_cashflow_v5.txt',
        'growth': 'value_investor_growth_v5.txt',
        'supervisor': 'supervisor_instruction_v5.txt',
        'description': 'Detailed prompts with metric reference tables (~80-125 lines)',
    },
    6: {
        'debt': 'value_investor_debt_v6.txt',
        'cashflow': 'value_investor_cashflow_v6.txt',
        'growth': 'value_investor_growth_v6.txt',
        'supervisor': 'supervisor_instruction_v6.txt',
        'description': 'Simplified prompts - model knows finance (~25-35 lines)',
    },
}

DEFAULT_VERSION = 5


def _import_from_lambda(module_path: str, module_name: str):
    """Import a module from the lambda directory (workaround for reserved keyword)."""
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_prompts(version: int = DEFAULT_VERSION) -> dict:
    """Load prompts for a specific version."""
    prompt_dir = backend_dir.parent / 'terraform' / 'modules' / 'bedrock' / 'prompts'
    version_config = PROMPT_VERSIONS.get(version, PROMPT_VERSIONS[DEFAULT_VERSION])

    prompts = {}
    for agent_type in ['debt', 'cashflow', 'growth', 'supervisor']:
        filename = version_config.get(agent_type)
        if filename:
            filepath = prompt_dir / filename
            if filepath.exists():
                prompts[agent_type] = filepath.read_text()
            else:
                prompts[agent_type] = f"[Prompt file not found: {filename}]"

    return prompts


def count_tokens_estimate(text: str) -> int:
    """Rough token estimate (4 chars per token average)."""
    return len(text) // 4


def run_interactive(
    ticker: str,
    agent_type: str = None,
    fiscal_year: int = None,
    version: int = DEFAULT_VERSION,
    compare: bool = False
):
    """
    Run interactive ensemble testing.

    Outputs formatted prompts that Claude Code can use directly.

    Args:
        ticker: Stock ticker symbol
        agent_type: Specific agent to show (debt/cashflow/growth) or None for all
        fiscal_year: Fiscal year to analyze
        version: Prompt version to use (5 or 6)
        compare: If True, show both v5 and v6 prompts for A/B testing
    """
    # Import from prediction_ensemble (now in sys.path)
    from utils.fmp_client import get_financial_data
    from utils.feature_extractor import (
        extract_all_features, extract_quarterly_trends, aggregate_annual_data
    )
    from services.inference import run_inference
    from handlers.action_group import extract_value_metrics
    from services.orchestrator import (
        format_annual_summary, format_fiscal_year_data
    )

    fiscal_year = fiscal_year or datetime.now().year

    # Load prompts for specified version(s)
    versions_to_show = [5, 6] if compare else [version]
    all_prompts = {v: load_prompts(v) for v in versions_to_show}

    print(f"Fetching data for {ticker}...")

    # Fetch data
    financial_data = get_financial_data(ticker)
    if not financial_data or 'raw_financials' not in financial_data:
        print(f"ERROR: No financial data found for {ticker}")
        return

    raw_financials = financial_data['raw_financials']
    features = extract_all_features(raw_financials)
    quarterly_trends = extract_quarterly_trends(raw_financials)

    # Run inference
    predictions = {}
    for at in ['debt', 'cashflow', 'growth']:
        predictions[at] = run_inference(at, features)

    # Extract metrics
    value_metrics = {}
    for at in ['debt', 'cashflow', 'growth']:
        value_metrics[at] = extract_value_metrics(quarterly_trends, features, at)

    # Aggregate annual
    annual_data = aggregate_annual_data(
        raw_financials.get('income_statement', []),
        raw_financials.get('balance_sheet', []),
        raw_financials.get('cash_flow', [])
    )

    # Determine which agents to show
    agents_to_show = [agent_type] if agent_type else ['debt', 'cashflow', 'growth']

    print("\n" + "=" * 80)
    print(f"PREDICTION ENSEMBLE - {ticker} (FY{fiscal_year})")
    if compare:
        print("MODE: A/B COMPARISON (v5 vs v6)")
    else:
        print(f"PROMPT VERSION: v{version} - {PROMPT_VERSIONS[version]['description']}")
    print("=" * 80)

    # Show ML predictions summary
    print("\n## ML PREDICTIONS SUMMARY")
    print("-" * 40)
    for at in ['debt', 'cashflow', 'growth']:
        pred = predictions[at]
        print(f"  {at.upper():10} : {pred.get('prediction'):4} ({pred.get('confidence', 0):.0%} confidence)")
    print()

    # Output each agent's prompt + data
    for at in agents_to_show:
        pred = predictions[at]
        probs = pred.get('probabilities', {})

        for v in versions_to_show:
            prompts = all_prompts[v]

            print("\n" + "=" * 80)
            if compare:
                print(f"## {at.upper()} EXPERT AGENT (v{v})")
            else:
                print(f"## {at.upper()} EXPERT AGENT")
            print("=" * 80)

            print(f"\n### SYSTEM PROMPT (v{v})")
            token_est = count_tokens_estimate(prompts[at])
            print(f"Lines: {len(prompts[at].splitlines())} | Est. tokens: ~{token_est}")
            print("-" * 40)
            print(prompts[at])

            # Only show data payload once (same for both versions)
            if v == versions_to_show[0]:
                print("\n### USER MESSAGE (DATA PAYLOAD)")
                print("-" * 40)

                inference_text = f"""## ML MODEL PREDICTION (Pre-computed)
- **Signal**: {pred.get('prediction', 'UNKNOWN')}
- **Confidence**: {pred.get('confidence', 0):.0%}
- **Confidence Interval Width**: {pred.get('ci_width', 0):.2f}
- **Probability Distribution**: SELL={probs.get('SELL', 0):.1%}, HOLD={probs.get('HOLD', 0):.1%}, BUY={probs.get('BUY', 0):.1%}
"""

                annual_summary = format_annual_summary(annual_data, agent_type=at)
                metrics_text = format_fiscal_year_data(value_metrics[at], agent_type=at)

                print(f"Analyze {ticker}'s {at} health for fiscal year {fiscal_year}.")
                print()
                print(inference_text)
                print(annual_summary)
                print(metrics_text)

        print("\n" + "-" * 40)
        print(">>> Ask Claude Code to act as this agent and provide analysis <<<")
        print("-" * 40)

    # Show supervisor prompt
    if not agent_type:
        for v in versions_to_show:
            prompts = all_prompts[v]
            print("\n" + "=" * 80)
            if compare:
                print(f"## SUPERVISOR AGENT (v{v})")
            else:
                print("## SUPERVISOR AGENT")
            print("=" * 80)

            print(f"\n### SYSTEM PROMPT (v{v})")
            token_est = count_tokens_estimate(prompts['supervisor'])
            print(f"Lines: {len(prompts['supervisor'].splitlines())} | Est. tokens: ~{token_est}")
            print("-" * 40)
            print(prompts['supervisor'])

        print("\n### WORKFLOW")
        print("1. First, ask Claude Code to analyze as each expert (debt, cashflow, growth)")
        print("2. Collect the 3 expert analyses")
        print("3. Then ask Claude Code to act as supervisor and synthesize")

    # Token summary for comparison mode
    if compare:
        print("\n" + "=" * 80)
        print("## TOKEN COMPARISON SUMMARY")
        print("=" * 80)
        for v in versions_to_show:
            prompts = all_prompts[v]
            total_tokens = sum(count_tokens_estimate(prompts[at]) for at in ['debt', 'cashflow', 'growth', 'supervisor'])
            print(f"  v{v}: ~{total_tokens} tokens total ({PROMPT_VERSIONS[v]['description']})")
        print("\nSavings with v6: ~60-70% fewer system prompt tokens")


def main():
    parser = argparse.ArgumentParser(
        description='Interactive ensemble testing with version control',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s AAPL                    # Run with default (v5) prompts
  %(prog)s AAPL --version 6        # Run with simplified (v6) prompts
  %(prog)s AAPL --compare          # A/B test: show both v5 and v6
  %(prog)s AAPL --agent debt -v 6  # Single agent with v6 prompt
        """
    )
    parser.add_argument('ticker', help='Ticker symbol')
    parser.add_argument('--agent', choices=['debt', 'cashflow', 'growth'],
                        help='Show specific agent only')
    parser.add_argument('--fiscal-year', type=int, help='Fiscal year')
    parser.add_argument('-v', '--version', type=int, choices=[5, 6], default=DEFAULT_VERSION,
                        help=f'Prompt version (default: {DEFAULT_VERSION})')
    parser.add_argument('--compare', action='store_true',
                        help='A/B test: show both v5 and v6 prompts')
    parser.add_argument('--list-versions', action='store_true',
                        help='List available prompt versions and exit')

    args = parser.parse_args()

    if args.list_versions:
        print("Available Prompt Versions:")
        print("-" * 60)
        for v, config in PROMPT_VERSIONS.items():
            print(f"  v{v}: {config['description']}")
        return

    run_interactive(
        ticker=args.ticker.upper(),
        agent_type=args.agent,
        fiscal_year=args.fiscal_year,
        version=args.version,
        compare=args.compare
    )


if __name__ == '__main__':
    main()
