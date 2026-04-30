# BuffettGPT Documentation

Welcome to the BuffettGPT documentation. BuffettGPT is a full-stack serverless financial chat application built on AWS that provides a Warren Buffett-themed AI advisor for investment and financial planning questions.

## Quick Links

<div class="grid cards" markdown>

- :material-rocket-launch: **[Getting Started](getting-started/index.md)**

    Set up your development environment and learn the basics

- :material-chart-tree: **[Architecture](architecture/index.md)**

    Understand the system design and component relationships

- :material-api: **[API Reference](api/index.md)**

    Complete API documentation for HTTP and WebSocket endpoints

- :material-file-document: **[Investment Research](investment-research/index.md)**

    Learn about the AI-powered investment report generation system

</div>

## Features

- **AI-Powered Financial Advice**: Uses Amazon Bedrock (Claude) with custom knowledge bases and guardrails
- **Real-Time Chat**: WebSocket-based streaming responses with typewriter effect
- **Investment Reports**: Comprehensive company analysis with DJIA 30 coverage
- **Follow-up Q&A**: Context-aware follow-up questions on generated reports
- **Multi-User Support**: Google OAuth authentication with rate limiting

## Technology Stack

| Layer | Technologies |
|-------|--------------|
| **Frontend** | React 18, Vite 5, Tailwind CSS |
| **Backend** | Python 3.11, AWS Lambda, API Gateway |
| **AI/ML** | Amazon Bedrock, Claude Haiku, Knowledge Bases |
| **Database** | DynamoDB (8 tables) |
| **Infrastructure** | Terraform, CloudFront, SQS, KMS |

## Repository Structure

```
buffett_chat_api/
├── chat-api/                 # Backend API and infrastructure
│   ├── backend/              # Lambda functions and utilities
│   └── terraform/            # Infrastructure as Code
├── frontend/                 # React + Vite frontend
└── docs/                     # This documentation
```

## Getting Help

- **[Installation Guide](getting-started/installation.md)** - Set up your local environment
- **[Troubleshooting](reference/troubleshooting.md)** - Common issues and solutions
- **[API Routes](api/routes.md)** - Complete endpoint reference
