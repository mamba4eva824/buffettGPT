#!/bin/bash
# =============================================================================
# Mobile Testing Helper Script
# =============================================================================
# Purpose: Start Vite dev server with network access for mobile testing
# Usage: ./scripts/test_mobile.sh
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Configuration
FRONTEND_DIR="frontend"
DEFAULT_PORT=5173

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

log_header() {
    echo -e "${CYAN}$1${NC}"
}

log_highlight() {
    echo -e "${MAGENTA}$1${NC}"
}

# Function to get local IP address
get_local_ip() {
    # Try multiple methods to get local IP
    local ip=""

    # Method 1: ifconfig (macOS/Linux)
    if command -v ifconfig &> /dev/null; then
        ip=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -1)
    fi

    # Method 2: ip command (Linux)
    if [ -z "$ip" ] && command -v ip &> /dev/null; then
        ip=$(ip addr show | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | cut -d/ -f1 | head -1)
    fi

    # Method 3: hostname (fallback)
    if [ -z "$ip" ]; then
        ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    fi

    echo "$ip"
}

# Function to check if port is available
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 1
    else
        return 0
    fi
}

# Function to display banner
show_banner() {
    echo ""
    log_header "╔════════════════════════════════════════════════════════════╗"
    log_header "║           BuffettGPT Mobile Testing Server                ║"
    log_header "╚════════════════════════════════════════════════════════════╝"
    echo ""
}

# Function to display instructions
show_instructions() {
    local ip=$1
    local port=$2

    echo ""
    log_success "╔════════════════════════════════════════════════════════════╗"
    log_success "║              Mobile Testing Server Started!                ║"
    log_success "╚════════════════════════════════════════════════════════════╝"
    echo ""

    log_info "📱 To test on your phone:"
    echo ""
    echo "   1. Make sure your phone is on the same WiFi network as this laptop"
    echo ""
    echo "   2. Open a browser on your phone and navigate to:"
    echo ""
    log_highlight "      ┌─────────────────────────────────────────────┐"
    log_highlight "      │   http://${ip}:${port}    │"
    log_highlight "      └─────────────────────────────────────────────┘"
    echo ""

    log_info "💡 Testing Checklist:"
    echo "   ✓ Send button (touch interaction)"
    echo "   ✓ Topic dropdowns (centering on mobile)"
    echo "   ✓ Hamburger menu and sidebar"
    echo "   ✓ Delete confirmation modal"
    echo "   ✓ Input field with mobile keyboard"
    echo "   ✓ Message bubble sizing"
    echo "   ✓ Dark mode toggle"
    echo ""

    log_info "🔄 Hot Reload Enabled:"
    echo "   Changes to your code will automatically update on your phone!"
    echo ""

    log_warning "Press Ctrl+C to stop the server"
    echo ""
    log_header "════════════════════════════════════════════════════════════"
    echo ""
}

# Main execution
main() {
    show_banner

    # Check if in correct directory
    if [ ! -d "$FRONTEND_DIR" ]; then
        log_error "Frontend directory not found!"
        echo "Please run this script from the project root directory."
        exit 1
    fi

    log_info "Checking frontend dependencies..."

    # Check if node_modules exists
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        log_warning "Dependencies not installed. Installing now..."
        cd "$FRONTEND_DIR"
        npm install
        cd ..
        log_success "Dependencies installed!"
    else
        log_success "Dependencies already installed"
    fi

    # Get local IP
    log_info "Detecting local IP address..."
    LOCAL_IP=$(get_local_ip)

    if [ -z "$LOCAL_IP" ]; then
        log_error "Could not detect local IP address"
        echo "Please check your network connection and try again."
        exit 1
    fi

    log_success "Local IP detected: $LOCAL_IP"

    # Check if port is available
    if ! check_port $DEFAULT_PORT; then
        log_warning "Port $DEFAULT_PORT is already in use"
        log_info "Trying to stop existing process..."
        lsof -ti:$DEFAULT_PORT | xargs kill -9 2>/dev/null || true
        sleep 1
    fi

    # Show instructions before starting server
    show_instructions "$LOCAL_IP" "$DEFAULT_PORT"

    # Start Vite dev server with network access
    log_info "Starting Vite dev server..."
    echo ""

    cd "$FRONTEND_DIR"
    npm run dev -- --host --port $DEFAULT_PORT

    # This will only execute if the server is stopped
    echo ""
    log_info "Server stopped."
}

# Cleanup on exit
cleanup() {
    echo ""
    log_info "Cleaning up..."
    # Kill any remaining node processes on the port
    lsof -ti:$DEFAULT_PORT | xargs kill -9 2>/dev/null || true
    log_success "Cleanup complete"
    exit 0
}

# Set up trap for cleanup
trap cleanup EXIT INT TERM

# Run main function
main "$@"
