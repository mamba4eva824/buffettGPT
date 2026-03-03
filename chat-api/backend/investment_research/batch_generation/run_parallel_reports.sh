#!/bin/bash
# Parallel report generation using tmux with wave-based recycling
# Splits tickers into fixed-size batches and runs them in waves across N tmux windows
# When a window finishes its batch, it picks up the next unprocessed batch
# Fully automated — no manual approvals required
#
# Usage:
#   ./run_parallel_reports.sh
#   ./run_parallel_reports.sh --index sp100 --windows 5 --batch-size 5
#   ./run_parallel_reports.sh --dry-run
#   ./run_parallel_reports.sh --prompt-version 5.1
#   ./run_parallel_reports.sh --index sp100 --windows 8 --batch-size 3
#
# Prerequisites:
#   - tmux installed (brew install tmux)
#   - claude CLI installed
#   - Data file exists (from prepare_batch_data.py)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

# Defaults
INDEX="djia"
WINDOWS=5
BATCH_SIZE=5
DRY_RUN=false
PROMPT_VERSION="5.1"
MAX_TURNS=""

# Allowed tools for automated execution
ALLOWED_TOOLS="Read,Write,Edit,Glob,Grep,Bash(python *),Bash(python3 *),Bash(cd *),Bash(cat *)"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --index)
            INDEX="$2"
            shift 2
            ;;
        --windows)
            WINDOWS="$2"
            shift 2
            ;;
        --batch-size)
            BATCH_SIZE="$2"
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
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--index djia] [--windows 5] [--batch-size 5] [--dry-run] [--prompt-version 5.1] [--max-turns N]"
            exit 1
            ;;
    esac
done

PROMPT_FILE_NAME="investment_report_prompt_v${PROMPT_VERSION//./_}.txt"
SESSION="${INDEX}-reports"

# Get tickers and split into fixed-size batches using Python
BATCHES=$(python3 -c "
import sys; sys.path.insert(0, '$PROJECT_ROOT/chat-api/backend')
from investment_research.index_tickers import get_index_tickers
tickers = get_index_tickers('$INDEX')
batch_size = $BATCH_SIZE
batches = []
for i in range(0, len(tickers), batch_size):
    batches.append(','.join(tickers[i:i+batch_size]))
print('\n'.join(batches))
")

# Get total ticker count
TOTAL_TICKERS=$(python3 -c "
import sys; sys.path.insert(0, '$PROJECT_ROOT/chat-api/backend')
from investment_research.index_tickers import get_index_tickers
print(len(get_index_tickers('$INDEX')))
")

# Split batches into array (one batch per line)
IFS=$'\n' read -r -d '' -a BATCH_ARRAY <<< "$BATCHES" || true

TOTAL_BATCHES=${#BATCH_ARRAY[@]}

# Auto-calculate max-turns if not specified: batch_size * 5 + 20
if [[ -z "$MAX_TURNS" ]]; then
    MAX_TURNS=$(( BATCH_SIZE * 5 + 20 ))
fi

# Find data file (glob for index pattern)
DATA_FILE=$(ls "$PROJECT_ROOT"/${INDEX}_*_batch_data.json 2>/dev/null | head -1 || echo "")
if [[ -z "$DATA_FILE" ]]; then
    DATA_FILE="$PROJECT_ROOT/${INDEX}_${TOTAL_TICKERS}_batch_data.json"
fi
DATA_FILE_BASENAME=$(basename "$DATA_FILE")

# Calculate number of waves
TOTAL_WAVES=$(( (TOTAL_BATCHES + WINDOWS - 1) / WINDOWS ))

INDEX_UPPER=$(echo "$INDEX" | tr '[:lower:]' '[:upper:]')
echo "============================================"
echo "  ${INDEX_UPPER} Wave-Based Report Generation (Automated)"
echo "  $TOTAL_BATCHES batches of ~$BATCH_SIZE tickers across $WINDOWS windows"
echo "============================================"
echo ""
echo "Project root:    $PROJECT_ROOT"
echo "Data file:       $DATA_FILE_BASENAME"
echo "Total tickers:   $TOTAL_TICKERS"
echo "Batch size:      $BATCH_SIZE tickers per batch"
echo "Total batches:   $TOTAL_BATCHES"
echo "Windows:         $WINDOWS (concurrent tmux windows)"
echo "Waves:           ~$TOTAL_WAVES"
echo "Prompt version:  v$PROMPT_VERSION"
echo "Max turns/batch: $MAX_TURNS"
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
    echo "WARNING: Data file not found: $DATA_FILE"
    echo "Run prepare_batch_data.py first:"
    echo "  python -m investment_research.batch_generation.prepare_batch_data --index $INDEX"
    if [[ "$DRY_RUN" != "true" ]]; then
        exit 1
    fi
fi

# Verify prompt file exists
PROMPT_FILE="$PROJECT_ROOT/chat-api/backend/investment_research/prompts/$PROMPT_FILE_NAME"
if [[ ! -f "$PROMPT_FILE" ]]; then
    echo "ERROR: Prompt file not found: $PROMPT_FILE"
    exit 1
fi

# Dry run - show wave plan with batches grouped by wave
if [[ "$DRY_RUN" == "true" ]]; then
    echo "DRY RUN - Wave plan for $TOTAL_BATCHES batches across $WINDOWS windows:"
    echo ""
    batch_idx=0
    wave_num=1
    while [[ $batch_idx -lt $TOTAL_BATCHES ]]; do
        echo "  Wave $wave_num:"
        wave_end=$((batch_idx + WINDOWS))
        if [[ $wave_end -gt $TOTAL_BATCHES ]]; then
            wave_end=$TOTAL_BATCHES
        fi
        while [[ $batch_idx -lt $wave_end ]]; do
            batch_num=$((batch_idx + 1))
            tickers="${BATCH_ARRAY[$batch_idx]}"
            ticker_count=$(echo "$tickers" | tr ',' '\n' | wc -l | tr -d ' ')
            echo "    Batch $batch_num ($ticker_count tickers): $tickers"
            batch_idx=$((batch_idx + 1))
        done
        echo ""
        wave_num=$((wave_num + 1))
    done
    echo "Each batch runs:"
    echo "  claude -p '<prompt>' --allowedTools '$ALLOWED_TOOLS' --max-turns $MAX_TURNS"
    echo ""
    echo "Sentinel files: /tmp/${INDEX}_batch{N}.done"
    exit 0
fi

# Kill existing session if present
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Function to build the prompt for a batch
build_prompt() {
    local tickers=$1
    local ticker_count
    ticker_count=$(echo "$tickers" | tr ',' '\n' | wc -l | tr -d ' ')
    cat <<PROMPT
Generate investment reports for: $tickers

You are running in FULLY AUTOMATED mode. Execute every step without waiting for confirmation.

Instructions:
1. Read the pre-fetched data from $DATA_FILE_BASENAME
2. For each ticker in ($tickers), extract its metrics_context from the JSON
3. Read the system prompt from chat-api/backend/investment_research/prompts/$PROMPT_FILE_NAME
4. Generate a complete investment report following the prompt structure
5. Save each report to DynamoDB by writing the report to /tmp/{TICKER}_report.md, then running:
   cd $PROJECT_ROOT/chat-api/backend && python3 -m investment_research.batch_generation.batch_save_report --ticker {TICKER} --data-file $PROJECT_ROOT/$DATA_FILE_BASENAME --report /tmp/{TICKER}_report.md --prompt-version $PROMPT_VERSION
6. Print "✓ TICKER saved" after each successful save

IMPORTANT:
- Do NOT ask for confirmation at any step
- Do NOT pause between reports
- If a report fails, log the error and continue with the next ticker
- Replace {TICKER} with the actual ticker symbol in each command
- When all reports are saved, print: "BATCH COMPLETE: $tickers"
PROMPT
}

# Function to launch a batch in a tmux window
launch_tmux_batch() {
    local batch_num=$1
    local tickers=$2

    if [[ "$SESSION_CREATED" != "true" ]]; then
        tmux new-session -d -s "$SESSION" -n "batch${batch_num}" -c "$PROJECT_ROOT"
        SESSION_CREATED=true
    else
        tmux new-window -t "$SESSION" -n "batch${batch_num}" -c "$PROJECT_ROOT"
    fi

    tmux send-keys -t "$SESSION:batch${batch_num}" \
        "claude -p '$(build_prompt "$tickers")' --allowedTools '$ALLOWED_TOOLS' --max-turns $MAX_TURNS --output-format text 2>&1 | tee /tmp/${INDEX}_batch${batch_num}.log; touch /tmp/${INDEX}_batch${batch_num}.done" Enter
}

echo "Starting wave-based execution..."
echo "  $TOTAL_BATCHES batches, $WINDOWS concurrent windows"
echo ""

# Clean up old sentinel files
rm -f /tmp/${INDEX}_batch*.done

SESSION_CREATED=false
NEXT_BATCH=0
ACTIVE=0

# Launch initial wave
while [[ $NEXT_BATCH -lt $TOTAL_BATCHES && $ACTIVE -lt $WINDOWS ]]; do
    batch_num=$((NEXT_BATCH + 1))
    echo "  Launching batch $batch_num/$TOTAL_BATCHES: ${BATCH_ARRAY[$NEXT_BATCH]}"
    launch_tmux_batch "$batch_num" "${BATCH_ARRAY[$NEXT_BATCH]}"
    NEXT_BATCH=$((NEXT_BATCH + 1))
    ACTIVE=$((ACTIVE + 1))
    sleep 1
done

echo ""
echo "Initial wave launched ($ACTIVE windows). Polling for completions..."
echo ""

# Poll for completions and launch next batches
while [[ $ACTIVE -gt 0 ]]; do
    sleep 5
    for done_file in /tmp/${INDEX}_batch*.done; do
        [ -f "$done_file" ] || continue
        # Extract batch number from filename for logging
        done_basename=$(basename "$done_file")
        done_batch_num=$(echo "$done_basename" | sed "s/${INDEX}_batch//" | sed 's/.done//')
        echo "  Batch $done_batch_num completed. ($ACTIVE active -> $((ACTIVE - 1)))"
        ACTIVE=$((ACTIVE - 1))
        rm "$done_file"
        if [[ $NEXT_BATCH -lt $TOTAL_BATCHES ]]; then
            batch_num=$((NEXT_BATCH + 1))
            echo "  Launching batch $batch_num/$TOTAL_BATCHES: ${BATCH_ARRAY[$NEXT_BATCH]}"
            launch_tmux_batch "$batch_num" "${BATCH_ARRAY[$NEXT_BATCH]}"
            NEXT_BATCH=$((NEXT_BATCH + 1))
            ACTIVE=$((ACTIVE + 1))
            sleep 1
        fi
    done
done

echo ""
echo "============================================"
echo "  All $TOTAL_BATCHES Batches Complete!"
echo "============================================"
echo ""
echo "Sessions ran autonomously across $WINDOWS tmux windows."
echo ""
echo "  tmux Session: $SESSION"
echo "  tmux attach -t $SESSION        # Attach to session"
echo "  tmux kill-session -t $SESSION  # Clean up session"
echo ""
echo "Logs:"
for i in $(seq 1 "$TOTAL_BATCHES"); do
    echo "  /tmp/${INDEX}_batch${i}.log"
done
echo ""
echo "Batch assignments:"
for i in "${!BATCH_ARRAY[@]}"; do
    batch_num=$((i + 1))
    echo "  Batch $batch_num: ${BATCH_ARRAY[$i]}"
done
echo ""
echo "Verify after completion:"
echo "  cd chat-api/backend && python -m investment_research.batch_generation.batch_cli verify --index $INDEX"
echo ""
echo "============================================"
