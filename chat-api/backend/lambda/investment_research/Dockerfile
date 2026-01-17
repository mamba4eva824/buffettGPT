# Investment Research Lambda Container
# Optimized for AWS Lambda - Simple DynamoDB reads + SSE streaming
# Uses Lambda Web Adapter for Python response streaming with FastAPI
#
# Key differences from prediction_ensemble:
# - NO ML dependencies (xgboost, sklearn, numpy)
# - NO system build tools (gcc, g++)
# - Much smaller image size (~200MB vs ~500MB+)
# - Same LWA v0.8.4 pattern for SSE streaming

ARG BUILD_DATE
ARG GIT_COMMIT

# Base Image - AWS Lambda Python 3.11
FROM public.ecr.aws/lambda/python:3.11

# =============================================================================
# Lambda Web Adapter - Enables Python response streaming
# https://github.com/awslabs/aws-lambda-web-adapter
# =============================================================================
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4 /lambda-adapter /opt/extensions/lambda-adapter
RUN chmod +x /opt/extensions/lambda-adapter

# Metadata
LABEL maintainer="Deep Value Insights Team"
LABEL version="1.0.0"
LABEL description="Investment Research - Cached report streaming via FastAPI"
LABEL build_date="${BUILD_DATE}"
LABEL git_commit="${GIT_COMMIT}"

# Set Working Directory
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy requirements first (for Docker layer caching)
COPY requirements.txt .

# =============================================================================
# Install Python Dependencies
# NO system build tools needed - all packages have pre-built wheels
# =============================================================================
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    "boto3>=1.34.0" \
    "botocore>=1.34.0" \
    "fastapi>=0.109.0" \
    "uvicorn>=0.27.0" \
    "sse-starlette>=1.6.0" \
    "pydantic>=2.0.0" \
    --target "${LAMBDA_TASK_ROOT}"

# Copy application files
COPY app.py .
COPY handler.py .
COPY config/ ./config/
COPY services/ ./services/
COPY models/ ./models/

# Set permissions for Lambda runtime (runs as non-root user)
RUN chmod -R 755 ${LAMBDA_TASK_ROOT}

# =============================================================================
# Environment Variables for Lambda Web Adapter
# =============================================================================
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
# Lambda Web Adapter configuration
ENV AWS_LWA_INVOKE_MODE=RESPONSE_STREAM
ENV AWS_LWA_PORT=8080
ENV PORT=8080

# =============================================================================
# Run FastAPI with uvicorn (Lambda Web Adapter will proxy requests)
# =============================================================================
# Clear the Lambda base image entrypoint and run uvicorn directly
ENTRYPOINT []
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
