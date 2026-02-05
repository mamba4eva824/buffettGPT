# Installation

This guide covers setting up your local development environment for BuffettGPT.

## Prerequisites

Before you begin, ensure you have the following installed:

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Backend Lambda functions |
| Node.js | 18+ | Frontend React application |
| Terraform | 1.9.1+ | Infrastructure deployment |
| AWS CLI | 2.x | AWS resource management |
| Git | 2.x | Version control |

## Clone the Repository

```bash
git clone https://github.com/your-org/buffett_chat_api.git
cd buffett_chat_api
```

## Backend Setup

### 1. Create Virtual Environment

```bash
cd chat-api/backend
make venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
make dev-install
```

### 3. Verify Installation

```bash
make test
```

## Frontend Setup

### 1. Install Node Dependencies

```bash
cd frontend
npm install
```

### 2. Configure Environment

Create `.env.local` from the example:

```bash
cp .env.example .env.local
```

Edit `.env.local` with your configuration:

```env
VITE_WEBSOCKET_URL=wss://your-ws-endpoint
VITE_REST_API_URL=https://your-api-endpoint
VITE_GOOGLE_CLIENT_ID=your-google-client-id
VITE_ENVIRONMENT=dev
```

### 3. Start Development Server

```bash
npm run dev
```

The frontend will be available at `http://localhost:3000`.

## AWS Configuration

### 1. Configure AWS CLI

```bash
aws configure
```

Enter your:
- AWS Access Key ID
- AWS Secret Access Key
- Default region (e.g., `us-east-1`)
- Output format (e.g., `json`)

### 2. Verify AWS Access

```bash
aws sts get-caller-identity
```

## Terraform Setup

### 1. Initialize Backend

```bash
cd chat-api/terraform/backend-setup
terraform init
terraform apply
```

### 2. Initialize Environment

```bash
cd ../environments/dev
terraform init
terraform validate
```

## Verification

### Backend Health Check

```bash
cd chat-api/backend
make run-http
# In another terminal:
curl http://localhost:8000/health
```

### Frontend Build Test

```bash
cd frontend
npm run build
npm run lint  # Should pass with 0 warnings
```

### Terraform Validation

```bash
cd chat-api/terraform/environments/dev
terraform validate
terraform plan
```

## Troubleshooting

### Python Version Issues

If you encounter Python version issues:

```bash
pyenv install 3.11
pyenv local 3.11
```

### Node.js Version Issues

Use nvm to manage Node versions:

```bash
nvm install 18
nvm use 18
```

### AWS Credentials

If AWS commands fail, verify your credentials:

```bash
cat ~/.aws/credentials
aws sts get-caller-identity
```

## Next Steps

- [Generate your first report](claude-code-workflow.md)
- [Explore the architecture](../architecture/index.md)
- [Review API documentation](../api/index.md)
