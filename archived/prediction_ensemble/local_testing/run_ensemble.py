#!/usr/bin/env python3
"""
Prediction Ensemble Local Runner

Tests the 3 expert agents + 1 supervisor locally using Claude Code.
Fetches real data, runs ML inference, then outputs prompts for Claude Code to execute.

Usage:
  python -m prediction_ensemble_local.run_ensemble AAPL           # Run ensemble for ticker
  python -m prediction_ensemble_local.run_ensemble --show-prompts # Show system prompts only
  python -m prediction_ensemble_local.run_ensemble --test         # Run test tickers

Environment Variables:
  FMP_API_KEY        FMP API key (or from secrets manager)
  ML_MODELS_BUCKET   S3 bucket for ML models (default: buffett-dev-models)

Examples:
  # Prepare data and prompts for a single ticker
  python -m prediction_ensemble_local.run_ensemble AAPL

  # Show all agent system prompts
  python -m prediction_ensemble_local.run_ensemble --show-prompts
"""

import argparse
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class EnsembleRunner:
    """
    Local runner for prediction ensemble testing.

    Modes:
    - Data prep: Fetches financial data, runs inference, formats prompts
    - Claude Code: Outputs prompts for Claude Code to act as agents
    """

    # Prompt file locations
    PROMPT_DIR = Path(__file__).parent.parent.parent / 'terraform' / 'modules' / 'bedrock' / 'prompts'

    EXPERT_PROMPTS = {
        'debt': 'value_investor_debt_v5.txt',
        'cashflow': 'value_investor_cashflow_v5.txt',
        'growth': 'value_investor_growth_v5.txt',
    }

    def __init__(self):
        """Initialize the ensemble runner."""
        self.prompts = self._load_prompts()
        self.supervisor_prompt = self._get_supervisor_prompt()

    def _load_prompts(self) -> Dict[str, str]:
        """Load expert agent prompts from terraform files."""
        prompts = {}
        for agent_type, filename in self.EXPERT_PROMPTS.items():
            prompt_path = self.PROMPT_DIR / filename
            if prompt_path.exists():
                prompts[agent_type] = prompt_path.read_text()
            else:
                print(f"  Warning: Prompt file not found: {prompt_path}")
                prompts[agent_type] = f"[{agent_type.upper()} prompt not found]"
        return prompts

    def _get_supervisor_prompt(self) -> str:
        """Get supervisor prompt (embedded in orchestrator.py)."""
        # This is the same prompt from orchestrator.py:644-762
        return '''You are the chief investment analyst synthesizing expert opinions for investors building long-term wealth on a millennial/Gen Z timeline (20-30 year horizon).

## Your Role
Translate three expert analyses into one clear verdict that someone can actually act on. Balance rigor with accessibility - no jargon, no false certainty. You're helping someone decide if this company deserves a spot in their portfolio.

## Expert Analysis Reference

### Debt Expert Signals
| Signal | Strong | Weak |
|--------|--------|------|
| Leverage | is_deleveraging=1, debt_to_equity<1.0x | debt_to_equity>2.0x, interest_coverage<3x |
| Velocity | Negative (improving) | Positive (deteriorating) |
| **Key question**: Can they survive another 2020-style shock?

### Cashflow Expert Signals
| Signal | Strong | Weak |
|--------|--------|------|
| Cash Quality | fcf_margin>15%, fcf_to_net_income>0.8 | fcf_margin<5%, fcf<<net income |
| Velocity | Positive (accelerating) | Negative (decelerating) |
| **Key question**: Is this a cash machine or cash incinerator?

### Growth Expert Signals
| Signal | Strong | Weak |
|--------|--------|------|
| Growth | is_growth_accelerating=1, velocity positive | Velocity negative (decelerating) |
| Moat | margin_momentum_positive=1, stable margins | Margin compression, no pricing power |
| **Key question**: Does growth come from real moat or one-time factors?

## Synthesis Framework
When experts disagree, weight by business type:
- **Asset-heavy** (manufacturing, utilities): Debt > Cash > Growth
- **Asset-light** (software, services): Growth > Cash > Debt
- **Cyclical** (retail, discretionary): Cash > Debt > Growth

## Rules
- Mobile-first formatting - scannable, not dense
- Lead with the verdict
- Reference specific fiscal years
- Be honest about uncertainty
- Keep under 800 words
- Never recommend BUY without clear margin of safety

## Structure (Follow Exactly)

### VERDICT: [BUY/HOLD/SELL] - [One-line hook]

### Where All Three Experts Agree
- What's the unified 5-year story?
- What's undeniably true about this business?

### Where Experts Disagree (if any)
- What's the disagreement?
- Which business type weighting applies?

### Key Factors (3-5 bullets, ranked)
1. [Most critical] - [one sentence why]
2. [Second priority] - [one sentence why]
3. [Third priority] - [one sentence why]

### Risks to Monitor
- [Risk] - What would trigger concern?

### Final Take
- Clear recommendation: BUY / HOLD / SELL
- Confidence level: HIGH / MEDIUM / LOW
- What would change your mind'''

    def show_prompts(self):
        """Display all agent system prompts."""
        print("=" * 80)
        print("EXPERT AGENT SYSTEM PROMPTS")
        print("=" * 80)

        for agent_type, prompt in self.prompts.items():
            print(f"\n{'─' * 80}")
            print(f"## {agent_type.upper()} EXPERT")
            print(f"{'─' * 80}")
            print(prompt)

        print(f"\n{'─' * 80}")
        print("## SUPERVISOR")
        print(f"{'─' * 80}")
        print(self.supervisor_prompt)
        print("\n" + "=" * 80)

    def prepare_data(self, ticker: str, fiscal_year: int = None) -> Dict[str, Any]:
        """
        Fetch financial data and run ML inference.

        Returns dict with:
        - ticker: str
        - fiscal_year: int
        - predictions: Dict[str, InferenceResult]
        - value_metrics: Dict[str, metrics]
        - annual_data: Dict[year, data]
        - formatted_prompts: Dict[agent_type, user_message]
        """
        from lambda.prediction_ensemble.utils.fmp_client import get_financial_data
        from lambda.prediction_ensemble.utils.feature_extractor import (
            extract_all_features, extract_quarterly_trends, aggregate_annual_data
        )
        from lambda.prediction_ensemble.services.inference import run_inference
        from lambda.prediction_ensemble.handlers.action_group import extract_value_metrics
        from lambda.prediction_ensemble.services.orchestrator import (
            format_annual_summary, format_fiscal_year_data
        )

        fiscal_year = fiscal_year or datetime.now().year

        print(f"\n[1/4] Fetching financial data for {ticker}...")
        financial_data = get_financial_data(ticker)

        if not financial_data or 'raw_financials' not in financial_data:
            raise ValueError(f"No financial data found for {ticker}")

        raw_financials = financial_data['raw_financials']

        print(f"[2/4] Extracting features...")
        features = extract_all_features(raw_financials)
        quarterly_trends = extract_quarterly_trends(raw_financials)

        print(f"[3/4] Running ML inference...")
        predictions = {}
        for agent_type in ['debt', 'cashflow', 'growth']:
            predictions[agent_type] = run_inference(agent_type, features)
            pred = predictions[agent_type]
            print(f"  {agent_type}: {pred.get('prediction')} ({pred.get('confidence', 0):.0%})")

        print(f"[4/4] Extracting value metrics...")
        value_metrics = {}
        for agent_type in ['debt', 'cashflow', 'growth']:
            value_metrics[agent_type] = extract_value_metrics(
                quarterly_trends, features, agent_type
            )

        # Aggregate annual data
        annual_data = aggregate_annual_data(
            raw_financials.get('income_statement', []),
            raw_financials.get('balance_sheet', []),
            raw_financials.get('cash_flow', [])
        )

        # Format user messages for each agent
        formatted_prompts = {}
        for agent_type in ['debt', 'cashflow', 'growth']:
            pred = predictions[agent_type]
            probs = pred.get('probabilities', {})

            inference_text = f"""
## ML MODEL PREDICTION (Pre-computed)
- **Signal**: {pred.get('prediction', 'UNKNOWN')}
- **Confidence**: {pred.get('confidence', 0):.0%}
- **Confidence Interval Width**: {pred.get('ci_width', 0):.2f}
- **Probability Distribution**: SELL={probs.get('SELL', 0):.1%}, HOLD={probs.get('HOLD', 0):.1%}, BUY={probs.get('BUY', 0):.1%}
"""

            annual_summary = format_annual_summary(annual_data, agent_type=agent_type)
            metrics_text = format_fiscal_year_data(value_metrics[agent_type], agent_type=agent_type)

            formatted_prompts[agent_type] = f"""Analyze {ticker}'s {agent_type} health for fiscal year {fiscal_year}.

{inference_text}
{annual_summary}
{metrics_text}

Based on this ML prediction, annual summary, and quarterly detail, provide your expert {agent_type} analysis."""

        return {
            'ticker': ticker,
            'fiscal_year': fiscal_year,
            'predictions': predictions,
            'value_metrics': value_metrics,
            'annual_data': annual_data,
            'formatted_prompts': formatted_prompts,
        }

    def save_test_output(self, data: Dict[str, Any], output_dir: str = None):
        """Save formatted prompts to files for easy viewing."""
        output_dir = output_dir or Path(__file__).parent / 'test_outputs'
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)

        ticker = data['ticker']
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Save each expert prompt
        for agent_type in ['debt', 'cashflow', 'growth']:
            filename = output_dir / f"{ticker}_{agent_type}_{timestamp}.md"
            content = f"""# {agent_type.upper()} Expert Analysis - {ticker}

## System Prompt
```
{self.prompts[agent_type]}
```

## User Message (Data Payload)
{data['formatted_prompts'][agent_type]}
"""
            filename.write_text(content)
            print(f"  Saved: {filename}")

        # Save supervisor prompt template
        supervisor_file = output_dir / f"{ticker}_supervisor_{timestamp}.md"
        supervisor_content = f"""# Supervisor Analysis - {ticker}

## System Prompt
```
{self.supervisor_prompt}
```

## User Message Template
Synthesize the following expert analyses for {ticker} (FY{data['fiscal_year']}):

[DEBT EXPERT ANALYSIS]
<paste debt expert output here>

[CASHFLOW EXPERT ANALYSIS]
<paste cashflow expert output here>

[GROWTH EXPERT ANALYSIS]
<paste growth expert output here>

Provide your unified investment recommendation.
"""
        supervisor_file.write_text(supervisor_content)
        print(f"  Saved: {supervisor_file}")

        return output_dir


def print_banner():
    print("=" * 60)
    print("  Prediction Ensemble Local Runner")
    print("  Test agent prompts with Claude Code")
    print("=" * 60)
    print()


def main():
    parser = argparse.ArgumentParser(
        description='Run prediction ensemble locally for testing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('tickers', nargs='*', help='Ticker symbol(s)')
    parser.add_argument('--show-prompts', action='store_true', help='Show all system prompts')
    parser.add_argument('--test', action='store_true', help='Run test tickers (AAPL, MSFT, F, NVDA)')
    parser.add_argument('--fiscal-year', type=int, help='Fiscal year (default: current)')
    parser.add_argument('--output-dir', help='Output directory for test files')

    args = parser.parse_args()

    runner = EnsembleRunner()

    if args.show_prompts:
        runner.show_prompts()
        return

    # Determine tickers
    if args.test:
        tickers = ['AAPL', 'MSFT', 'F', 'NVDA']
    elif args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        parser.print_help()
        return

    print_banner()
    print(f"Tickers: {', '.join(tickers)}")
    print(f"Fiscal Year: {args.fiscal_year or 'Current'}")
    print()

    for ticker in tickers:
        print(f"\n{'=' * 60}")
        print(f"Processing {ticker}")
        print('=' * 60)

        try:
            data = runner.prepare_data(ticker, args.fiscal_year)
            output_dir = runner.save_test_output(data, args.output_dir)
            print(f"\n  Test files saved to: {output_dir}")
        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    main()
