#!/bin/bash
# Open 5 Terminal.app windows for parallel DJIA report generation
# Fully automated — no manual approvals required
#
# This script uses AppleScript to open visible Terminal windows,
# each running a Claude session for a batch of 6 companies.
#
# Usage:
#   ./open_parallel_terminals.sh
#   ./open_parallel_terminals.sh --dry-run
#   ./open_parallel_terminals.sh --prompt-version 5.1
#
# Prerequisites:
#   - macOS with Terminal.app
#   - claude CLI installed
#   - djia_30_batch_data.json exists (from prepare_batch_data.py)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
DATA_FILE="$PROJECT_ROOT/djia_30_batch_data.json"
PROMPT_FILE="$SCRIPT_DIR/batch_prompt_template.md"

# 5 batches of 6 companies each (alphabetically sorted)
BATCH1="AAPL,AMGN,AXP,BA,CAT,CRM"
BATCH2="CSCO,CVX,DIS,DOW,GS,HD"
BATCH3="HON,IBM,INTC,JNJ,JPM,KO"
BATCH4="MCD,MMM,MRK,MSFT,NKE,PG"
BATCH5="TRV,UNH,V,VZ,WBA,WMT"

# Defaults
DRY_RUN=false
PROMPT_VERSION="4.8"
MAX_TURNS=50

# Allowed tools for automated execution
ALLOWED_TOOLS="Read,Write,Edit,Glob,Grep,Bash(python *),Bash(python3 *),Bash(cd *),Bash(cat *)"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
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
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--dry-run] [--prompt-version 4.8] [--max-turns 50]"
            exit 1
            ;;
    esac
done

PROMPT_FILE_NAME="investment_report_prompt_v${PROMPT_VERSION//./_}.txt"

echo "============================================"
echo "  DJIA Batch Report Generation (Automated)"
echo "  5 Terminal windows × 6 companies each"
echo "============================================"
echo ""
echo "Project root:    $PROJECT_ROOT"
echo "Data file:       $DATA_FILE"
echo "Prompt version:  v$PROMPT_VERSION"
echo "Max turns/batch: $MAX_TURNS"
echo ""

# Check prerequisites
if ! command -v claude &> /dev/null; then
    echo "ERROR: claude CLI is required but not installed."
    exit 1
fi

if [[ ! -f "$DATA_FILE" ]]; then
    echo "ERROR: Data file not found: $DATA_FILE"
    echo "Run prepare_batch_data.py first:"
    echo "  python -m investment_research.batch_generation.batch_cli prepare"
    exit 1
fi

# Verify prompt file exists
PROMPT_FILE_PATH="$PROJECT_ROOT/chat-api/backend/investment_research/prompts/$PROMPT_FILE_NAME"
if [[ ! -f "$PROMPT_FILE_PATH" ]]; then
    echo "ERROR: Prompt file not found: $PROMPT_FILE_PATH"
    exit 1
fi

# Dry run - just show what would happen
if [[ "$DRY_RUN" == "true" ]]; then
    echo "DRY RUN - Would open 5 Terminal windows:"
    echo "  Window 1 (batch1): $BATCH1"
    echo "  Window 2 (batch2): $BATCH2"
    echo "  Window 3 (batch3): $BATCH3"
    echo "  Window 4 (batch4): $BATCH4"
    echo "  Window 5 (batch5): $BATCH5"
    echo ""
    echo "Each window runs:"
    echo "  claude -p '<prompt>' --allowedTools '$ALLOWED_TOOLS' --max-turns $MAX_TURNS"
    exit 0
fi

# Function to open a Terminal window with automated Claude
open_terminal_with_claude() {
    local batch_num=$1
    local tickers=$2
    local window_title="DJIA Batch $batch_num: $tickers"
    local log_file="/tmp/djia_batch${batch_num}.log"

    # Build the prompt inline
    local prompt="Generate investment reports for: $tickers

You are running in FULLY AUTOMATED mode. Execute every step without waiting for confirmation.

Instructions:
1. Read the pre-fetched data from djia_30_batch_data.json
2. For each ticker in ($tickers), extract its metrics_context from the JSON
3. Read the system prompt from chat-api/backend/investment_research/prompts/$PROMPT_FILE_NAME
4. Generate a complete investment report following the prompt structure
5. Save each report to DynamoDB by writing the report to /tmp/{TICKER}_report.md, then running:
   cd $PROJECT_ROOT/chat-api/backend && python3 -c \"
import sys; sys.path.insert(0, '.')
from investment_research.report_generator import ReportGenerator
generator = ReportGenerator(prompt_version=$PROMPT_VERSION)
report_content = open('/tmp/{TICKER}_report.md').read()
generator.save_report_sections('{TICKER}', 2026, report_content)
\"
6. Print '✓ TICKER saved' after each successful save

IMPORTANT:
- Do NOT ask for confirmation at any step
- Do NOT pause between reports
- If a report fails, log the error and continue with the next ticker
- Replace {TICKER} with the actual ticker symbol in each command
- When all reports are saved, print: 'BATCH COMPLETE: $tickers'"

    # Use AppleScript to open a new Terminal window with automated claude
    osascript <<EOF
tell application "Terminal"
    activate
    do script "echo 'Starting Batch $batch_num: $tickers' && cd '$PROJECT_ROOT' && claude -p '$(echo "$prompt" | sed "s/'/'\\''/g")' --allowedTools '$ALLOWED_TOOLS' --max-turns $MAX_TURNS --output-format text 2>&1 | tee $log_file"
    set custom title of front window to "$window_title"
end tell
EOF
}

echo "Opening 5 Terminal windows (automated)..."
echo ""

# Open each terminal with a slight delay to prevent race conditions
open_terminal_with_claude 1 "$BATCH1"
sleep 1
open_terminal_with_claude 2 "$BATCH2"
sleep 1
open_terminal_with_claude 3 "$BATCH3"
sleep 1
open_terminal_with_claude 4 "$BATCH4"
sleep 1
open_terminal_with_claude 5 "$BATCH5"

echo ""
echo "============================================"
echo "  5 Automated Terminal Windows Opened!"
echo "============================================"
echo ""
echo "Sessions are running autonomously — no manual approval needed."
echo ""
echo "Logs:"
echo "  tail -f /tmp/djia_batch1.log   # Watch batch 1"
echo "  tail -f /tmp/djia_batch2.log   # Watch batch 2"
echo "  tail -f /tmp/djia_batch3.log   # Watch batch 3"
echo "  tail -f /tmp/djia_batch4.log   # Watch batch 4"
echo "  tail -f /tmp/djia_batch5.log   # Watch batch 5"
echo ""
echo "Batch assignments:"
echo "  Window 1: $BATCH1"
echo "  Window 2: $BATCH2"
echo "  Window 3: $BATCH3"
echo "  Window 4: $BATCH4"
echo "  Window 5: $BATCH5"
echo ""
echo "Verify after completion:"
echo "  cd chat-api/backend && python -m investment_research.batch_generation.batch_cli verify"
echo ""
echo "============================================"
