#!/usr/bin/env bash
# ============================================================================
# run_performance_tests.sh — Orchestrate Stripe performance / load tests
#
# Usage:
#   ./scripts/run_performance_tests.sh              # run all pytest phases
#   ./scripts/run_performance_tests.sh --phase 2    # run Phase 2 only
#   ./scripts/run_performance_tests.sh --phase 3    # run Phase 3 only
#   ./scripts/run_performance_tests.sh --phase 4    # run Phase 4 only
#   ./scripts/run_performance_tests.sh --locust     # Locust HTTP load test
#   ./scripts/run_performance_tests.sh --all        # all pytest phases (default)
#   ./scripts/run_performance_tests.sh --help       # show usage
#
# Environment variables:
#   PERF_TEST_HOST   Base URL for Locust (e.g. http://localhost:8000)
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPORTS_DIR="$BACKEND_DIR/tests/performance/reports"

# Colours (disable when piped)
if [[ -t 1 ]]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; NC=''
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
  --all             Run all pytest performance phases (default)
  --phase N         Run a specific phase (2, 3, or 4)
  --locust          Run Locust HTTP load test (headless)
  --aws             Run Locust against AWS dev API with real auth (Phase 7)
  --host URL        Base URL for Locust (overrides PERF_TEST_HOST)
  --help            Show this help message

Environment variables (--aws mode):
  LOCUST_USERS        Number of concurrent users (default: 50)
  LOCUST_SPAWN_RATE   User spawn rate per second (default: 5)
  LOCUST_DURATION     Test duration (default: 60s)
  CUSTOM_HOST         Override dev API URL

Examples:
  $(basename "$0")                      # run all pytest phases
  $(basename "$0") --phase 2            # Phase 2 only
  $(basename "$0") --locust --host http://localhost:8000
  $(basename "$0") --aws               # AWS dev load test
  LOCUST_USERS=20 LOCUST_DURATION=30s $(basename "$0") --aws
EOF
}

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

check_python() {
    if ! command -v python3 &>/dev/null; then
        log_error "python3 not found — Python 3.11+ is required"
        exit 1
    fi
    local ver
    ver=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    log_info "Python version: $ver"
}

install_deps() {
    local req="$BACKEND_DIR/requirements-performance.txt"
    if [[ ! -f "$req" ]]; then
        log_error "Missing $req"
        exit 1
    fi
    log_info "Installing performance dependencies …"
    pip install -q -r "$req"
}

ensure_reports_dir() {
    mkdir -p "$REPORTS_DIR"
}

# ---------------------------------------------------------------------------
# Test runners
# ---------------------------------------------------------------------------

OVERALL_RC=0
RESULT_LABELS=()            # indexed array of test labels
RESULT_VALUES=()            # indexed array of PASS/FAIL strings
TOTAL_START=$(date +%s)

run_pytest_file() {
    local label="$1"; shift
    local start elapsed rc
    start=$(date +%s)
    log_info "Running: $label"

    set +e
    (cd "$BACKEND_DIR" && python3 -m pytest "$@" -v -s)
    rc=$?
    set -e

    elapsed=$(( $(date +%s) - start ))

    if [[ $rc -eq 0 ]]; then
        RESULT_LABELS+=("$label")
        RESULT_VALUES+=("PASS (${elapsed}s)")
    else
        RESULT_LABELS+=("$label")
        RESULT_VALUES+=("FAIL (${elapsed}s)")
        OVERALL_RC=1
    fi
}

run_phase_2() {
    run_pytest_file "Phase 2 — Webhook Concurrency" \
        tests/performance/test_webhook_concurrency.py \
        tests/performance/test_idempotency_stress.py
}

run_phase_3() {
    run_pytest_file "Phase 3 — DynamoDB Throughput" \
        tests/performance/test_dynamodb_throughput.py
}

run_phase_4() {
    run_pytest_file "Phase 4 — Spike Scenarios" \
        tests/performance/test_spike_scenarios.py
}

run_all_pytest() {
    run_phase_2
    run_phase_3
    run_phase_4
}

run_locust() {
    local host="${LOCUST_HOST:-${PERF_TEST_HOST:-}}"
    if [[ -z "$host" ]]; then
        log_error "No host specified. Use --host URL or set PERF_TEST_HOST"
        exit 1
    fi

    local report="$REPORTS_DIR/locust_report.html"
    log_info "Starting Locust: 100 users, spawn-rate 10/s, 60 s against $host"

    local start rc
    start=$(date +%s)

    set +e
    (cd "$BACKEND_DIR" && python3 -m locust \
        -f tests/performance/locustfile.py \
        --headless \
        -u 100 \
        -r 10 \
        -t 60s \
        --host="$host" \
        --html="$report" \
    )
    rc=$?
    set -e

    local elapsed=$(( $(date +%s) - start ))

    if [[ $rc -eq 0 ]]; then
        RESULT_LABELS+=("Locust load test")
        RESULT_VALUES+=("PASS (${elapsed}s)")
        log_info "Locust report saved to $report"
    else
        RESULT_LABELS+=("Locust load test")
        RESULT_VALUES+=("FAIL (${elapsed}s)")
        OVERALL_RC=1
    fi
}

# ---------------------------------------------------------------------------
# AWS Dev Environment Mode (Phase 7)
# ---------------------------------------------------------------------------

DEV_API_URL="https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev"

run_aws() {
    echo "=== Phase 7: AWS Dev Environment Load Testing ==="
    echo ""

    # Verify AWS CLI is configured
    if ! aws sts get-caller-identity &>/dev/null; then
        log_error "AWS CLI not configured. Run 'aws configure' first."
        exit 1
    fi
    log_info "[1/5] AWS credentials verified"

    # Fetch secrets from Secrets Manager (NEVER hardcode)
    log_info "[2/5] Fetching secrets from AWS Secrets Manager..."
    export AWS_JWT_SECRET
    AWS_JWT_SECRET=$(aws secretsmanager get-secret-value \
        --secret-id buffett-dev-jwt-secret \
        --query SecretString --output text 2>/dev/null)

    if [ -z "$AWS_JWT_SECRET" ]; then
        log_error "Could not fetch buffett-dev-jwt-secret"
        exit 1
    fi

    export AWS_WEBHOOK_SECRET
    AWS_WEBHOOK_SECRET=$(aws secretsmanager get-secret-value \
        --secret-id stripe-webhook-secret-dev \
        --query SecretString --output text 2>/dev/null)

    if [ -z "$AWS_WEBHOOK_SECRET" ]; then
        log_error "Could not fetch stripe-webhook-secret-dev"
        exit 1
    fi
    log_info "  Secrets loaded (JWT + Webhook)"

    # Seed test users
    log_info "[3/5] Seeding test users in DynamoDB..."
    (cd "$BACKEND_DIR" && python3 -m tests.performance.utils.seed_test_user seed --count 10)

    # Run Locust
    local host="${CUSTOM_HOST:-$DEV_API_URL}"
    log_info "[4/5] Launching Locust against $host"
    echo ""
    echo "  IMPORTANT: API Gateway rate limits apply"
    echo "    Steady: 100 req/s | Burst: 500 req/s"
    echo "    Recommended: -u 50 -r 5 (stay under limits)"
    echo ""

    local start rc
    start=$(date +%s)

    set +e
    (cd "$BACKEND_DIR" && python3 -m locust \
        -f tests/performance/locustfile.py \
        --headless \
        -u "${LOCUST_USERS:-50}" \
        -r "${LOCUST_SPAWN_RATE:-5}" \
        -t "${LOCUST_DURATION:-60s}" \
        --host="$host" \
        --html="$REPORTS_DIR/aws_dev_report.html" \
        --csv="$REPORTS_DIR/aws_dev" \
    )
    rc=$?
    set -e

    local elapsed=$(( $(date +%s) - start ))

    if [[ $rc -eq 0 ]]; then
        RESULT_LABELS+=("AWS Dev Load Test")
        RESULT_VALUES+=("PASS (${elapsed}s)")
        log_info "Report: $REPORTS_DIR/aws_dev_report.html"
    else
        RESULT_LABELS+=("AWS Dev Load Test")
        RESULT_VALUES+=("FAIL (${elapsed}s)")
        OVERALL_RC=1
    fi

    # Cleanup test users
    echo ""
    log_info "[5/5] Cleaning up test users..."
    (cd "$BACKEND_DIR" && python3 -m tests.performance.utils.seed_test_user cleanup)

    # Unset secrets from environment
    unset AWS_JWT_SECRET
    unset AWS_WEBHOOK_SECRET

    echo ""
    log_info "=== AWS Dev Load Test Complete ==="
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print_summary() {
    local total_elapsed=$(( $(date +%s) - TOTAL_START ))
    echo ""
    echo "============================================================"
    echo " Performance Test Summary"
    echo "============================================================"
    printf " %-40s %s\n" "Test" "Result"
    echo "------------------------------------------------------------"
    local i=0
    while [[ $i -lt ${#RESULT_LABELS[@]} ]]; do
        local label="${RESULT_LABELS[$i]}"
        local val="${RESULT_VALUES[$i]}"
        if [[ "$val" == PASS* ]]; then
            printf " %-40s ${GREEN}%s${NC}\n" "$label" "$val"
        else
            printf " %-40s ${RED}%s${NC}\n" "$label" "$val"
        fi
        i=$((i + 1))
    done
    echo "------------------------------------------------------------"
    printf " %-40s %s\n" "Total duration" "${total_elapsed}s"
    echo "============================================================"

    if [[ $OVERALL_RC -ne 0 ]]; then
        log_error "Some tests FAILED"
    else
        log_info "All tests PASSED"
    fi
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

MODE="all"
PHASE=""
LOCUST_HOST=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            usage
            exit 0
            ;;
        --all)
            MODE="all"
            shift
            ;;
        --phase)
            MODE="phase"
            PHASE="${2:-}"
            if [[ -z "$PHASE" ]]; then
                log_error "--phase requires a number (2, 3, or 4)"
                exit 1
            fi
            shift 2
            ;;
        --locust)
            MODE="locust"
            shift
            ;;
        --aws)
            MODE="aws"
            shift
            ;;
        --host)
            LOCUST_HOST="${2:-}"
            if [[ -z "$LOCUST_HOST" ]]; then
                log_error "--host requires a URL"
                exit 1
            fi
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

check_python
install_deps
ensure_reports_dir

case "$MODE" in
    all)
        run_all_pytest
        ;;
    phase)
        case "$PHASE" in
            2) run_phase_2 ;;
            3) run_phase_3 ;;
            4) run_phase_4 ;;
            *)
                log_error "Invalid phase: $PHASE (valid: 2, 3, 4)"
                exit 1
                ;;
        esac
        ;;
    locust)
        run_locust
        ;;
    aws)
        run_aws
        ;;
esac

print_summary
exit $OVERALL_RC
