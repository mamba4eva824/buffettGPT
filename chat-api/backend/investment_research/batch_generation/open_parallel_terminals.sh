#!/bin/bash
# Open 5 Terminal.app windows for parallel DJIA report generation
#
# This script uses AppleScript to open visible Terminal windows,
# each running a Claude session for a batch of 6 companies.
#
# Usage:
#   ./open_parallel_terminals.sh
#   ./open_parallel_terminals.sh --dry-run
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

# Parse arguments
DRY_RUN=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "============================================"
echo "  DJIA Batch Report Generation"
echo "  5 Terminal windows × 6 companies each"
echo "============================================"
echo ""
echo "Project root: $PROJECT_ROOT"
echo "Data file:    $DATA_FILE"
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

# Dry run - just show what would happen
if [[ "$DRY_RUN" == "true" ]]; then
    echo "DRY RUN - Would open 5 Terminal windows:"
    echo "  Window 1 (batch1): $BATCH1"
    echo "  Window 2 (batch2): $BATCH2"
    echo "  Window 3 (batch3): $BATCH3"
    echo "  Window 4 (batch4): $BATCH4"
    echo "  Window 5 (batch5): $BATCH5"
    exit 0
fi

# Function to open a Terminal window with Claude
open_terminal_with_claude() {
    local batch_num=$1
    local tickers=$2
    local window_title="DJIA Batch $batch_num: $tickers"

    # Create the command to run in the new terminal
    # We use 'claude -p' to pass a prompt file instead of inline text
    local cmd="cd '$PROJECT_ROOT' && echo '=== Batch $batch_num: $tickers ===' && claude -p 'Generate investment reports for: $tickers. Read data from djia_30_batch_data.json, use v4.8 prompt, save to DynamoDB.'"

    # Use AppleScript to open a new Terminal window
    osascript <<EOF
tell application "Terminal"
    activate
    do script "echo 'Starting Batch $batch_num: $tickers' && cd '$PROJECT_ROOT' && claude"
    set custom title of front window to "$window_title"
end tell
EOF
}

echo "Opening 5 Terminal windows..."
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
echo "  5 Terminal Windows Opened!"
echo "============================================"
echo ""
echo "Each window has Claude ready. Paste this prompt in each:"
echo ""
echo "  Generate investment reports for: [TICKERS]"
echo "  Read data from djia_30_batch_data.json"
echo "  Use v4.8 prompt from prompts/investment_report_prompt_v4_8.txt"
echo "  Save each report to DynamoDB with save_report_sections()"
echo ""
echo "Batch assignments:"
echo "  Window 1: $BATCH1"
echo "  Window 2: $BATCH2"
echo "  Window 3: $BATCH3"
echo "  Window 4: $BATCH4"
echo "  Window 5: $BATCH5"
echo ""
echo "============================================"
