#!/bin/bash
# =============================================================================
# Monitor Deployment Script
# =============================================================================
# Purpose: Monitor GitHub Actions deployment and verify Lambda health
# Usage: ./scripts/monitor_deployment.sh [run-id]
#        If no run-id provided, monitors the latest workflow run
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
WORKFLOW_NAME="deploy.yml"
TERRAFORM_DIR="chat-api/terraform/environments/dev"

# Function to print colored output
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Function to check if gh CLI is installed
check_gh_cli() {
    if ! command -v gh &> /dev/null; then
        log_error "GitHub CLI (gh) is not installed"
        echo "Install it with: brew install gh"
        exit 1
    fi
    log_success "GitHub CLI is installed"
}

# Function to check if authenticated
check_gh_auth() {
    if ! gh auth status &> /dev/null; then
        log_error "Not authenticated with GitHub CLI"
        echo "Run: gh auth login"
        exit 1
    fi
    log_success "Authenticated with GitHub"
}

# Function to get the latest or specific run ID
get_run_id() {
    local provided_run_id="$1"

    if [ -n "$provided_run_id" ]; then
        echo "$provided_run_id"
    else
        log_info "Fetching latest workflow run..."
        local run_id=$(gh run list --workflow="$WORKFLOW_NAME" --limit 1 --json databaseId --jq '.[0].databaseId')

        if [ -z "$run_id" ] || [ "$run_id" = "null" ]; then
            log_error "No workflow runs found for $WORKFLOW_NAME"
            exit 1
        fi

        echo "$run_id"
    fi
}

# Function to get run details
get_run_details() {
    local run_id="$1"

    log_info "Fetching run details..."
    gh run view "$run_id" --json number,status,conclusion,workflowName,createdAt,event,headBranch,url \
        --jq '{
            number: .number,
            status: .status,
            conclusion: .conclusion,
            workflow: .workflowName,
            created: .createdAt,
            event: .event,
            branch: .headBranch,
            url: .url
        }'
}

# Function to monitor deployment in real-time
monitor_deployment() {
    local run_id="$1"

    echo ""
    log_info "=== Monitoring GitHub Actions Deployment (Run #$run_id) ==="
    echo ""

    # Show run details
    get_run_details "$run_id"

    echo ""
    log_info "Watching deployment in real-time (Ctrl+C to stop)..."
    echo ""

    # Watch the run
    if gh run watch "$run_id" --interval 5 --exit-status; then
        log_success "=== Deployment Successful ==="
        return 0
    else
        log_error "=== Deployment Failed ==="
        return 1
    fi
}

# Function to check Lambda function health
check_lambda_health() {
    log_info "=== Checking Lambda Function Health ==="
    echo ""

    # Define Lambda functions to check
    local functions=(
        "chat-processor"
        "websocket-connect"
        "websocket-message"
        "conversations-handler"
        "chat-http-handler"
    )

    local all_healthy=true

    for func_name in "${functions[@]}"; do
        # Try to get function with prefix from Terraform
        local full_name=$(aws lambda list-functions --query "Functions[?contains(FunctionName, '$func_name')].FunctionName" --output text | head -1)

        if [ -z "$full_name" ]; then
            log_warning "Function matching '$func_name' not found"
            continue
        fi

        # Get function state
        local state=$(aws lambda get-function --function-name "$full_name" --query 'Configuration.State' --output text 2>/dev/null)
        local last_update=$(aws lambda get-function --function-name "$full_name" --query 'Configuration.LastUpdateStatus' --output text 2>/dev/null)

        if [ "$state" = "Active" ] && [ "$last_update" = "Successful" ]; then
            log_success "$full_name is Active and Healthy"
        else
            log_error "$full_name is in state: $state (Last Update: $last_update)"
            all_healthy=false
        fi

        # Get recent logs (last 2 minutes)
        local log_group="/aws/lambda/$full_name"
        if aws logs describe-log-groups --log-group-name-prefix "$log_group" &> /dev/null; then
            local error_count=$(aws logs filter-log-events \
                --log-group-name "$log_group" \
                --start-time "$(($(date +%s) - 120))000" \
                --filter-pattern "ERROR" \
                --query 'events' \
                --output json | jq 'length' 2>/dev/null || echo "0")

            if [ "$error_count" -gt 0 ]; then
                log_warning "Found $error_count ERROR entries in recent logs"
            fi
        fi
    done

    echo ""
    if [ "$all_healthy" = true ]; then
        log_success "All Lambda functions are healthy"
        return 0
    else
        log_error "Some Lambda functions are not healthy"
        return 1
    fi
}

# Function to check DynamoDB tables
check_dynamodb_health() {
    log_info "=== Checking DynamoDB Tables ==="
    echo ""

    # Get table names from AWS
    local tables=$(aws dynamodb list-tables --query 'TableNames[?contains(@, `chat-`)]' --output text)

    if [ -z "$tables" ]; then
        log_warning "No DynamoDB tables found with 'chat-' prefix"
        return 1
    fi

    local all_healthy=true

    for table in $tables; do
        local status=$(aws dynamodb describe-table --table-name "$table" --query 'Table.TableStatus' --output text 2>/dev/null)

        if [ "$status" = "ACTIVE" ]; then
            log_success "$table is Active"
        else
            log_error "$table is in state: $status"
            all_healthy=false
        fi
    done

    echo ""
    if [ "$all_healthy" = true ]; then
        log_success "All DynamoDB tables are healthy"
        return 0
    else
        log_error "Some DynamoDB tables are not healthy"
        return 1
    fi
}

# Function to check API Gateway
check_api_gateway() {
    log_info "=== Checking API Gateway ==="
    echo ""

    # Check if terraform directory exists
    if [ ! -d "$TERRAFORM_DIR" ]; then
        log_warning "Terraform directory not found: $TERRAFORM_DIR"
        return 1
    fi

    # Get API endpoints from Terraform outputs
    cd "$TERRAFORM_DIR"

    local rest_api=$(terraform output -raw rest_api_endpoint 2>/dev/null || echo "")
    local websocket_api=$(terraform output -raw websocket_api_endpoint 2>/dev/null || echo "")

    cd - > /dev/null

    if [ -n "$rest_api" ] && [ "$rest_api" != "" ]; then
        log_success "REST API: $rest_api"
    else
        log_warning "REST API endpoint not found in Terraform outputs"
    fi

    if [ -n "$websocket_api" ] && [ "$websocket_api" != "" ]; then
        log_success "WebSocket API: $websocket_api"
    else
        log_warning "WebSocket API endpoint not found in Terraform outputs"
    fi

    echo ""
}

# Function to show deployment logs
show_deployment_logs() {
    local run_id="$1"

    log_info "=== Fetching Deployment Logs ==="
    echo ""

    gh run view "$run_id" --log
}

# Function to show failed logs only
show_failed_logs() {
    local run_id="$1"

    log_error "=== Fetching Failed Job Logs ==="
    echo ""

    gh run view "$run_id" --log-failed
}

# Main execution
main() {
    local run_id="$1"
    local show_logs="${2:-false}"

    echo ""
    log_info "╔════════════════════════════════════════════════════════════╗"
    log_info "║        BuffettGPT Deployment Monitoring Script            ║"
    log_info "╚════════════════════════════════════════════════════════════╝"
    echo ""

    # Pre-flight checks
    check_gh_cli
    check_gh_auth

    # Get run ID
    run_id=$(get_run_id "$run_id")

    echo ""
    log_success "Monitoring Run ID: $run_id"
    echo ""

    # Monitor the deployment
    if monitor_deployment "$run_id"; then
        echo ""
        log_info "=== Post-Deployment Verification ==="
        echo ""

        # Run health checks
        check_lambda_health
        check_dynamodb_health
        check_api_gateway

        echo ""
        log_success "╔════════════════════════════════════════════════════════════╗"
        log_success "║       Deployment Complete and Verified Successfully        ║"
        log_success "╚════════════════════════════════════════════════════════════╝"
        echo ""

        exit 0
    else
        echo ""
        log_error "Deployment failed. Fetching error logs..."
        echo ""

        show_failed_logs "$run_id"

        echo ""
        log_error "╔════════════════════════════════════════════════════════════╗"
        log_error "║              Deployment Failed - See Logs Above            ║"
        log_error "╚════════════════════════════════════════════════════════════╝"
        echo ""

        exit 1
    fi
}

# Run main function
main "$@"