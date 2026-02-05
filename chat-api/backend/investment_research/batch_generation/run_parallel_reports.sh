#!/bin/bash
# Parallel DJIA report generation using tmux
# Spawns 5 Claude Code sessions, each handling 6 companies
#
# Usage:
#   ./run_parallel_reports.sh
#   ./run_parallel_reports.sh --dry-run
#
# Prerequisites:
#   - tmux installed (brew install tmux)
#   - claude CLI installed
#   - djia_30_batch_data.json exists (from prepare_batch_data.py)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
DATA_FILE="$PROJECT_ROOT/djia_30_batch_data.json"

# 5 batches of 6 companies each (alphabetically sorted)
BATCH1="AAPL,AMGN,AXP,BA,CAT,CRM"
BATCH2="CSCO,CVX,DIS,DOW,GS,HD"
BATCH3="HON,IBM,INTC,JNJ,JPM,KO"
BATCH4="MCD,MMM,MRK,MSFT,NKE,PG"
BATCH5="TRV,UNH,V,VZ,WBA,WMT"

SESSION="djia-reports"

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
echo "  5 parallel sessions × 6 companies each"
echo "============================================"
echo ""
echo "Project root: $PROJECT_ROOT"
echo "Data file:    $DATA_FILE"
echo ""

# Check prerequisites
if ! command -v tmux &> /dev/null; then
    echo "ERROR: tmux is required but not installed."
    echo "Install with: brew install tmux"
    exit 1
fi

if ! command -v claude &> /dev/null; then
    echo "ERROR: claude CLI is required but not installed."
    exit 1
fi

if [[ ! -f "$DATA_FILE" ]]; then
    echo "ERROR: Data file not found: $DATA_FILE"
    echo "Run prepare_batch_data.py first:"
    echo "  python -m investment_research.batch_generation.prepare_batch_data"
    exit 1
fi

# Dry run - just show what would happen
if [[ "$DRY_RUN" == "true" ]]; then
    echo "DRY RUN - Would create 5 tmux windows:"
    echo "  Window 0 (batch1): $BATCH1"
    echo "  Window 1 (batch2): $BATCH2"
    echo "  Window 2 (batch3): $BATCH3"
    echo "  Window 3 (batch4): $BATCH4"
    echo "  Window 4 (batch5): $BATCH5"
    exit 0
fi

# Kill existing session if present
tmux kill-session -t $SESSION 2>/dev/null || true

# Build the prompt template for each batch
# Note: Each Claude session will need to:
# 1. Read the batch data file
# 2. Load the v4.8 prompt template
# 3. Generate and save each report
read -r -d '' PROMPT_TEMPLATE << 'EOF' || true
Generate investment reports for the following companies: TICKERS

Instructions:
1. Read the pre-fetched data from djia_30_batch_data.json
2. For each ticker, load its metrics_context from the JSON
3. Read the system prompt from chat-api/backend/investment_research/prompts/investment_report_prompt_v4_8.txt
4. Generate a complete investment report following the v4.8 structure
5. Save each report to DynamoDB using:
   from investment_research.report_generator import ReportGenerator
   generator = ReportGenerator(prompt_version=4.8)
   generator.save_report_sections(ticker, 2026, report_content)
6. Print "✓ TICKER saved" after each successful save

When all 6 reports are saved, print: "BATCH COMPLETE"
EOF

echo "Creating tmux session: $SESSION"
echo ""

# Create tmux session with 5 windows
tmux new-session -d -s $SESSION -n "batch1" -c "$PROJECT_ROOT"
tmux send-keys -t $SESSION:batch1 "claude --print '${PROMPT_TEMPLATE//TICKERS/$BATCH1}'" Enter

tmux new-window -t $SESSION -n "batch2" -c "$PROJECT_ROOT"
tmux send-keys -t $SESSION:batch2 "claude --print '${PROMPT_TEMPLATE//TICKERS/$BATCH2}'" Enter

tmux new-window -t $SESSION -n "batch3" -c "$PROJECT_ROOT"
tmux send-keys -t $SESSION:batch3 "claude --print '${PROMPT_TEMPLATE//TICKERS/$BATCH3}'" Enter

tmux new-window -t $SESSION -n "batch4" -c "$PROJECT_ROOT"
tmux send-keys -t $SESSION:batch4 "claude --print '${PROMPT_TEMPLATE//TICKERS/$BATCH4}'" Enter

tmux new-window -t $SESSION -n "batch5" -c "$PROJECT_ROOT"
tmux send-keys -t $SESSION:batch5 "claude --print '${PROMPT_TEMPLATE//TICKERS/$BATCH5}'" Enter

echo "Started 5 parallel Claude sessions!"
echo ""
echo "============================================"
echo "  tmux Session: $SESSION"
echo "============================================"
echo ""
echo "Commands:"
echo "  tmux attach -t $SESSION     # Attach to session"
echo "  Ctrl+B then 0-4             # Switch between windows"
echo "  Ctrl+B then D               # Detach (sessions continue)"
echo "  tmux kill-session -t $SESSION  # Stop all sessions"
echo ""
echo "Batches:"
echo "  Window 0: $BATCH1"
echo "  Window 1: $BATCH2"
echo "  Window 2: $BATCH3"
echo "  Window 3: $BATCH4"
echo "  Window 4: $BATCH5"
echo ""
echo "============================================"
