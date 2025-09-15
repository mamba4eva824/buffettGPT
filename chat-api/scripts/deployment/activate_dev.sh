#!/bin/bash

# Development environment activation script
# Usage: source activate_dev.sh

echo "🚀 Activating Buffett Chat API development environment..."

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✅ Virtual environment activated"
else
    echo "❌ Virtual environment not found. Please run: python -m venv venv && pip install -r requirements.txt"
    return 1
fi

# Set up environment variables for local development
python -c "from local_config import setup_test_environment; setup_test_environment()"

# Show current environment
echo ""
echo "📊 Development Environment Status:"
echo "   Python: $(python --version)"
echo "   Virtual Env: $VIRTUAL_ENV"
echo "   AWS Region: ${AWS_REGION:-'Not set'}"
echo "   Project: ${PROJECT_NAME:-'Not set'}"
echo ""
echo "🔧 Available commands:"
echo "   pytest                    - Run all tests"
echo "   pytest tests/ -v          - Run tests with verbose output"
echo "   black lambda-functions/   - Format code"
echo "   flake8 lambda-functions/  - Check code style"
echo "   python local_config.py    - Setup test environment"
echo ""
echo "📁 Useful directories:"
echo "   lambda-functions/         - Lambda function source code"
echo "   tests/                    - Test files"
echo "   terraform.tfvars          - Infrastructure configuration"
echo ""
echo "🎉 Ready for development! Run 'pytest tests/ -v' to verify setup."
