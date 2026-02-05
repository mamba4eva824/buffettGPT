# Bedrock Agent Version Control Architecture

## Executive Overview

This document explains how AWS Bedrock agent versioning works in our ensemble analysis system, using the v3 → v4 transition as a concrete example.

---

## Architecture: How Components Connect

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TERRAFORM CONFIGURATION                            │
│                    (chat-api/terraform/modules/bedrock/)                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐        │
│  │   main.tf       │    │  variables.tf   │    │  outputs.tf     │        │
│  │                 │    │                 │    │                 │        │
│  │ - Agent modules │    │ - Input vars    │    │ - Agent IDs     │        │
│  │ - Action groups │    │ - Model IDs     │    │ - Alias IDs     │        │
│  │ - Dependencies  │    │ - Feature flags │    │ - ARNs          │        │
│  └────────┬────────┘    └─────────────────┘    └─────────────────┘        │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐      │
│  │                      PROMPT FILES (versioned)                    │      │
│  │                 prompts/value_investor_*_v5.txt                  │      │
│  │                                                                  │      │
│  │  debt_v5.txt ──────► debt_expert_agent.agent_instruction        │      │
│  │  cashflow_v5.txt ──► cashflow_expert_agent.agent_instruction    │      │
│  │  growth_v5.txt ────► growth_expert_agent.agent_instruction      │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐      │
│  │                     ACTION GROUP SCHEMA                          │      │
│  │              schemas/value_investor_action.yaml                  │      │
│  │                                                                  │      │
│  │  Defines: /analyze endpoint, parameters, response structure      │      │
│  │  Points to: Lambda ARN (ensemble_analyzer)                       │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            AWS BEDROCK (Runtime)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────┐      │
│  │                    AGENT (Mutable DRAFT)                        │      │
│  │                                                                  │      │
│  │  debt-expert (LUOMTWUFPI)                                       │      │
│  │  ├── instruction: value_investor_debt_v5.txt content            │      │
│  │  ├── foundation_model: us.anthropic.claude-haiku-4-5 (profile)  │      │
│  │  └── action_group: FinancialAnalysis → Lambda                   │      │
│  │                                                                  │      │
│  │  cashflow-expert (Z572DVMJ7R)                                   │      │
│  │  growth-expert (HVPBFURQCG)                                     │      │
│  │  supervisor (UE2GD0ADEU)                                        │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│           │                                                                 │
│           │  alias creation auto-creates immutable snapshot                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐      │
│  │                 AGENT VERSION (Immutable Snapshot)               │      │
│  │                                                                  │      │
│  │  Version 3 ─► Claude 4.5 Haiku, v5 prompts ◄── CURRENT (all)    │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│           │                                                                 │
│           │  alias points to specific version                               │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐      │
│  │                    AGENT ALIAS (Routing Layer)                   │      │
│  │                                                                  │      │
│  │  "live" alias ──────────────────────────► Version 3 (all agents)│      │
│  │                                                                  │      │
│  │  Your Lambda calls: agent_alias_id (e.g., UPAVXUTEZZ)           │      │
│  │  NOT the agent_id directly                                       │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LAMBDA (Action Group Handler)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────┐      │
│  │              prediction_ensemble (Docker Lambda)                 │      │
│  │                                                                  │      │
│  │  ECR Image: buffett/prediction-ensemble:v1.8.x                  │      │
│  │                                                                  │      │
│  │  Modular Structure:                                              │      │
│  │  ├── handler.py ─► Lambda router                                │      │
│  │  ├── handlers/action_group.py ─► Bedrock action groups          │      │
│  │  ├── services/inference.py ─► XGBoost ML predictions            │      │
│  │  ├── services/orchestrator.py ─► Multi-agent orchestration      │      │
│  │  └── models/metrics.py ─► VALUE_INVESTOR_METRICS                │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The Version Lifecycle

### 1. DRAFT State (Mutable)
- When you modify agent configuration in Terraform, changes apply to DRAFT
- DRAFT is always the "working copy" of your agent
- Testing alias `AgentTestAlias` points to DRAFT for testing

### 2. Version Creation (Immutable Snapshot)
- `terraform apply` with `create_agent_version = true` creates a numbered version
- Versions are **immutable** - once created, they cannot be modified
- Each version captures: instruction, model, action groups, guardrails

### 3. Alias Routing
- Aliases are **pointers** to specific versions
- Production traffic uses `live` alias
- Updating an alias is instant (no downtime)

---

## What Happened: Version 3 → Version 4

### Before (Version 3)
```
prompts/value_investor_debt_instruction.txt (60 lines)
├── Prescriptive format with exact output structure
├── Detailed metric-by-metric instructions
└── Tables and formatting requirements
```

**Result**: Agent produced "checklist-style" responses listing metrics in tables.

### After (Version 4)
```
prompts/value_investor_debt_v2.txt (15 lines)
├── Narrative-focused storytelling prompt
├── Questions about company phases/trajectory
└── Buffett-style verdict requirement
```

**Result**: Agent should produce story-driven analysis explaining what metrics mean.

### The Deployment Steps

```bash
# 1. Create new prompt files
prompts/value_investor_debt_v2.txt
prompts/value_investor_cashflow_v2.txt
prompts/value_investor_growth_v2.txt

# 2. Update main.tf to reference v2 prompts
agent_instruction = file("${path.module}/prompts/value_investor_debt_v2.txt")

# 3. Apply Terraform (updates DRAFT, creates Version 4)
terraform apply

# 4. Aliases still point to Version 3! Must update them.
terraform taint 'module.bedrock.module.debt_expert_agent.aws_bedrockagent_agent_alias.main'
terraform taint 'module.bedrock.module.cashflow_expert_agent.aws_bedrockagent_agent_alias.main'
terraform taint 'module.bedrock.module.growth_expert_agent.aws_bedrockagent_agent_alias.main'

# 5. Apply again to recreate aliases pointing to Version 4
terraform apply
```

---

## Key Files and Their Roles

| File | Purpose | When to Modify |
|------|---------|----------------|
| `main.tf` | Agent module definitions, prompt file references | Adding agents, changing models, updating prompt references |
| `prompts/*.txt` | Agent instructions (the "system prompt") | Changing agent behavior/personality |
| `schemas/*.yaml` | OpenAPI schema for action group | Changing what data Lambda returns to agent |
| `handler.py` | Lambda code that processes action group calls | Changing ML inference, metrics, response format |
| `variables.tf` | Input variables and defaults | Adding new configurable options |

---

## Common Operations Cheat Sheet

### Check Current Alias Versions
```bash
for agent in "debt-expert" "cashflow-expert" "growth-expert"; do
  agent_id=$(aws bedrock-agent list-agents \
    --query "agentSummaries[?contains(agentName, '${agent}')].agentId" \
    --output text)
  echo "=== ${agent} ==="
  aws bedrock-agent list-agent-aliases --agent-id "$agent_id" \
    --query "agentAliasSummaries[*].{alias:agentAliasName, version:routingConfiguration[0].agentVersion}" \
    --output table
done
```

### Update Agent Configuration (Full Workflow)

**Important**: The `terraform taint` approach does NOT work for aliases. AWS rejects creating a new alias with the same name as one being destroyed. Use the delete-and-recreate workflow below.

```bash
# 1. Make changes in Terraform (prompts, foundation_model, etc.)
vim chat-api/terraform/modules/bedrock/main.tf
vim chat-api/terraform/modules/bedrock/prompts/value_investor_debt_v3.txt

# 2. Apply to update DRAFT (does NOT create versions yet)
cd chat-api/terraform/environments/dev
terraform apply

# 3. Delete existing aliases in AWS (get IDs first)
aws bedrock-agent list-agent-aliases --agent-id <AGENT_ID> --output table
aws bedrock-agent delete-agent-alias --agent-id <AGENT_ID> --agent-alias-id <ALIAS_ID>

# 4. Remove aliases from Terraform state
terraform state rm 'module.bedrock.module.debt_expert_agent.aws_bedrockagent_agent_alias.main'
terraform state rm 'module.bedrock.module.cashflow_expert_agent.aws_bedrockagent_agent_alias.main'
terraform state rm 'module.bedrock.module.growth_expert_agent.aws_bedrockagent_agent_alias.main'
terraform state rm 'module.bedrock.module.supervisor_agent.aws_bedrockagent_agent_alias.main'

# 5. Apply again - creates new aliases which AUTO-CREATE new versions from DRAFT
terraform apply

# 6. Verify new versions have correct configuration
aws bedrock-agent get-agent-alias --agent-id <AGENT_ID> --agent-alias-id <NEW_ALIAS_ID> \
  --query 'agentAlias.routingConfiguration[0].agentVersion'
aws bedrock-agent get-agent-version --agent-id <AGENT_ID> --agent-version <VERSION> \
  --query 'agentVersion.foundationModel'
```

**Why this works**: When Terraform creates an alias WITHOUT explicit `routing_configuration`, AWS automatically creates a new numbered version from DRAFT and points the alias to it.

### Update Lambda Handler (Docker)
```bash
# 1. Edit handler code
vim chat-api/backend/lambda/prediction_ensemble/handler.py

# 2. Build Docker image locally and test
docker build -t prediction-ensemble:v1.x.x .
docker run --rm -e AWS_DEFAULT_REGION=us-east-1 -e ENVIRONMENT=dev \
  prediction-ensemble:v1.x.x python -c "import handler; import app; print('OK')"

# 3. Push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 430118826061.dkr.ecr.us-east-1.amazonaws.com
docker tag prediction-ensemble:v1.x.x 430118826061.dkr.ecr.us-east-1.amazonaws.com/buffett/prediction-ensemble:v1.x.x
docker push 430118826061.dkr.ecr.us-east-1.amazonaws.com/buffett/prediction-ensemble:v1.x.x

# 4. Update Lambda to use new image (via Terraform or CLI)
aws lambda update-function-code \
  --function-name buffett-dev-prediction-ensemble \
  --image-uri 430118826061.dkr.ecr.us-east-1.amazonaws.com/buffett/prediction-ensemble:v1.x.x
```

### Rollback to Previous Version
```bash
# Update alias to point to previous version
aws bedrock-agent update-agent-alias \
  --agent-id <AGENT_ID> \
  --agent-alias-id <ALIAS_ID> \
  --routing-configuration agentVersion=3
```

---

## Version History

### Expert Agents (debt, cashflow, growth)

| Version | Date | Changes |
|---------|------|---------|
| 1 | 2024-12-01 | Initial deployment |
| 2 | 2024-12-01 | First iteration |
| 3 | 2024-12-04 | v1 prompts, value investor format, action groups |
| 4 | 2024-12-05 | v2 narrative prompts (15-line storytelling) |
| 5-8 | 2024-12-06 | Iterative prompt refinements, action group updates |
| 9 | 2024-12-09 | Foundation model change: Claude 4.5 Haiku → Claude 3.5 Haiku |

**Note**: Expert agents were recreated with new IDs on 2024-12-09 when switching to inference profiles. New version history starts at v1:

| Version | Date | Changes |
|---------|------|---------|
| 1 | 2024-12-09 | New agents with inference profile `us.anthropic.claude-3-5-haiku-20241022-v1:0` |
| 2 | 2024-12-20 | Upgraded to Claude 4.5 Haiku `us.anthropic.claude-haiku-4-5-20251001-v1:0` (model sunset) |
| 3 | 2024-12-21 | **v5 prompts**: Millennial/Gen Z voice, metric reference tables, temporal metrics (velocity/acceleration), 24 metrics per agent |

### Supervisor Agent

| Version | Date | Changes |
|---------|------|---------|
| 1 | 2024-12-08 | Initial deployment with Claude 4.5 Sonnet, KB integration |
| 2 | 2024-12-09 | Foundation model: Claude 4.5 Haiku, KB temporarily disabled |
| 3 | 2024-12-21 | **v5 prompt**: Expert synthesis framework, market cycle education, business-type weighting |

---

## Current Agent Configuration (as of 2024-12-21)

| Agent | Agent ID | Alias ID | Version | Foundation Model | Prompt |
|-------|----------|----------|---------|------------------|--------|
| Debt Expert | LUOMTWUFPI | UPAVXUTEZZ | 3 | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | v5 |
| Cashflow Expert | Z572DVMJ7R | XVLNTHTPFV | 3 | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | v5 |
| Growth Expert | HVPBFURQCG | GEJ0QWEPPQ | 3 | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | v5 |
| Supervisor | UE2GD0ADEU | TBLZIWGLFN | 3 | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | v5 |

**Note**: All agents use Claude Haiku 4.5 inference profile with v5 prompts (millennial/Gen Z voice, 24 metrics per agent).

---

## Troubleshooting

### "ConflictException" when applying Terraform after taint
**Problem**: `terraform taint` on alias → `terraform apply` fails with "alias name already exists"

**Why**: AWS alias lifecycle doesn't support in-place recreation. Terraform tries to create the new alias before the old one is fully deleted.

**Solution**: Use the delete-and-recreate workflow:
1. Delete alias in AWS: `aws bedrock-agent delete-agent-alias ...`
2. Remove from state: `terraform state rm ...`
3. Apply: `terraform apply`

### "ValidationException" when pointing alias to DRAFT
**Problem**: Trying to update alias `routing_configuration` to use DRAFT version

**Why**: Named aliases (like "live") cannot point to DRAFT. Only test aliases can use DRAFT.

**Solution**: Create a new version from DRAFT, then point alias to that version. The delete-and-recreate workflow handles this automatically.

### Changes not reflected after `terraform apply`
**Problem**: Updated `main.tf` (foundation_model, prompts), applied, but agent still uses old config

**Why**: `terraform apply` only updates DRAFT. Existing aliases still point to old immutable versions.

**Solution**: Follow the full "Update Agent Configuration" workflow above to create new versions and update aliases.

---

## Architecture Decisions

### Why Aliases Instead of Direct Version References?
- **Zero-downtime deployments**: Update alias, traffic switches instantly
- **Easy rollback**: Point alias back to previous version
- **A/B testing**: Create multiple aliases pointing to different versions

### Why Docker Lambda for ML?
- **Large dependencies**: XGBoost, NumPy, pandas exceed 250MB limit
- **Consistent environment**: Same container locally and in production
- **ECR versioning**: Tag images (v1.0.0, v1.1.0) for rollback capability

### Why Separate Prompts from Code?
- **Rapid iteration**: Change agent behavior without Lambda redeploy
- **Version control**: Git history shows prompt evolution
- **A/B testing**: Easy to swap between prompt versions
