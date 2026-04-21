# GSD Plan: Fix Staging Terraform Drift

## Audit Snapshot

### Knowns / Evidence
- **Dev environment works** — it's the reference for correct module interfaces
- **Staging main.tf** has drifted from module interfaces after refactoring
- **Key mismatches identified**:
  1. `module.bedrock.agent_alias_id` doesn't exist — should be `followup_agent_alias_id` (line 54, hidden by `try()`)
  2. Staging missing: API gateway feature flags, followup action Lambda config, bedrock action group, stripe module, email module, function-specific env vars
  3. `deploy-staging.yml` extracts `investment_research_function_url` via `terraform output -raw` which will fail if value is null (Docker Lambda not created)

### Constraints
- Must pass `terraform validate`
- Cannot test `terraform plan` without AWS credentials/secrets
- Enabling stripe/email modules requires corresponding AWS Secrets Manager secrets in staging

### Risks
1. Enabling Docker Lambda requires ECR image to exist in staging — use conditional creation
2. Stripe/email secrets may not exist yet in staging — but modules just reference them, `terraform validate` won't check
3. Foundation model ID in staging uses older Claude 3.0 Haiku — separate concern, not blocking

---

## Acceptance Criteria

```
AC-1: `cd chat-api/terraform/environments/staging && terraform validate` passes with no errors.
AC-2: All module output references in staging/outputs.tf resolve to actual module outputs.
AC-3: FOLLOWUP_AGENT_ALIAS env var correctly references `followup_agent_alias_id`.
AC-4: deploy-staging.yml `terraform output -raw` commands only reference outputs that produce non-null values.
AC-5: Staging main.tf passes all variables that dev passes to shared modules.
```

---

## Implementation Plan

### Objective
Sync staging Terraform config with actual module interfaces so `terraform validate` passes and CI/CD pipeline succeeds.

### Approach
Use dev/main.tf as the source of truth. Fix staging to match dev's module invocations (with staging-appropriate values). Add missing modules (stripe, email). Fix outputs and workflow.

### Steps

1. **Fix staging/main.tf — Bedrock alias reference** (line 54)
   - `module.bedrock.agent_alias_id` → `module.bedrock.followup_agent_alias_id`

2. **Fix staging/main.tf — Lambda module: add followup action config**
   - Add `create_followup_action_lambda`, `followup_action_image_tag`
   - Add DynamoDB table ARN/name vars (6 vars from dev)

3. **Fix staging/main.tf — API Gateway: add feature flags**
   - Add `enable_analysis_api = true`, `enable_research_api = true`
   - Add `enable_subscription_routes = true`, `enable_stripe_webhook = true`
   - Add `auth_verify_invoke_arn`, `auth_verify_function_name`
   - Add `investment_research_function_url`, `investment_research_function_name`, `analysis_followup_function_url`

4. **Fix staging/main.tf — Bedrock: add action group config**
   - Add `enable_followup_action_group = true`
   - Add `followup_action_lambda_arn`, `followup_action_lambda_function_name`

5. **Add Stripe module to staging/main.tf**
   - Copy stripe module block from dev (with staging secret names)
   - Add IAM role policy attachment

6. **Add Email module to staging/main.tf**
   - Copy email module block from dev (with staging secret name)
   - Add IAM role policy attachment

7. **Fix staging/main.tf — Add function-specific env vars**
   - Add stripe_webhook_handler, subscription_handler, waitlist_handler env vars (matching dev)

8. **Fix staging/outputs.tf — Add analysis_api_endpoint and research_api_endpoint**
   - Match dev outputs where applicable

9. **Fix deploy-staging.yml — Handle output extraction safely**
   - Use `|| true` or `|| echo ""` fallback for potentially null outputs

10. **Validate locally**
    ```bash
    cd chat-api/terraform/environments/staging && terraform init -backend-config=backend.hcl && terraform validate
    ```

### Files to Modify
- `chat-api/terraform/environments/staging/main.tf`
- `chat-api/terraform/environments/staging/outputs.tf`
- `.github/workflows/deploy-staging.yml`

### Verification
```bash
cd chat-api/terraform/environments/staging && terraform init -backend-config=backend.hcl && terraform validate
```
