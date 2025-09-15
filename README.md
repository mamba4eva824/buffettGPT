# Buffett Chat API

A comprehensive chat API system built with AWS infrastructure, featuring real-time WebSocket communication, authentication, and integration with financial data sources.

## 🏗️ Architecture

This project consists of three main components:

- **Backend API** (`chat-api/`): AWS Lambda-based serverless backend with WebSocket and HTTP APIs
- **Frontend** (`frontend/`): React-based web application with Vite build system
- **Infrastructure** (`chat-api/terraform/`): Terraform configurations for AWS resources

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Node.js 16+
- AWS CLI configured
- Terraform 1.0+

### Backend Setup

```bash
cd chat-api
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### Infrastructure Deployment

```bash
cd chat-api/terraform
terraform init
terraform plan
terraform apply
```

## 📁 Project Structure

```
buffett_chat_api/
├── chat-api/                 # Backend API and Lambda functions
│   ├── backend/             # Core backend logic
│   ├── lambda-auth/         # Authentication Lambda functions
│   ├── terraform/           # Infrastructure as Code
│   └── scripts/             # Deployment and utility scripts
├── frontend/                # React frontend application
│   ├── src/                 # Source code
│   └── dist/                # Build output
└── .gitignore              # Git ignore rules
```

## 🔧 Development

### Backend Development

The backend uses AWS Lambda functions for:
- HTTP API endpoints
- WebSocket connection management
- Authentication and authorization
- Chat message processing

### Frontend Development

The frontend is built with:
- React 18
- Vite for build tooling
- Tailwind CSS for styling
- WebSocket client for real-time communication

## 🚀 Deployment

### Environment Setup

1. Copy `terraform.tfvars.example` to `terraform.tfvars`
2. Configure your AWS credentials
3. Set appropriate environment variables

### Infrastructure

Deploy infrastructure using Terraform:

```bash
cd chat-api/terraform
terraform init
terraform plan -var-file="environments/prod.tfvars"
terraform apply -var-file="environments/prod.tfvars"
```

### Application Deployment

Use the provided deployment scripts:

```bash
cd chat-api/scripts/deployment
./deploy.sh
```

## 📋 Features

- **Real-time Chat**: WebSocket-based messaging
- **Authentication**: JWT-based user authentication
- **Rate Limiting**: API rate limiting and throttling
- **Monitoring**: CloudWatch integration
- **Scalability**: Auto-scaling Lambda functions
- **Security**: IAM roles and policies

## 🔒 Security

- Environment variables for sensitive data
- IAM roles with least privilege
- VPC configuration for network isolation
- API Gateway authentication
- Input validation and sanitization

## 📊 Monitoring

- CloudWatch logs and metrics
- X-Ray tracing for debugging
- Custom dashboards for key metrics
- Alerting for critical issues

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🆘 Support

For issues and questions:
1. Check the documentation in `docs/`
2. Review existing issues
3. Create a new issue with detailed information

## 📝 Notes

- Large files and build artifacts have been moved to `cleanup_backup/` directory
- Virtual environments and node_modules are excluded from version control
- Terraform state files are excluded for security
- Build artifacts (ZIP files) are generated during deployment

## 🔄 Cleanup

The following items were cleaned up before adding to version control:
- Virtual environments (`venv/`, `node_modules/`)
- Build artifacts (`*.zip`, `dist/`, `build/`)
- Terraform state files (`*.tfstate*`)
- Archive and backup files
- Large deployment packages

These can be regenerated using the setup instructions above.
