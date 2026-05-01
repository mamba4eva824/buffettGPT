# Build context: chat-api/backend/
# (so we can COPY src/ + investment_research/ alongside lambda/analysis_followup/)
#
# Build:
#   docker build -f lambda/analysis_followup/Dockerfile -t buffett/analysis-followup:<tag> .
FROM public.ecr.aws/lambda/python:3.11

# Lambda Web Adapter — converts HTTP requests to Lambda invocations + RESPONSE_STREAM.
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4 /lambda-adapter /opt/extensions/lambda-adapter
RUN chmod +x /opt/extensions/lambda-adapter

WORKDIR ${LAMBDA_TASK_ROOT}

# Python deps installed straight into LAMBDA_TASK_ROOT so they sit on sys.path.
COPY lambda/analysis_followup/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Canonical handler tree. Imports use top-level `handlers.*`, `utils.*`,
# `investment_research.*` — copy each module to the task-root so PYTHONPATH
# (defaulting to /var/task via LAMBDA_TASK_ROOT) resolves them without prefixes.
COPY src/handlers/ ./handlers/
COPY src/utils/ ./utils/
COPY investment_research/ ./investment_research/

# FastAPI entry-point (thin wrapper around handlers.analysis_followup).
COPY lambda/analysis_followup/app.py ./app.py

ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV AWS_LWA_INVOKE_MODE=RESPONSE_STREAM
ENV AWS_LWA_PORT=8080
ENV PORT=8080

# Override the base image's Lambda-handler entrypoint so uvicorn serves
# FastAPI directly; LWA bridges Lambda invocations to HTTP.
ENTRYPOINT []
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
