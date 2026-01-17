# Followup Action Lambda - Bedrock Action Group Handler
# Handles action group invocations for investment research follow-up questions
#
# No Lambda Web Adapter needed - this is a standard Lambda handler
# that returns Bedrock action group JSON format directly

FROM public.ecr.aws/lambda/python:3.11

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . ${LAMBDA_TASK_ROOT}

# Set the handler
CMD ["handler.lambda_handler"]
