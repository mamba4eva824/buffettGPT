# Terraform - Infrastructure & Prompt Management

## 🏗️ Agent Architecture Overview

### Prompt Locations

| Agent | Prompt Source | Notes |
|-------|---------------|-------|
| **Debt Expert** | `modules/bedrock/prompts/value_investor_debt_v5.txt` | Deployed via Terraform |
| **Cashflow Expert** | `modules/bedrock/prompts/value_investor_cashflow_v5.txt` | Deployed via Terraform |
| **Growth Expert** | `modules/bedrock/prompts/value_investor_growth_v5.txt` | Deployed via Terraform |
| **Supervisor** | `backend/.../orchestrator.py:520-640` | Hardcoded in Python (uses converse_stream) |

### Why Different Locations?

- **Expert agents** use `invoke_agent()` API which loads system prompts from Bedrock agent configuration (Terraform-managed)
- **Supervisor** uses `converse_stream()` API for true token streaming, which requires inline system prompt (Python code)

### Action Groups (REMOVED)

Bedrock Agents action groups were used by the deprecated expert agent (Debt/Cashflow/Growth) and follow-up agent architectures. Both have been removed:

- Expert agent action group (`value_investor_action.yaml`, `prediction_ensemble`) — archived 2025-01.
- Follow-up agent action group (`followup_action.yaml`, `followup-action` Docker Lambda) — removed 2026-05.

Live agents (`analysis_followup`, `market_intel_chat`) now use **Bedrock Runtime `converse_stream` with inline `tools`**. Tool schemas live in the Python handlers under `chat-api/backend/src/handlers/`. No Bedrock Agent or action group is needed.

---

## 🔧 Expert Agent Prompt Workflow

```bash
# 1. Edit prompt
vim modules/bedrock/prompts/<agent>_expert_instruction.txt

# 2. Validate & plan
cd environments/dev
terraform validate
terraform plan

# 3. Apply
terraform apply

# 4. Test with baseline ticker
curl -X POST <api>/analysis/supervisor -d '{"ticker":"AAPL"}'
```

## Prompt File Locations
- `modules/bedrock/prompts/debt_expert_instruction.txt`
- `modules/bedrock/prompts/cashflow_expert_instruction.txt`
- `modules/bedrock/prompts/growth_expert_instruction.txt`
- `modules/bedrock/prompts/supervisor_instruction_v5.txt` (reference only)

## Version History
Versioned prompts (v2-v5) are kept for rollback reference.
Active prompts are the non-versioned `*_expert_instruction.txt` files.
