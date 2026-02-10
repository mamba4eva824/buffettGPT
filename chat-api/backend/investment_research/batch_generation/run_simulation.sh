#!/bin/bash
# Simulate automated report generation for 1-2 tickers
#
# Tests the fully automated flow (no manual approvals) before scaling to 30.
#
# Usage:
#   ./run_simulation.sh                          # Default: DIS,NFLX
#   ./run_simulation.sh --tickers AAPL,MSFT      # Custom tickers
#   ./run_simulation.sh --dry-run                 # Show command without executing
#   ./run_simulation.sh --prompt-version 5.1      # Use specific prompt version
#
# Prerequisites:
#   - claude CLI installed
#   - Batch data JSON exists (from prepare_batch_data.py)
#   - AWS credentials configured for DynamoDB

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
PROMPT_TEMPLATE="$SCRIPT_DIR/batch_prompt_template.md"

# Defaults
TICKERS="DIS,NFLX"
DRY_RUN=false
PROMPT_VERSION="4.8"
MAX_TURNS=30
DATA_FILE="$PROJECT_ROOT/djia_30_batch_data.json"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --tickers)
            TICKERS="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --prompt-version)
            PROMPT_VERSION="$2"
            shift 2
            ;;
        --max-turns)
            MAX_TURNS="$2"
            shift 2
            ;;
        --data-file)
            DATA_FILE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--tickers AAPL,MSFT] [--dry-run] [--prompt-version 4.8] [--max-turns 30] [--data-file path]"
            exit 1
            ;;
    esac
done

# Count tickers
TICKER_COUNT=$(echo "$TICKERS" | tr ',' '\n' | wc -l | tr -d ' ')

echo "============================================"
echo "  Report Generation Simulation"
echo "  $TICKER_COUNT ticker(s): $TICKERS"
echo "============================================"
echo ""
echo "Project root:    $PROJECT_ROOT"
echo "Data file:       $DATA_FILE"
echo "Prompt version:  v$PROMPT_VERSION"
echo "Max turns:       $MAX_TURNS"
echo ""

# Check prerequisites
if ! command -v claude &> /dev/null; then
    echo "ERROR: claude CLI is required but not installed."
    exit 1
fi

if [[ ! -f "$DATA_FILE" ]]; then
    echo "ERROR: Data file not found: $DATA_FILE"
    echo "Run prepare_batch_data.py first:"
    echo "  cd $PROJECT_ROOT/chat-api/backend && python -m investment_research.batch_generation.batch_cli prepare --tickers $TICKERS"
    exit 1
fi

# Resolve prompt file
PROMPT_FILE="$PROJECT_ROOT/chat-api/backend/investment_research/prompts/investment_report_prompt_v${PROMPT_VERSION//./_}.txt"
if [[ ! -f "$PROMPT_FILE" ]]; then
    echo "ERROR: Prompt file not found: $PROMPT_FILE"
    exit 1
fi

# Build the prompt
PROMPT="Generate investment reports for: $TICKERS

You are running in FULLY AUTOMATED mode. Execute every step without waiting for confirmation.

Instructions:
1. Read the pre-fetched financial data from $DATA_FILE
2. For each ticker ($TICKERS), extract its metrics_context from the JSON
3. Read the system prompt from chat-api/backend/investment_research/prompts/investment_report_prompt_v${PROMPT_VERSION//./_}.txt
4. Generate a complete investment report following the prompt structure
5. Save each report to DynamoDB:
   cd $PROJECT_ROOT/chat-api/backend && python3 -c \"
import sys; sys.path.insert(0, '.')
from investment_research.report_generator import ReportGenerator
generator = ReportGenerator(prompt_version=$PROMPT_VERSION)
report_content = open('/tmp/{TICKER}_report.md').read()
generator.save_report_sections('{TICKER}', 2026, report_content)
\"
6. Print '✓ TICKER saved' after each successful save
7. After all tickers are done, print: 'SIMULATION COMPLETE: $TICKERS'

IMPORTANT:
- Do NOT ask for confirmation at any step
- Do NOT pause between reports
- If a report fails, log the error and continue with the next ticker
- Write each report to /tmp/{TICKER}_report.md before saving to DynamoDB
- Use the exact Python commands shown above for saving"

# Define allowed tools for automation
ALLOWED_TOOLS="Read,Write,Glob,Grep,Bash(python *),Bash(python3 *),Bash(cd *),Bash(cat *)"

# Build the claude command
CLAUDE_CMD="claude -p '$PROMPT' \
  --allowedTools '$ALLOWED_TOOLS' \
  --max-turns $MAX_TURNS \
  --output-format text"

if [[ "$DRY_RUN" == "true" ]]; then
    echo "DRY RUN — Would execute:"
    echo ""
    echo "  cd $PROJECT_ROOT"
    echo ""
    echo "  $CLAUDE_CMD"
    echo ""
    echo "Allowed tools:"
    echo "  - Read (file reading)"
    echo "  - Write (file writing)"
    echo "  - Glob (file search)"
    echo "  - Grep (content search)"
    echo "  - Bash(python *) (Python execution)"
    echo "  - Bash(python3 *) (Python3 execution)"
    echo "  - Bash(cd *) (directory changes)"
    echo "  - Bash(cat *) (file display)"
    echo ""
    echo "Max turns: $MAX_TURNS"
    exit 0
fi

echo "Starting automated report generation..."
echo "Tickers: $TICKERS"
echo "This will run without manual approvals."
echo ""
echo "--------------------------------------------"

# Execute
cd "$PROJECT_ROOT"

claude -p "$PROMPT" \
  --allowedTools "$ALLOWED_TOOLS" \
  --max-turns "$MAX_TURNS" \
  --output-format text

EXIT_CODE=$?

echo ""
echo "--------------------------------------------"

if [[ $EXIT_CODE -eq 0 ]]; then
    echo "Simulation completed successfully."
else
    echo "Simulation exited with code: $EXIT_CODE"
    echo "(This may indicate max-turns was reached)"
fi

echo ""
echo "To verify reports were saved:"
echo "  cd $PROJECT_ROOT/chat-api/backend && python -m investment_research.batch_generation.batch_cli verify --tickers $TICKERS"
echo ""
