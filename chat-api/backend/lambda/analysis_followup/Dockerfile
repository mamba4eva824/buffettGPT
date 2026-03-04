FROM public.ecr.aws/lambda/python:3.11

# Lambda Web Adapter — enables HTTP streaming via RESPONSE_STREAM
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4 /lambda-adapter /opt/extensions/lambda-adapter
RUN chmod +x /opt/extensions/lambda-adapter

WORKDIR ${LAMBDA_TASK_ROOT}

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    "boto3>=1.34.0" \
    "botocore>=1.34.0" \
    "fastapi>=0.109.0" \
    "uvicorn>=0.27.0" \
    "sse-starlette>=1.6.0" \
    "pydantic>=2.0.0" \
    "PyJWT>=2.8.0" \
    --target "${LAMBDA_TASK_ROOT}"

COPY app.py .
COPY utils/ ./utils/

ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV AWS_LWA_INVOKE_MODE=RESPONSE_STREAM
ENV AWS_LWA_PORT=8080
ENV PORT=8080

ENTRYPOINT []
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
