#!/bin/bash
# Parallel DJIA report generation using tmux
# Spawns 5 Claude Code sessions, each handling 6 companies
# Fully automated — no manual approvals required
#
# Usage:
#   ./run_parallel_reports.sh
#   ./run_parallel_reports.sh --dry-run
#   ./run_parallel_reports.sh --prompt-version 5.1
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
echo "  5 parallel sessions × 6 companies each"
echo "============================================"
echo ""
echo "Project root:    $PROJECT_ROOT"
echo "Data file:       $DATA_FILE"
echo "Prompt version:  v$PROMPT_VERSION"
echo "Max turns/batch: $MAX_TURNS"
echo "Allowed tools:   $ALLOWED_TOOLS"
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

# Verify prompt file exists
PROMPT_FILE="$PROJECT_ROOT/chat-api/backend/investment_research/prompts/$PROMPT_FILE_NAME"
if [[ ! -f "$PROMPT_FILE" ]]; then
    echo "ERROR: Prompt file not found: $PROMPT_FILE"
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
    echo ""
    echo "Each window runs:"
    echo "  claude -p '<prompt>' --allowedTools '$ALLOWED_TOOLS' --max-turns $MAX_TURNS"
    exit 0
fi

# Kill existing session if present
tmux kill-session -t $SESSION 2>/dev/null || true

# Function to build the prompt for a batch
build_prompt() {
    local tickers=$1
    cat <<PROMPT
Generate investment reports for: $tickers

You are running in FULLY AUTOMATED mode. Execute every step without waiting for confirmation.

Instructions:
1. Read the pre-fetched data from djia_30_batch_data.json
2. For each ticker in ($tickers), extract its metrics_context from the JSON
3. Read the system prompt from chat-api/backend/investment_research/prompts/$PROMPT_FILE_NAME
4. Generate a complete investment report following the prompt structure
5. Save each report to DynamoDB by writing the report to /tmp/{TICKER}_report.md, then running:
   cd $PROJECT_ROOT/chat-api/backend && python3 -c "
import sys; sys.path.insert(0, '.')
from investment_research.report_generator import ReportGenerator
generator = ReportGenerator(prompt_version=$PROMPT_VERSION)
report_content = open('/tmp/{TICKER}_report.md').read()
generator.save_report_sections('{TICKER}', 2026, report_content)
"
6. Print "✓ TICKER saved" after each successful save

IMPORTANT:
- Do NOT ask for confirmation at any step
- Do NOT pause between reports
- If a report fails, log the error and continue with the next ticker
- Replace {TICKER} with the actual ticker symbol in each command
- When all reports are saved, print: "BATCH COMPLETE: $tickers"
PROMPT
}

echo "Creating tmux session: $SESSION"
echo ""

# Create tmux session with 5 windows, each running automated Claude
tmux new-session -d -s $SESSION -n "batch1" -c "$PROJECT_ROOT"
tmux send-keys -t $SESSION:batch1 "claude -p '$(build_prompt "$BATCH1")' --allowedTools '$ALLOWED_TOOLS' --max-turns $MAX_TURNS --output-format text 2>&1 | tee /tmp/djia_batch1.log" Enter

tmux new-window -t $SESSION -n "batch2" -c "$PROJECT_ROOT"
tmux send-keys -t $SESSION:batch2 "claude -p '$(build_prompt "$BATCH2")' --allowedTools '$ALLOWED_TOOLS' --max-turns $MAX_TURNS --output-format text 2>&1 | tee /tmp/djia_batch2.log" Enter

tmux new-window -t $SESSION -n "batch3" -c "$PROJECT_ROOT"
tmux send-keys -t $SESSION:batch3 "claude -p '$(build_prompt "$BATCH3")' --allowedTools '$ALLOWED_TOOLS' --max-turns $MAX_TURNS --output-format text 2>&1 | tee /tmp/djia_batch3.log" Enter

tmux new-window -t $SESSION -n "batch4" -c "$PROJECT_ROOT"
tmux send-keys -t $SESSION:batch4 "claude -p '$(build_prompt "$BATCH4")' --allowedTools '$ALLOWED_TOOLS' --max-turns $MAX_TURNS --output-format text 2>&1 | tee /tmp/djia_batch4.log" Enter

tmux new-window -t $SESSION -n "batch5" -c "$PROJECT_ROOT"
tmux send-keys -t $SESSION:batch5 "claude -p '$(build_prompt "$BATCH5")' --allowedTools '$ALLOWED_TOOLS' --max-turns $MAX_TURNS --output-format text 2>&1 | tee /tmp/djia_batch5.log" Enter

echo "Started 5 automated Claude sessions!"
echo ""
echo "============================================"
echo "  tmux Session: $SESSION"
echo "============================================"
echo ""
echo "Commands:"
echo "  tmux attach -t $SESSION        # Attach to session"
echo "  Ctrl+B then 0-4                # Switch between windows"
echo "  Ctrl+B then D                  # Detach (sessions continue)"
echo "  tmux kill-session -t $SESSION  # Stop all sessions"
echo ""
echo "Logs:"
echo "  tail -f /tmp/djia_batch1.log   # Watch batch 1 progress"
echo "  tail -f /tmp/djia_batch2.log   # Watch batch 2 progress"
echo "  tail -f /tmp/djia_batch3.log   # Watch batch 3 progress"
echo "  tail -f /tmp/djia_batch4.log   # Watch batch 4 progress"
echo "  tail -f /tmp/djia_batch5.log   # Watch batch 5 progress"
echo ""
echo "Batches:"
echo "  Window 0: $BATCH1"
echo "  Window 1: $BATCH2"
echo "  Window 2: $BATCH3"
echo "  Window 3: $BATCH4"
echo "  Window 4: $BATCH5"
echo ""
echo "Verify after completion:"
echo "  cd chat-api/backend && python -m investment_research.batch_generation.batch_cli verify"
echo ""
echo "============================================"
