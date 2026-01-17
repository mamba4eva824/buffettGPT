# AWS Bedrock Agent Versioning Strategy

## Overview

This document outlines the versioning strategy for AWS Bedrock Agents in the buffett_chat_api project. Understanding this is critical for successfully updating agents without disruption.

## Key Concepts

### DRAFT vs Numbered Versions

**DRAFT Version:**
- The mutable "working copy" of your agent
- All Terraform changes update the DRAFT version
- Cannot be used with aliases once the agent has been versioned
- Identifier: `"DRAFT"`

**Numbered Versions (1, 2, 3...):**
- Immutable snapshots of the agent at a point in time
- Created when you call `prepare-agent` on a modified DRAFT
- Required for alias routing once an agent has been prepared
- Cannot be modified after creation

### Why You Can't Use DRAFT

**AWS Bedrock Limitation:**
Once an agent has been **prepared** (which happens automatically with `prepare_agent = true` in Terraform), AWS requires all aliases to point to numbered versions, not DRAFT.

**What we learned:**
```
AWS Error: "DRAFT must not be associated with this alias"
```

This happens because the agent was previously prepared and versioned.

## Current Configuration (Dev Environment)

### Both Agents Are Configured For Versioning

**Location:** [chat-api/terraform/environments/dev/main.tf](environments/dev/main.tf)

```terraform
# BuffettGPT Agent
module "bedrock" {
  create_agent_version = true
  agent_version_number = "1"  # Current stable version
}

# Debt Analyst Agent
module "bedrock_debt_analyst" {
  create_agent_version = true
  agent_version_number = "1"  # Current stable version
}
```

**Current State:**
- Both agents have version `"1"` deployed
- Both aliases point to version `"1"`
- DRAFT exists but is not routable via aliases

---

## How to Update Agents (Development Workflow)

### Step-by-Step Process

#### 1. **Make Configuration Changes**

Edit the agent configuration in [environments/dev/main.tf](environments/dev/main.tf):

```terraform
module "bedrock" {
  # Change foundation model
  foundation_model_id = "anthropic.claude-3-5-sonnet-20241022-v2:0"

  # Or update instructions
  agent_instruction = var.bedrock_agent_instruction  # Modified in variables

  # Version remains at current
  agent_version_number = "1"  # Don't change yet!
}
```

#### 2. **Apply Terraform**

```bash
cd chat-api/terraform/environments/dev
terraform apply
```

**What happens:**
- ✅ Terraform updates the DRAFT version with new configuration
- ✅ Agent is automatically prepared (because `prepare_agent = true`)
- ✅ A new version is created (version 2, 3, etc.)
- ❌ Alias still points to old version (1)

#### 3. **Verify New Version**

Check that the new version was created:

```bash
# Check versions for BuffettGPT agent
aws bedrock-agent list-agent-versions \
  --agent-id QTFYZ6BBSE \
  --query 'agentVersionSummaries[].{Version:agentVersion,Status:agentStatus}' \
  --output table

# Check versions for Debt Analyst agent
aws bedrock-agent list-agent-versions \
  --agent-id ZCIAI0BCN8 \
  --query 'agentVersionSummaries[].{Version:agentVersion,Status:agentStatus}' \
  --output table
```

Expected output:
```
-------------------------------
|   ListAgentVersions        |
+--------+------------------+
| Status | Version          |
+--------+------------------+
| PREPARED| 2               |  ← New version
| PREPARED| 1               |
| PREPARED| DRAFT           |
+--------+------------------+
```

#### 4. **Test New Version (Optional But Recommended)**

Before routing traffic, test the new version directly:

```bash
# Test BuffettGPT v2
aws bedrock-agent-runtime invoke-agent \
  --agent-id QTFYZ6BBSE \
  --agent-alias-id TSTALIASID \  # Or create test alias
  --session-id test-session-$(date +%s) \
  --input-text "What is Warren Buffett's view on debt?"
```

#### 5. **Promote New Version**

Update the `agent_version_number` to point aliases to the new version:

```terraform
module "bedrock" {
  create_agent_version = true
  agent_version_number = "2"  # ← Increment to new version
}

module "bedrock_debt_analyst" {
  create_agent_version = true
  agent_version_number = "2"  # ← Increment to new version
}
```

Apply:
```bash
terraform apply
```

**What happens:**
- ✅ Aliases update to point to version 2
- ✅ All API traffic now uses the new version
- ✅ Version 1 remains available for rollback

#### 6. **Rollback If Needed**

If issues are discovered, instantly rollback:

```terraform
module "bedrock" {
  agent_version_number = "1"  # ← Rollback to previous version
}
```

```bash
terraform apply  # Takes ~2 seconds
```

---

## Production Workflow (Multi-Environment)

### Recommended Pattern

**Directory Structure:**
```
terraform/environments/
├── dev/          # Development environment
├── staging/      # Staging environment
└── prod/         # Production environment
```

**Version Promotion Flow:**
```
Dev (v2-alpha) → Test → Staging (v2-beta) → Test → Prod (v2)
```

### Example Configuration

**Dev Environment (rapid iteration):**
```terraform
# environments/dev/main.tf
module "bedrock" {
  agent_version_number = "2"  # Latest experimental version
}
```

**Staging Environment (pre-production testing):**
```terraform
# environments/staging/main.tf
module "bedrock" {
  agent_version_number = "2"  # Testing v2 before prod
}
```

**Production Environment (stable):**
```terraform
# environments/prod/main.tf
module "bedrock" {
  agent_version_number = "1"  # Proven stable version
}
```

---

## Advanced Patterns

### Pattern 1: Blue/Green Deployment with Traffic Splitting

```terraform
resource "aws_bedrockagent_agent_alias" "production" {
  agent_alias_name = "production"
  agent_id         = aws_bedrockagent_agent.main.id

  # Route 90% to v1, 10% to v2 for canary testing
  routing_configuration {
    agent_version = "1"
    routing_weight = 90
  }

  routing_configuration {
    agent_version = "2"
    routing_weight = 10
  }
}
```

### Pattern 2: Environment-Specific Aliases

```terraform
# Dev alias - always latest
resource "aws_bedrockagent_agent_alias" "dev" {
  agent_alias_name = "dev"
  routing_configuration {
    agent_version = var.latest_version  # "2"
  }
}

# Prod alias - conservative
resource "aws_bedrockagent_agent_alias" "prod" {
  agent_alias_name = "production"
  routing_configuration {
    agent_version = var.stable_version  # "1"
  }
}
```

---

## Common Issues and Solutions

### Issue 1: "DRAFT must not be associated with this alias"

**Cause:** Trying to point an alias to DRAFT after the agent has been versioned.

**Solution:** Use numbered versions. See "How to Update Agents" above.

### Issue 2: "Agent Version X doesn't exist"

**Cause:** Referencing a version number that hasn't been created yet.

**Solution:**
```bash
# Check existing versions
aws bedrock-agent list-agent-versions --agent-id QTFYZ6BBSE

# Create new version by modifying agent and applying Terraform
# The null_resource provisioner will call prepare-agent
```

### Issue 3: Changes Not Reflected

**Cause:** Alias still pointing to old version.

**Solution:** Increment `agent_version_number` in Terraform config.

### Issue 4: Version Creation Timing

**Cause:** `prepare-agent` is async; version may not exist immediately.

**Solution:** Wait 10-30 seconds after Terraform apply before using new version.

---

## Version History Tracking

### View All Versions

```bash
# List all versions with details
aws bedrock-agent list-agent-versions \
  --agent-id QTFYZ6BBSE \
  --query 'agentVersionSummaries[]' \
  --output json
```

### Version Metadata

Each version snapshot includes:
- Foundation model used
- Agent instructions
- Knowledge base associations
- Action groups
- Guardrails configuration
- Prompt overrides

---

## Best Practices

### ✅ DO

1. **Always test new versions** before promoting to production
2. **Keep version numbers in sync** with your release tags
3. **Document what changed** in each version (use git commit messages)
4. **Maintain at least 2 versions** for rollback capability
5. **Increment versions** when making significant changes (model, instructions, KB)

### ❌ DON'T

1. **Don't skip testing** new versions
2. **Don't delete old versions** immediately (keep for rollback)
3. **Don't modify version numbers** without applying config changes first
4. **Don't point multiple environments** to the same version during testing
5. **Don't forget to increment** `agent_version_number` after creating new versions

---

## Quick Reference Commands

```bash
# Check current agent status
aws bedrock-agent get-agent --agent-id QTFYZ6BBSE

# List all versions
aws bedrock-agent list-agent-versions --agent-id QTFYZ6BBSE

# Get specific version details
aws bedrock-agent get-agent --agent-id QTFYZ6BBSE --agent-version 1

# Check alias routing
aws bedrock-agent get-agent-alias \
  --agent-id QTFYZ6BBSE \
  --agent-alias-id GBR5BNBNYM

# Invoke agent (testing)
aws bedrock-agent-runtime invoke-agent \
  --agent-id QTFYZ6BBSE \
  --agent-alias-id GBR5BNBNYM \
  --session-id test-session \
  --input-text "Test query"
```

---

## Summary

**Key Takeaway:** AWS Bedrock Agents require versioned aliases once they've been prepared. You cannot use DRAFT with aliases. Instead:

1. Make changes in Terraform
2. Apply (creates new version automatically)
3. Test new version
4. Increment `agent_version_number`
5. Apply again (routes traffic to new version)

This workflow enables zero-downtime updates with instant rollback capability.
