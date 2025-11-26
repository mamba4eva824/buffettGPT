# Debt Analyzer Lambda Container
# Optimized for AWS Lambda with CPU-bound gradient boosting inference

ARG MODEL_VERSION=0.1.0
ARG BUILD_DATE
ARG GIT_COMMIT
# Base Image - AWS Lambda Python 3.11
FROM public.ecr.aws/lambda/python:3.11

# Metadata
LABEL maintainer="Buffett Chat Team"
LABEL version="${MODEL_VERSION}"
LABEL description="Debt Analyzer Agent - ML-powered debt analysis"
LABEL build_date="${BUILD_DATE}"
LABEL git_commit="${GIT_COMMIT}"


# Install System Dependencies
# Install GCC for building numpy/scipy wheels (if needed)
RUN yum install -y gcc gcc-c++ && \
    yum clean all && \
    rm -rf /var/cache/yum

# Set Working Directory
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy and Install Python Dependencies
# Copy requirements first (Docker layer caching)
COPY requirements.txt .

# Install Python packages
# --no-cache-dir: Don't cache downloaded packages (saves space)
# --target: Install to Lambda task root
RUN pip install --no-cache-dir \
    --upgrade pip && \
    pip install --no-cache-dir \
    -r requirements.txt \
    --target "${LAMBDA_TASK_ROOT}"

# Copy handler
COPY handler.py .

# Copy utilities
COPY utils/ ./utils/

# Note: Model is NOT baked into image - downloaded from S3 at runtime
# This keeps image small and allows model updates without redeployment
# Environment Variables (Defaults)

ENV MODEL_VERSION=${MODEL_VERSION}
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO


# Lambda Handler
CMD ["handler.lambda_handler"]
