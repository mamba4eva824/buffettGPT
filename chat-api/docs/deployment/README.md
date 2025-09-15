# Backend Dev Environment (Python / AWS Lambda)

This folder contains Terraform and Lambda function code for the Buffett Chat API backend. The steps below set up a lightweight local Python environment to lint, run, and iterate on the Lambda handlers.

## Prerequisites

- Python 3.10+ installed and on PATH
- AWS credentials configured (e.g., via `aws configure` or environment variables)

## Quick Start

1) Create a virtual environment and install deps:

```bash
cd chat-api
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -U pip
pip install -r requirements.txt
```

2) Configure environment variables (optional for local):

```bash
cp .env.example .env
# Edit .env to set table names, queue URL, Bedrock values, etc.
```

3) Run a handler locally with a sample event:

```bash
source .venv/bin/activate
python - <<'PY'
import os, json
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).with_name('.env'))
except Exception:
    pass
from lambda-functions.chat_http_handler import lambda_handler

with open('events/sample_http_event.json') as f:
    event = json.load(f)
print(lambda_handler(event, {}))
PY
```

Notes:
- The Lambda code uses boto3 to access AWS services. For purely offline tests, you may want to stub AWS with libraries like `moto` or inject mocks in your own test harness.
- Live AWS calls require valid AWS credentials and existing resources (tables/queues) aligned with values in your `.env`.

## Handy Make Targets (Optional)

A `Makefile` is included for convenience:

```bash
make venv       # Create venv
make install    # Install requirements in venv
make run-http   # Invoke chat_http_handler with sample event
```

## Structure

- `lambda-functions/` — Python AWS Lambda handlers
- `requirements.txt` — Minimal runtime dependencies
- `events/` — Example payloads for local runs
- Terraform files — AWS infra definitions

## Next Steps

- Add tests under `chat-api/tests` or your preferred location
- Expand requirements as you add SDKs/utilities
- Use the Terraform stack here to provision AWS infra for end-to-end testing

