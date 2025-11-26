#!/bin/bash
# =============================================================================
# Deployment Status Script
# =============================================================================
# Purpose: Quick status check of GitHub Actions deployments
# Usage: ./scripts/deployment_status.sh [--limit N] [--workflow NAME]
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default configuration
LIMIT=10
WORKFLOW_NAME=""

# Function to print colored output
log_info() {
    echo -e "${BLUE}$1${NC}"
}

log_success() {
    echo -e "${GREEN}$1${NC}"
}

log_warning() {
    echo -e "${YELLOW}$1${NC}"
}

log_error() {
    echo -e "${RED}$1${NC}"
}

log_header() {
    echo -e "${CYAN}$1${NC}"
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --limit)
                LIMIT="$2"
                shift 2
                ;;
            --workflow)
                WORKFLOW_NAME="$2"
                shift 2
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

# Show help
show_help() {
    echo "Usage: ./scripts/deployment_status.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --limit N          Number of runs to display (default: 10)"
    echo "  --workflow NAME    Filter by workflow name (default: all workflows)"
    echo "  -h, --help         Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./scripts/deployment_status.sh"
    echo "  ./scripts/deployment_status.sh --limit 5"
    echo "  ./scripts/deployment_status.sh --workflow deploy.yml"
}

# Function to check if gh CLI is installed
check_gh_cli() {
    if ! command -v gh &> /dev/null; then
        log_error "GitHub CLI (gh) is not installed"
        echo "Install it with: brew install gh"
        exit 1
    fi
}

# Function to check if authenticated
check_gh_auth() {
    if ! gh auth status &> /dev/null; then
        log_error "Not authenticated with GitHub CLI"
        echo "Run: gh auth login"
        exit 1
    fi
}

# Function to format status with color
format_status() {
    local status="$1"
    local conclusion="$2"

    if [ "$status" = "completed" ]; then
        if [ "$conclusion" = "success" ]; then
            log_success "✅ Success"
        elif [ "$conclusion" = "failure" ]; then
            log_error "❌ Failed"
        elif [ "$conclusion" = "cancelled" ]; then
            log_warning "🚫 Cancelled"
        else
            log_warning "⚠️  $conclusion"
        fi
    elif [ "$status" = "in_progress" ]; then
        log_info "🔄 In Progress"
    elif [ "$status" = "queued" ]; then
        log_info "⏳ Queued"
    else
        echo "$status"
    fi
}

# Function to format duration
format_duration() {
    local seconds="$1"

    if [ -z "$seconds" ] || [ "$seconds" = "null" ]; then
        echo "N/A"
        return
    fi

    local minutes=$((seconds / 60))
    local remaining_seconds=$((seconds % 60))

    if [ $minutes -gt 0 ]; then
        echo "${minutes}m ${remaining_seconds}s"
    else
        echo "${seconds}s"
    fi
}

# Function to get relative time
get_relative_time() {
    local timestamp="$1"

    if [ -z "$timestamp" ] || [ "$timestamp" = "null" ]; then
        echo "Unknown"
        return
    fi

    # Use date command to convert timestamp
    local run_time=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$timestamp" "+%s" 2>/dev/null || echo "0")
    local current_time=$(date "+%s")
    local diff=$((current_time - run_time))

    local minutes=$((diff / 60))
    local hours=$((minutes / 60))
    local days=$((hours / 24))

    if [ $days -gt 0 ]; then
        echo "${days}d ago"
    elif [ $hours -gt 0 ]; then
        echo "${hours}h ago"
    elif [ $minutes -gt 0 ]; then
        echo "${minutes}m ago"
    else
        echo "just now"
    fi
}

# Function to list recent workflow runs
list_workflow_runs() {
    local workflow_filter=""

    if [ -n "$WORKFLOW_NAME" ]; then
        workflow_filter="--workflow=$WORKFLOW_NAME"
    fi

    log_header "╔════════════════════════════════════════════════════════════════════════════╗"
    log_header "║                    GitHub Actions Deployment Status                        ║"
    log_header "╚════════════════════════════════════════════════════════════════════════════╝"
    echo ""

    # Get workflow runs
    local runs=$(gh run list $workflow_filter --limit "$LIMIT" --json databaseId,number,status,conclusion,workflowName,headBranch,createdAt,event,url)

    if [ -z "$runs" ] || [ "$runs" = "[]" ]; then
        log_warning "No workflow runs found"
        return
    fi

    # Parse and display runs
    echo "$runs" | jq -r '.[] | @json' | while IFS= read -r run; do
        local run_id=$(echo "$run" | jq -r '.databaseId')
        local number=$(echo "$run" | jq -r '.number')
        local status=$(echo "$run" | jq -r '.status')
        local conclusion=$(echo "$run" | jq -r '.conclusion')
        local workflow=$(echo "$run" | jq -r '.workflowName')
        local branch=$(echo "$run" | jq -r '.headBranch')
        local created_at=$(echo "$run" | jq -r '.createdAt')
        local event=$(echo "$run" | jq -r '.event')
        local url=$(echo "$run" | jq -r '.url')

        # Format relative time
        local relative_time=$(get_relative_time "$created_at")

        # Display run information
        echo -e "${CYAN}Run #${number}${NC} (ID: ${run_id})"
        echo "  Workflow: $workflow"
        echo "  Branch: $branch"
        echo "  Event: $event"
        echo -n "  Status: "
        format_status "$status" "$conclusion"
        echo "  Created: $relative_time"
        echo "  URL: $url"
        echo ""
    done
}

# Function to show latest run details
show_latest_run() {
    echo ""
    log_header "╔════════════════════════════════════════════════════════════════════════════╗"
    log_header "║                         Latest Deployment Details                          ║"
    log_header "╚════════════════════════════════════════════════════════════════════════════╝"
    echo ""

    local workflow_filter=""
    if [ -n "$WORKFLOW_NAME" ]; then
        workflow_filter="--workflow=$WORKFLOW_NAME"
    fi

    local latest_run=$(gh run list $workflow_filter --limit 1 --json databaseId,number,status,conclusion,workflowName,headBranch,createdAt,updatedAt,event,url,jobs)

    if [ -z "$latest_run" ] || [ "$latest_run" = "[]" ]; then
        log_warning "No workflow runs found"
        return
    fi

    local run_id=$(echo "$latest_run" | jq -r '.[0].databaseId')
    local number=$(echo "$latest_run" | jq -r '.[0].number')
    local status=$(echo "$latest_run" | jq -r '.[0].status')
    local conclusion=$(echo "$latest_run" | jq -r '.[0].conclusion')
    local workflow=$(echo "$latest_run" | jq -r '.[0].workflowName')
    local branch=$(echo "$latest_run" | jq -r '.[0].headBranch')
    local created_at=$(echo "$latest_run" | jq -r '.[0].createdAt')
    local updated_at=$(echo "$latest_run" | jq -r '.[0].updatedAt')
    local event=$(echo "$latest_run" | jq -r '.[0].event')
    local url=$(echo "$latest_run" | jq -r '.[0].url')

    # Calculate duration
    local created_epoch=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$created_at" "+%s" 2>/dev/null || echo "0")
    local updated_epoch=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$updated_at" "+%s" 2>/dev/null || echo "0")
    local duration=$((updated_epoch - created_epoch))

    echo "Run #${number} (ID: ${run_id})"
    echo "Workflow: $workflow"
    echo "Branch: $branch"
    echo "Event: $event"
    echo -n "Status: "
    format_status "$status" "$conclusion"
    echo "Created: $(get_relative_time "$created_at")"

    if [ "$status" = "completed" ]; then
        echo "Duration: $(format_duration $duration)"
    fi

    echo "URL: $url"

    # Show jobs if available
    local jobs=$(echo "$latest_run" | jq -r '.[0].jobs')
    if [ -n "$jobs" ] && [ "$jobs" != "null" ]; then
        echo ""
        log_info "Jobs:"
        gh run view "$run_id" --json jobs --jq '.jobs[] | "  - \(.name): \(.conclusion // .status)"'
    fi

    echo ""
}

# Function to show statistics
show_statistics() {
    echo ""
    log_header "╔════════════════════════════════════════════════════════════════════════════╗"
    log_header "║                          Deployment Statistics                             ║"
    log_header "╚════════════════════════════════════════════════════════════════════════════╝"
    echo ""

    local workflow_filter=""
    if [ -n "$WORKFLOW_NAME" ]; then
        workflow_filter="--workflow=$WORKFLOW_NAME"
    fi

    local runs=$(gh run list $workflow_filter --limit 50 --json status,conclusion)

    if [ -z "$runs" ] || [ "$runs" = "[]" ]; then
        log_warning "No workflow runs found"
        return
    fi

    local total=$(echo "$runs" | jq 'length')
    local success=$(echo "$runs" | jq '[.[] | select(.conclusion == "success")] | length')
    local failed=$(echo "$runs" | jq '[.[] | select(.conclusion == "failure")] | length')
    local cancelled=$(echo "$runs" | jq '[.[] | select(.conclusion == "cancelled")] | length')
    local in_progress=$(echo "$runs" | jq '[.[] | select(.status == "in_progress")] | length')

    local success_rate=0
    if [ $total -gt 0 ]; then
        success_rate=$(awk "BEGIN {printf \"%.1f\", ($success / $total) * 100}")
    fi

    echo "Total Runs (last 50): $total"
    log_success "✅ Successful: $success"
    log_error "❌ Failed: $failed"
    log_warning "🚫 Cancelled: $cancelled"
    log_info "🔄 In Progress: $in_progress"
    echo ""
    echo "Success Rate: ${success_rate}%"
    echo ""
}

# Main execution
main() {
    parse_args "$@"

    # Pre-flight checks
    check_gh_cli
    check_gh_auth

    echo ""

    # Show deployment status
    list_workflow_runs
    show_latest_run
    show_statistics

    log_success "╔════════════════════════════════════════════════════════════════════════════╗"
    log_success "║                      Status Check Complete                                 ║"
    log_success "╚════════════════════════════════════════════════════════════════════════════╝"
    echo ""
}

# Run main function
main "$@"