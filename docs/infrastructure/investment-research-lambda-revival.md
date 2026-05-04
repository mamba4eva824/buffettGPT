# Investment Research Lambda — Revival Runbook

`buffett-dev-investment-research` is a Docker/Image-based Lambda
(FastAPI + Lambda Web Adapter, RESPONSE_STREAM Function URL). It serves
cached v2 investment reports from DynamoDB as SSE events.

This runbook covers the recovery path when the function URL returns
502 / Internal Server Error and the dev-deploy smoke test
(`Investment Research - Health Check`, `Investment Research - TOC Fetch (AAPL)`)
has been failing in CI.

## Symptom

- AWS Lambda console shows the function in state `Inactive`
  with `LastModified` 8+ weeks ago.
- `https://<function-url>/health` returns HTTP 502.
- `Investment Research - Health Check` and
  `Investment Research - TOC Fetch (AAPL)` fail in every
  `deploy-dev.yml` smoke-test job (see PR #53 PR body for the
  pre-existing-failure notation).

## Why this happens

The Lambda's Docker image is rebuilt and `update-function-code`'d **only**
when something under `chat-api/backend/lambda/investment_research/` changes
(see `.github/workflows/deploy-dev.yml`, `detect-changes` job, line
`IR_CHANGED=$(git diff --name-only HEAD^ HEAD | grep -q "chat-api/backend/lambda/investment_research/" ...)`).
The last commit touching that path was `7595df3` on 2026-03-02.

In parallel, AWS Lambda marks any function `Inactive` after ~14 days of no
invocations and reclaims its underlying compute resources. The next
invocation triggers an asynchronous reactivation that re-pulls the image
and restarts the container. If that reactivation fails repeatedly (image
gone from ECR, image manifest unsupported, container start hits an
unrecoverable error, IAM regression), the Lambda settles into a state
where every invocation immediately returns 502 until something pushes a
**fresh** image and runs `update-function-code`.

That "something" hasn't happened for `investment-research` in 8+ weeks
because no code in its source path has changed.

## Recovery

The cleanest fix is to trigger the existing CI job. It will rebuild the
image, push fresh `:<sha>` and `:latest` tags, run
`aws lambda update-function-code`, wait for `function-updated`, and curl
`/health` to confirm reactivation.

### Option A — workflow_dispatch (preferred)

From the GitHub UI: *Actions → Deploy to Dev → Run workflow* on `dev`,
with `build_investment_research = true`. Or via `gh`:

```bash
gh workflow run deploy-dev.yml \
  --ref dev \
  -f build_investment_research=true
```

The `build-docker-lambdas` matrix entry for `investment-research` will:

1. Build `lambda/investment_research/Dockerfile`
   (context `chat-api/backend/lambda/investment_research`).
2. Push to ECR as
   `<acct>.dkr.ecr.us-east-1.amazonaws.com/buffett/investment-research:<sha>`
   and `:latest`.
3. `aws lambda update-function-code --function-name buffett-dev-investment-research --image-uri <acct>...:<sha>`.
4. `aws lambda wait function-updated`.
5. `curl -s -o /dev/null -w "%{http_code}" "${FUNC_URL}health"` —
   must be `200`.

### Option B — local rebuild + push (if CI is broken)

Requires AWS credentials with ECR push, Docker, and platform
`linux/amd64` (use `--platform linux/amd64` on Apple Silicon).

```bash
ACCT=430118826061
REGION=us-east-1
REPO=buffett/investment-research
TAG=manual-$(date +%Y%m%d-%H%M%S)

cd chat-api/backend/lambda/investment_research

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ACCT.dkr.ecr.$REGION.amazonaws.com"

docker build --platform linux/amd64 -t "$REPO:$TAG" .

docker tag "$REPO:$TAG" "$ACCT.dkr.ecr.$REGION.amazonaws.com/$REPO:$TAG"
docker tag "$REPO:$TAG" "$ACCT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest"

docker push "$ACCT.dkr.ecr.$REGION.amazonaws.com/$REPO:$TAG"
docker push "$ACCT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest"

aws lambda update-function-code \
  --function-name buffett-dev-investment-research \
  --image-uri "$ACCT.dkr.ecr.$REGION.amazonaws.com/$REPO:$TAG" \
  --region "$REGION"

aws lambda wait function-updated \
  --function-name buffett-dev-investment-research \
  --region "$REGION"

FUNC_URL=$(aws lambda get-function-url-config \
  --function-name buffett-dev-investment-research \
  --query 'FunctionUrl' --output text)
curl -s -o /dev/null -w "%{http_code}\n" "${FUNC_URL}health"
# expect 200
```

## Pre-recovery diagnostics (optional but useful)

If the smoke test still fails after Option A, work through these to
narrow the failure mode before retrying. All commands assume
`AWS_REGION=us-east-1`.

1. **State + image URI**
   ```bash
   aws lambda get-function \
     --function-name buffett-dev-investment-research \
     --query 'Configuration.[State,StateReason,StateReasonCode,LastUpdateStatus,LastUpdateStatusReason,Code.ImageUri]' \
     --output table
   ```
   `StateReasonCode = ImageDeleted` / `ImageAccessDenied` / `InvalidImage` points
   directly at ECR or IAM. `InternalError` usually means container startup.

2. **Image still in ECR**
   ```bash
   # parse the tag from Code.ImageUri above
   aws ecr describe-images \
     --repository-name buffett/investment-research \
     --image-ids imageTag=<tag> \
     --query 'imageDetails[0].[imageDigest,imagePushedAt]'
   ```

3. **Force-trigger reactivation and capture the error**
   ```bash
   aws lambda invoke \
     --function-name buffett-dev-investment-research \
     --payload '{"requestContext":{"http":{"method":"GET","path":"/health"}},"rawPath":"/health","headers":{}}' \
     --cli-binary-format raw-in-base64-out /tmp/inv_out.json
   cat /tmp/inv_out.json
   ```

4. **CloudWatch INIT_ERROR / Runtime exited**
   ```bash
   aws logs filter-log-events \
     --log-group-name /aws/lambda/buffett-dev-investment-research \
     --start-time $(node -e "console.log(Date.now() - 14*24*3600*1000)") \
     --filter-pattern '?ERROR ?Exception ?Traceback ?"INIT_ERROR" ?"Runtime exited"' \
     --query 'events[-30:].message' --output text
   ```

5. **Compare against the working analog** (`buffett-dev-analysis-followup`)
   for image URI / role / env-vars / memory drift:
   ```bash
   diff \
     <(aws lambda get-function --function-name buffett-dev-investment-research --query 'Configuration.[Code.ImageUri,Role,Environment,Timeout,MemorySize]') \
     <(aws lambda get-function --function-name buffett-dev-analysis-followup   --query 'Configuration.[Code.ImageUri,Role,Environment,Timeout,MemorySize]')
   ```

## Preventing recurrence

This is a structural CI pattern: Docker Lambdas whose source rarely
changes drift into the Inactive state and silently rot. Follow-up work
to consider (out of scope for this runbook):

- Add a periodic `workflow_dispatch` (e.g. weekly) that rebuilds and
  redeploys investment-research even when no source changed, so the
  image is exercised and the Lambda stays Active.
- Add a low-frequency EventBridge rule that pings `/health` (e.g. every
  6 hours) so the function never goes Inactive in the first place.
- Mirror analysis-followup's `prevent_destroy = true` on the
  investment-research ECR repo so it can never be torn down by an
  accidental Terraform refactor (same risk profile, same fix).
