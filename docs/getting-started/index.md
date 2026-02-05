# Getting Started

This section covers everything you need to set up and start working with BuffettGPT.

## Overview

BuffettGPT is a serverless application that requires:

- **Python 3.11** for Lambda functions
- **Node.js 18+** for the React frontend
- **Terraform 1.9.1+** for infrastructure deployment
- **AWS CLI** configured with appropriate credentials

## Quick Start

1. **[Installation](installation.md)** - Set up your local development environment
2. **[Claude Code Workflow](claude-code-workflow.md)** - Learn how to generate investment reports

## Prerequisites

Before you begin, ensure you have:

- [ ] AWS account with appropriate IAM permissions
- [ ] Google OAuth credentials for authentication
- [ ] Python 3.11 installed
- [ ] Node.js 18+ installed
- [ ] Terraform 1.9.1+ installed

## Development Workflow

### Backend Development

```bash
cd chat-api/backend
make venv           # Create virtual environment
make dev-install    # Install dependencies
make test           # Run tests
make run-http       # Test HTTP handler locally
```

### Frontend Development

```bash
cd frontend
npm install         # Install dependencies
npm run dev         # Start dev server (port 3000)
npm run build       # Production build
npm run lint        # ESLint (0 warnings policy)
```

### Infrastructure Deployment

```bash
cd chat-api/terraform/environments/dev
terraform init      # Initialize Terraform
terraform validate  # Validate configuration
terraform plan      # Preview changes
terraform apply     # Apply changes
```

## Next Steps

- Read the [Installation Guide](installation.md) for detailed setup instructions
- Learn about the [System Architecture](../architecture/system-overview.md)
- Explore the [API Reference](../api/index.md)
