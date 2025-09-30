#!/bin/bash

# Bedrock Agent Version Deployment Script
# Orchestrates Terraform deployment with agent version management
# Usage: ./deploy_agent_version.sh [dev|staging|prod]

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../../" && pwd)"
TERRAFORM_DIR="${PROJECT_ROOT}/terraform/environments"
PYTHON_SCRIPT="${SCRIPT_DIR}/bedrock_agent_manager.py"

# Default values
ENVIRONMENT="${1:-dev}"
AWS_REGION="${AWS_REGION:-us-east-1}"
AGENT_ID="${BEDROCK_AGENT_ID:-P82I6ITJGO}"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Validate environment
validate_environment() {
    if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
        log_error "Invalid environment: $ENVIRONMENT"
        echo "Usage: $0 [dev|staging|prod]"
        exit 1
    fi

    if [ ! -d "${TERRAFORM_DIR}/${ENVIRONMENT}" ]; then
        log_error "Terraform environment directory not found: ${TERRAFORM_DIR}/${ENVIRONMENT}"
        exit 1
    fi

    if [ ! -f "$PYTHON_SCRIPT" ]; then
        log_error "Python script not found: $PYTHON_SCRIPT"
        exit 1
    fi

    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed"
        exit 1
    fi

    # Check Terraform
    if ! command -v terraform &> /dev/null; then
        log_error "Terraform is not installed"
        exit 1
    fi

    # Check Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed"
        exit 1
    fi
}

# Get current agent status
get_agent_status() {
    log_info "Fetching current agent status..."
    python3 "$PYTHON_SCRIPT" --agent-id "$AGENT_ID" --region "$AWS_REGION" status
}

# Get current versions
get_current_versions() {
    log_info "Listing current agent versions..."
    python3 "$PYTHON_SCRIPT" --agent-id "$AGENT_ID" --region "$AWS_REGION" list-versions
}

# Run Terraform plan
run_terraform_plan() {
    log_info "Running Terraform plan for ${ENVIRONMENT}..."
    cd "${TERRAFORM_DIR}/${ENVIRONMENT}"

    # Initialize if needed
    if [ ! -d ".terraform" ]; then
        log_info "Initializing Terraform..."
        terraform init
    fi

    # Validate configuration
    log_info "Validating Terraform configuration..."
    terraform validate

    # Generate plan
    log_info "Generating Terraform plan..."
    terraform plan -out=tfplan

    # Ask for confirmation
    echo -e "\n${YELLOW}Review the plan above. Do you want to apply these changes? (yes/no)${NC}"
    read -r response

    if [[ ! "$response" =~ ^[Yy][Ee][Ss]$ ]]; then
        log_warning "Deployment cancelled by user"
        rm -f tfplan
        exit 0
    fi
}

# Apply Terraform changes
apply_terraform() {
    log_info "Applying Terraform changes..."
    cd "${TERRAFORM_DIR}/${ENVIRONMENT}"

    terraform apply tfplan
    rm -f tfplan

    log_success "Terraform apply completed"
}

# Prepare agent (may create new version)
prepare_agent() {
    log_info "Preparing agent..."
    python3 "$PYTHON_SCRIPT" --agent-id "$AGENT_ID" --region "$AWS_REGION" prepare

    # Wait for preparation to complete
    sleep 5
}

# Create new version if needed
create_version() {
    log_info "Attempting to create new agent version..."

    # Get version count before
    VERSIONS_BEFORE=$(python3 "$PYTHON_SCRIPT" --agent-id "$AGENT_ID" --region "$AWS_REGION" list-versions | grep -c "Version:" || true)

    # Try to create version
    python3 "$PYTHON_SCRIPT" --agent-id "$AGENT_ID" --region "$AWS_REGION" create-version

    # Get version count after
    sleep 5
    VERSIONS_AFTER=$(python3 "$PYTHON_SCRIPT" --agent-id "$AGENT_ID" --region "$AWS_REGION" list-versions | grep -c "Version:" || true)

    if [ "$VERSIONS_AFTER" -gt "$VERSIONS_BEFORE" ]; then
        NEW_VERSION=$((VERSIONS_AFTER - 1))  # Subtract 1 because DRAFT is also counted
        log_success "Created new version: $NEW_VERSION"
        return 0
    else
        log_warning "No new version created (no significant changes detected)"
        return 1
    fi
}

# Update alias to point to new version
update_alias() {
    local version=$1
    local alias_name="${2:-${ENVIRONMENT}}"

    log_info "Updating alias '${alias_name}' to point to version ${version}..."

    # Get alias ID
    ALIAS_ID=$(aws bedrock-agent list-agent-aliases \
        --agent-id "$AGENT_ID" \
        --region "$AWS_REGION" \
        --query "agentAliasSummaries[?agentAliasName=='${alias_name}'].agentAliasId" \
        --output text 2>/dev/null || echo "")

    if [ -z "$ALIAS_ID" ]; then
        log_warning "Alias '${alias_name}' not found. Creating new alias..."
        python3 "$PYTHON_SCRIPT" \
            --agent-id "$AGENT_ID" \
            --region "$AWS_REGION" \
            create-alias \
            --name "${alias_name}" \
            --version "$version" \
            --description "Alias for ${ENVIRONMENT} environment"
    else
        python3 "$PYTHON_SCRIPT" \
            --agent-id "$AGENT_ID" \
            --region "$AWS_REGION" \
            update-alias \
            --alias-id "$ALIAS_ID" \
            --version "$version"
    fi
}

# Update Lambda environment variables if needed
update_lambda_envvars() {
    local alias_id=$1

    log_info "Updating Lambda function environment variables..."

    # List of Lambda functions that need updating
    LAMBDA_FUNCTIONS=(
        "buffett-${ENVIRONMENT}-websocket-message"
        "buffett-${ENVIRONMENT}-chat-processor"
    )

    for func in "${LAMBDA_FUNCTIONS[@]}"; do
        log_info "Updating ${func}..."

        # Get current configuration
        CURRENT_ENV=$(aws lambda get-function-configuration \
            --function-name "$func" \
            --region "$AWS_REGION" \
            --query 'Environment.Variables' \
            --output json 2>/dev/null || echo "{}")

        # Update BEDROCK_AGENT_ALIAS
        UPDATED_ENV=$(echo "$CURRENT_ENV" | jq ".BEDROCK_AGENT_ALIAS = \"$alias_id\"")

        # Apply update
        aws lambda update-function-configuration \
            --function-name "$func" \
            --region "$AWS_REGION" \
            --environment "Variables=${UPDATED_ENV}" \
            --output json > /dev/null
    done

    log_success "Lambda environment variables updated"
}

# Main deployment flow
main() {
    log_info "Starting Bedrock Agent deployment for ${ENVIRONMENT}"

    # Validate environment
    validate_environment

    # Show current status
    get_agent_status
    echo ""
    get_current_versions
    echo ""

    # Run Terraform
    run_terraform_plan
    apply_terraform

    # Prepare agent
    prepare_agent

    # Try to create new version
    if create_version; then
        # Update alias if new version was created
        if [ -n "$NEW_VERSION" ]; then
            update_alias "$NEW_VERSION"

            # Get the alias ID for Lambda updates
            ALIAS_ID=$(aws bedrock-agent list-agent-aliases \
                --agent-id "$AGENT_ID" \
                --region "$AWS_REGION" \
                --query "agentAliasSummaries[?agentAliasName=='${ENVIRONMENT}'].agentAliasId" \
                --output text 2>/dev/null || echo "TSTALIASID")

            # Update Lambda functions
            update_lambda_envvars "$ALIAS_ID"
        fi
    else
        log_warning "Skipping alias update (no new version created)"
    fi

    # Show final status
    echo ""
    log_info "Final agent status:"
    get_agent_status
    echo ""
    get_current_versions

    log_success "Deployment completed successfully!"

    # Print summary
    echo ""
    echo "========================================="
    echo "Deployment Summary:"
    echo "  Environment: ${ENVIRONMENT}"
    echo "  Agent ID: ${AGENT_ID}"
    echo "  Region: ${AWS_REGION}"
    if [ -n "$NEW_VERSION" ]; then
        echo "  New Version: ${NEW_VERSION}"
    fi
    echo "========================================="
}

# Handle errors
trap 'log_error "Deployment failed at line $LINENO"' ERR

# Run main function
main "$@"