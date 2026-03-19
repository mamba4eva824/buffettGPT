---
description: "Run all verification gates and report pass/fail status"
---

# Verify — Run All Project Gates

Run all verification gates and report pass/fail status for each.

## Execution Strategy

**Spawn a Verifier agent** (from `.claude/agents/verifier.md`) via Task tool with instructions to run the **full verification suite**:

```bash
# Python Backend
cd chat-api/backend && make test

# Frontend Lint
cd frontend && npm run lint

# Terraform Validation
cd chat-api/terraform/environments/dev && terraform validate

# Lambda Build
cd chat-api/backend && ./scripts/build_lambdas.sh
```

The Verifier agent will run all gates and return a structured Verification Report.

## Failure Handling

If any gate fails:
1. **Spawn a Researcher agent** (from `.claude/agents/researcher.md`) to investigate the failure — pass it the error output and ask it to identify the root cause and affected files
2. Present the Verifier's report and the Researcher's diagnosis
3. Suggest fixes
4. Do NOT mark verification as complete until all gates pass
