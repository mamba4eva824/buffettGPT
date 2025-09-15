#!/bin/bash
# WebSocket Integration Test Runner
# Automated testing script for WebSocket chat API

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
TERRAFORM_DIR="$PROJECT_DIR"

# Default values
TEST_TYPE="all"
USER_ID="test-user-$(date +%s)"
ENVIRONMENT="dev"
VERBOSE=false

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
show_usage() {
    cat << EOF
WebSocket Chat API Test Runner

Usage: $0 [OPTIONS]

OPTIONS:
    -e, --environment ENV    Environment to test (dev|staging|prod) [default: dev]
    -t, --test TYPE         Test type (basic|error|load|all) [default: all]
    -u, --user-id ID        User ID for testing [default: auto-generated]
    -v, --verbose           Enable verbose output
    -h, --help              Show this help message

EXAMPLES:
    $0                                      # Run all tests on dev environment
    $0 -e dev -t basic                     # Run basic tests on dev
    $0 -e prod -t load -u production-test  # Run load tests on prod
    $0 --verbose                           # Run with verbose output

REQUIREMENTS:
    - Python 3.7+ with websockets library
    - Node.js with ws library (optional)
    - Terraform deployment must be active
    - AWS CLI configured (for endpoint discovery)

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -t|--test)
            TEST_TYPE="$2"
            shift 2
            ;;
        -u|--user-id)
            USER_ID="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
    print_error "Invalid environment: $ENVIRONMENT"
    print_error "Valid environments: dev, staging, prod"
    exit 1
fi

# Validate test type
if [[ ! "$TEST_TYPE" =~ ^(basic|error|load|all)$ ]]; then
    print_error "Invalid test type: $TEST_TYPE"
    print_error "Valid test types: basic, error, load, all"
    exit 1
fi

print_status "Starting WebSocket Chat API Tests"
print_status "Environment: $ENVIRONMENT"
print_status "Test Type: $TEST_TYPE"
print_status "User ID: $USER_ID"
echo

# Check if Terraform directory exists
if [[ ! -d "$TERRAFORM_DIR" ]]; then
    print_error "Terraform directory not found: $TERRAFORM_DIR"
    exit 1
fi

# Change to Terraform directory
cd "$TERRAFORM_DIR"

# Check if Terraform is initialized
if [[ ! -d ".terraform" ]]; then
    print_error "Terraform not initialized. Run 'terraform init' first."
    exit 1
fi

# Get WebSocket endpoint from Terraform outputs
print_status "Retrieving WebSocket endpoint from Terraform..."

if ! terraform output > /dev/null 2>&1; then
    print_error "Failed to get Terraform outputs. Make sure infrastructure is deployed."
    exit 1
fi

# Extract WebSocket URL
WEBSOCKET_URL=$(terraform output -raw websocket_api_invoke_url 2>/dev/null || echo "")

if [[ -z "$WEBSOCKET_URL" ]]; then
    print_error "WebSocket URL not found in Terraform outputs."
    print_error "Make sure Phase 3 (WebSocket) infrastructure is deployed."
    exit 1
fi

# Add wss:// protocol if not present
if [[ ! "$WEBSOCKET_URL" =~ ^wss:// ]]; then
    WEBSOCKET_URL="wss://$WEBSOCKET_URL"
fi

print_success "WebSocket URL: $WEBSOCKET_URL"
echo

# Check Python dependencies
print_status "Checking Python dependencies..."

if ! python3 -c "import websockets" 2>/dev/null; then
    print_warning "websockets library not found. Installing..."
    if ! pip3 install websockets 2>/dev/null; then
        print_error "Failed to install websockets library"
        print_error "Try: pip3 install websockets"
        exit 1
    fi
    print_success "websockets library installed"
fi

# Check if test script exists
PYTHON_TEST_SCRIPT="$SCRIPT_DIR/websocket_client_test.py"
if [[ ! -f "$PYTHON_TEST_SCRIPT" ]]; then
    print_error "Python test script not found: $PYTHON_TEST_SCRIPT"
    exit 1
fi

# Make test script executable
chmod +x "$PYTHON_TEST_SCRIPT"

# Run tests
print_status "Running WebSocket tests..."
echo "=" * 60

# Set verbosity
if [[ "$VERBOSE" == "true" ]]; then
    VERBOSE_FLAG=""
else
    VERBOSE_FLAG=""  # Add any verbosity flags here if needed
fi

# Execute Python test script
TEST_COMMAND="python3 '$PYTHON_TEST_SCRIPT' '$WEBSOCKET_URL' --user-id '$USER_ID' --test '$TEST_TYPE'"

if [[ "$VERBOSE" == "true" ]]; then
    print_status "Executing: $TEST_COMMAND"
fi

# Run the test and capture exit code
set +e  # Don't exit on error temporarily
eval "$TEST_COMMAND"
TEST_EXIT_CODE=$?
set -e

echo
echo "=" * 60

# Report results
if [[ $TEST_EXIT_CODE -eq 0 ]]; then
    print_success "All tests completed successfully! ✅"
    
    # Additional info for successful tests
    echo
    print_status "WebSocket endpoint tested: $WEBSOCKET_URL"
    print_status "Environment: $ENVIRONMENT"
    print_status "User ID: $USER_ID"
    
    if [[ "$TEST_TYPE" == "all" ]]; then
        echo
        print_status "Test Coverage:"
        echo "  ✅ Connection establishment and teardown"
        echo "  ✅ Ping/pong heartbeat functionality"
        echo "  ✅ Chat message sending and acknowledgment"
        echo "  ✅ AI response generation via Bedrock"
        echo "  ✅ Error handling for invalid messages"
        echo "  ✅ Load testing with multiple messages"
    fi
    
else
    print_error "Tests failed with exit code: $TEST_EXIT_CODE ❌"
    
    echo
    print_status "Troubleshooting tips:"
    echo "  1. Check if the infrastructure is properly deployed:"
    echo "     terraform plan"
    echo "  2. Verify WebSocket endpoint is accessible:"
    echo "     curl -I https://$(echo $WEBSOCKET_URL | sed 's/wss:\/\///')"
    echo "  3. Check CloudWatch logs for Lambda errors"
    echo "  4. Verify Bedrock agent is properly configured"
    
    exit $TEST_EXIT_CODE
fi

# Optional: Run Node.js tests if available
NODE_TEST_SCRIPT="$SCRIPT_DIR/websocket_client_node.js"
if [[ -f "$NODE_TEST_SCRIPT" ]] && command -v node >/dev/null 2>&1; then
    echo
    read -p "Run Node.js tests as well? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_status "Running Node.js tests..."
        
        # Check Node.js dependencies
        if [[ ! -d "$SCRIPT_DIR/node_modules" ]]; then
            print_status "Installing Node.js dependencies..."
            cd "$SCRIPT_DIR"
            npm init -y > /dev/null 2>&1 || true
            npm install ws uuid > /dev/null 2>&1 || print_warning "Failed to install Node.js dependencies"
            cd "$TERRAFORM_DIR"
        fi
        
        chmod +x "$NODE_TEST_SCRIPT"
        
        if node "$NODE_TEST_SCRIPT" "$WEBSOCKET_URL" "$USER_ID"; then
            print_success "Node.js tests completed successfully! ✅"
        else
            print_warning "Node.js tests failed ⚠️"
        fi
    fi
fi

echo
print_success "Test run completed! 🎉"
