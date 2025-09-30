#!/bin/bash
# =============================================================================
# Post-Deployment Health Check Script
# =============================================================================
# Purpose: Verify all AWS resources are healthy after deployment
# Usage: ./scripts/health_check.sh
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
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

# Track overall health
HEALTH_ISSUES=0

# Function to check AWS CLI
check_aws_cli() {
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed"
        exit 1
    fi
    log_success "AWS CLI is installed"
}

# Function to check AWS credentials
check_aws_credentials() {
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured or invalid"
        exit 1
    fi

    local identity=$(aws sts get-caller-identity --output json)
    local account=$(echo "$identity" | jq -r '.Account')
    local arn=$(echo "$identity" | jq -r '.Arn')

    log_success "Authenticated as: $arn"
    log_info "AWS Account: $account"
}

# Function to check Lambda functions
check_lambda_functions() {
    log_info "=== Checking Lambda Functions ==="
    echo ""

    local functions=(
        "chat-processor"
        "websocket-connect"
        "websocket-message"
        "conversations-handler"
        "chat-http-handler"
    )

    for func_pattern in "${functions[@]}"; do
        # Find function with pattern
        local full_name=$(aws lambda list-functions \
            --region "$AWS_REGION" \
            --query "Functions[?contains(FunctionName, '$func_pattern')].FunctionName" \
            --output text | head -1)

        if [ -z "$full_name" ]; then
            log_warning "Function matching '$func_pattern' not found"
            ((HEALTH_ISSUES++))
            continue
        fi

        # Get function details
        local func_info=$(aws lambda get-function \
            --function-name "$full_name" \
            --region "$AWS_REGION" \
            --output json 2>/dev/null)

        if [ $? -ne 0 ]; then
            log_error "Failed to get details for $full_name"
            ((HEALTH_ISSUES++))
            continue
        fi

        local state=$(echo "$func_info" | jq -r '.Configuration.State')
        local last_update=$(echo "$func_info" | jq -r '.Configuration.LastUpdateStatus')
        local runtime=$(echo "$func_info" | jq -r '.Configuration.Runtime')
        local memory=$(echo "$func_info" | jq -r '.Configuration.MemorySize')
        local timeout=$(echo "$func_info" | jq -r '.Configuration.Timeout')

        if [ "$state" = "Active" ] && [ "$last_update" = "Successful" ]; then
            log_success "$full_name"
            echo "   State: $state | Update: $last_update"
            echo "   Runtime: $runtime | Memory: ${memory}MB | Timeout: ${timeout}s"
        else
            log_error "$full_name"
            echo "   State: $state | Update: $last_update"
            ((HEALTH_ISSUES++))
        fi

        # Check recent invocations
        local log_group="/aws/lambda/$full_name"
        if aws logs describe-log-groups --log-group-name-prefix "$log_group" --region "$AWS_REGION" &> /dev/null; then
            local end_time=$(date +%s)000
            local start_time=$((end_time - 300000))  # Last 5 minutes

            local error_count=$(aws logs filter-log-events \
                --log-group-name "$log_group" \
                --start-time "$start_time" \
                --filter-pattern "ERROR" \
                --region "$AWS_REGION" \
                --query 'events' \
                --output json 2>/dev/null | jq 'length' || echo "0")

            if [ "$error_count" -gt 0 ]; then
                log_warning "   Found $error_count ERROR entries in last 5 minutes"
                ((HEALTH_ISSUES++))
            else
                echo "   No recent errors in logs"
            fi
        fi
        echo ""
    done
}

# Function to check DynamoDB tables
check_dynamodb_tables() {
    log_info "=== Checking DynamoDB Tables ==="
    echo ""

    # Get all tables with chat- prefix
    local tables=$(aws dynamodb list-tables \
        --region "$AWS_REGION" \
        --query 'TableNames[?contains(@, `chat-`)]' \
        --output text)

    if [ -z "$tables" ]; then
        log_warning "No DynamoDB tables found with 'chat-' prefix"
        ((HEALTH_ISSUES++))
        return
    fi

    for table in $tables; do
        local table_info=$(aws dynamodb describe-table \
            --table-name "$table" \
            --region "$AWS_REGION" \
            --output json 2>/dev/null)

        if [ $? -ne 0 ]; then
            log_error "Failed to describe table: $table"
            ((HEALTH_ISSUES++))
            continue
        fi

        local status=$(echo "$table_info" | jq -r '.Table.TableStatus')
        local item_count=$(echo "$table_info" | jq -r '.Table.ItemCount')
        local size_bytes=$(echo "$table_info" | jq -r '.Table.TableSizeBytes')

        if [ "$status" = "ACTIVE" ]; then
            log_success "$table"
            echo "   Status: $status | Items: $item_count | Size: ${size_bytes} bytes"
        else
            log_error "$table"
            echo "   Status: $status"
            ((HEALTH_ISSUES++))
        fi
        echo ""
    done
}

# Function to check API Gateway
check_api_gateways() {
    log_info "=== Checking API Gateway ==="
    echo ""

    # Check HTTP API (REST)
    local http_apis=$(aws apigatewayv2 get-apis \
        --region "$AWS_REGION" \
        --query 'Items[?contains(Name, `chat`)].{Name:Name, ApiId:ApiId, Endpoint:ApiEndpoint}' \
        --output json)

    if [ -z "$http_apis" ] || [ "$http_apis" = "[]" ]; then
        log_warning "No HTTP APIs found"
        ((HEALTH_ISSUES++))
    else
        echo "$http_apis" | jq -r '.[] | "\(.Name) (\(.ApiId))\n   Endpoint: \(.Endpoint)"' | while read -r line; do
            if [[ $line =~ ^[A-Za-z] ]]; then
                log_success "$line"
            else
                echo "$line"
            fi
        done
        echo ""
    fi

    # Get endpoints from Terraform if available
    if [ -d "$TERRAFORM_DIR" ]; then
        cd "$TERRAFORM_DIR"

        local rest_api=$(terraform output -raw rest_api_endpoint 2>/dev/null || echo "")
        local ws_api=$(terraform output -raw websocket_api_endpoint 2>/dev/null || echo "")

        cd - > /dev/null

        if [ -n "$rest_api" ] && [ "$rest_api" != "" ]; then
            log_info "REST API Endpoint (from Terraform): $rest_api"
        fi

        if [ -n "$ws_api" ] && [ "$ws_api" != "" ]; then
            log_info "WebSocket API Endpoint (from Terraform): $ws_api"
        fi
    fi

    echo ""
}

# Function to check Bedrock Agent
check_bedrock_agent() {
    log_info "=== Checking Bedrock Agent ==="
    echo ""

    # List agents
    local agents=$(aws bedrock-agent list-agents \
        --region "$AWS_REGION" \
        --query 'agentSummaries[?contains(agentName, `buffett`) || contains(agentName, `chat`)].{Name:agentName, Id:agentId, Status:agentStatus}' \
        --output json 2>/dev/null)

    if [ $? -ne 0 ]; then
        log_warning "Unable to list Bedrock agents (may lack permissions)"
        return
    fi

    if [ -z "$agents" ] || [ "$agents" = "[]" ]; then
        log_warning "No Bedrock agents found"
        return
    fi

    echo "$agents" | jq -r '.[] | "\(.Name) (\(.Id))\n   Status: \(.Status)"' | while read -r line; do
        if [[ $line =~ ^[A-Za-z] ]]; then
            log_success "$line"
        else
            echo "$line"
        fi
    done

    echo ""
}

# Function to check Secrets Manager
check_secrets_manager() {
    log_info "=== Checking AWS Secrets Manager ==="
    echo ""

    local secrets=$(aws secretsmanager list-secrets \
        --region "$AWS_REGION" \
        --query 'SecretList[?contains(Name, `buffett`) || contains(Name, `chat`)].{Name:Name, LastAccessed:LastAccessedDate}' \
        --output json 2>/dev/null)

    if [ $? -ne 0 ]; then
        log_warning "Unable to list secrets (may lack permissions)"
        return
    fi

    if [ -z "$secrets" ] || [ "$secrets" = "[]" ]; then
        log_warning "No secrets found"
        return
    fi

    echo "$secrets" | jq -r '.[] | "\(.Name)\n   Last Accessed: \(.LastAccessed // "Never")"' | while read -r line; do
        if [[ $line =~ ^[A-Za-z] ]]; then
            log_success "$line"
        else
            echo "$line"
        fi
    done

    echo ""
}

# Function to test API endpoint
test_api_endpoint() {
    local endpoint="$1"

    if [ -z "$endpoint" ]; then
        return
    fi

    log_info "=== Testing API Endpoint ==="
    echo ""

    local response=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$endpoint/health" 2>/dev/null || echo "000")

    if [ "$response" = "200" ]; then
        log_success "API health check passed (HTTP $response)"
    elif [ "$response" = "000" ]; then
        log_warning "API health check timed out or unreachable"
        ((HEALTH_ISSUES++))
    else
        log_warning "API health check returned HTTP $response"
        ((HEALTH_ISSUES++))
    fi

    echo ""
}

# Function to generate summary report
generate_summary() {
    echo ""
    log_info "╔════════════════════════════════════════════════════════════╗"
    log_info "║              Health Check Summary Report                   ║"
    log_info "╚════════════════════════════════════════════════════════════╝"
    echo ""

    if [ "$HEALTH_ISSUES" -eq 0 ]; then
        log_success "All health checks passed! ✨"
        echo ""
        log_success "Your BuffettGPT deployment is healthy and ready to use."
        return 0
    else
        log_warning "Health check completed with $HEALTH_ISSUES issue(s)"
        echo ""
        log_warning "Please review the warnings and errors above."
        return 1
    fi
}

# Main execution
main() {
    echo ""
    log_info "╔════════════════════════════════════════════════════════════╗"
    log_info "║          BuffettGPT Health Check Script                   ║"
    log_info "╚════════════════════════════════════════════════════════════╝"
    echo ""

    # Pre-flight checks
    check_aws_cli
    check_aws_credentials

    echo ""

    # Run all health checks
    check_lambda_functions
    check_dynamodb_tables
    check_api_gateways
    check_bedrock_agent
    check_secrets_manager

    # Get API endpoint from Terraform for testing
    if [ -d "$TERRAFORM_DIR" ]; then
        cd "$TERRAFORM_DIR"
        local api_endpoint=$(terraform output -raw rest_api_endpoint 2>/dev/null || echo "")
        cd - > /dev/null

        if [ -n "$api_endpoint" ]; then
            test_api_endpoint "$api_endpoint"
        fi
    fi

    # Generate summary
    generate_summary
    exit $?
}

# Run main function
main "$@"