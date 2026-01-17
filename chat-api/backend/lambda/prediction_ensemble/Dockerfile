# Prediction Ensemble Lambda Container
# Optimized for AWS Lambda with ML inference (XGBoost/scikit-learn)
# Uses Lambda Web Adapter for Python response streaming with FastAPI

ARG MODEL_VERSION=0.1.0
ARG BUILD_DATE
ARG GIT_COMMIT

# Base Image - AWS Lambda Python 3.11
FROM public.ecr.aws/lambda/python:3.11

# ============================================================================
# Lambda Web Adapter - Enables Python response streaming
# https://github.com/awslabs/aws-lambda-web-adapter
# Use latest stable version from AWS official ECR
# ============================================================================
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4 /lambda-adapter /opt/extensions/lambda-adapter
RUN chmod +x /opt/extensions/lambda-adapter

# Metadata
LABEL maintainer="Buffett Chat Team"
LABEL version="${MODEL_VERSION}"
LABEL description="Prediction Ensemble - 3-model ML inference with Bedrock streaming via FastAPI"
LABEL build_date="${BUILD_DATE}"
LABEL git_commit="${GIT_COMMIT}"

# Install System Dependencies
RUN yum install -y gcc gcc-c++ && \
    yum clean all && \
    rm -rf /var/cache/yum

# Set Working Directory
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy and Install Python Dependencies
COPY requirements.txt .

# Install Python packages in two steps:
# 1. Install packages with binary wheels (--only-binary for ML packages)
# 2. Install pure Python packages that don't have wheels
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --only-binary :all: \
    "xgboost>=2.0.0" "scikit-learn>=1.3.0" "numpy>=1.24.0,<2.0.0" "joblib>=1.3.0" \
    "boto3>=1.34.0" "botocore>=1.34.0" \
    "fastapi>=0.109.0" "uvicorn>=0.27.0" "sse-starlette>=1.6.0" \
    "httpx>=0.27.0" "PyJWT>=2.8.0" "python-dateutil>=2.8.0" \
    --target "${LAMBDA_TASK_ROOT}" && \
    pip install --no-cache-dir \
    "lwa-fastapi-middleware-bedrock-agent>=0.0.4" \
    --target "${LAMBDA_TASK_ROOT}"

# Copy application files
COPY app.py .
COPY handler.py .
COPY utils/ ./utils/
COPY config/ ./config/
COPY models/ ./models/
COPY handlers/ ./handlers/
COPY services/ ./services/

# Set permissions for Lambda runtime (runs as non-root user)
RUN chmod -R 755 ${LAMBDA_TASK_ROOT}

# ============================================================================
# Environment Variables for Lambda Web Adapter
# ============================================================================
ENV MODEL_VERSION=${MODEL_VERSION}
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
# Lambda Web Adapter configuration
ENV AWS_LWA_INVOKE_MODE=RESPONSE_STREAM
ENV AWS_LWA_PORT=8080
ENV PORT=8080

# ============================================================================
# Run FastAPI with uvicorn (Lambda Web Adapter will proxy requests)
# ============================================================================
# Clear the Lambda base image entrypoint and run uvicorn directly
ENTRYPOINT []
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
