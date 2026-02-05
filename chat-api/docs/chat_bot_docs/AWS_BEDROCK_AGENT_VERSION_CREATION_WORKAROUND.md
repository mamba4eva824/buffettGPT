# AWS Bedrock Agent Version Creation Workaround

**Last Updated**: October 31, 2025
**Status**: Active Workaround
**Applies To**: AWS Bedrock Agents (all regions)

---

## Problem Statement

AWS Bedrock Agents do not provide a direct API or CLI command to create agent versions programmatically. While AWS provides commands to:
- `get-agent-version` (view existing versions)
- `list-agent-versions` (list all versions)
- `delete-agent-version` (delete versions)

There is **NO** `create-agent-version` command available via:
- AWS CLI (`aws bedrock-agent`)
- AWS SDK boto3 (`boto3.client('bedrock-agent')`)
- Terraform AWS Provider (`aws_bedrockagent_agent_version` resource does not exist)

This creates a challenge for Infrastructure as Code (IaC) deployments where version management needs to be automated.

---

## Investigation Summary

### What We Tried

1. **Terraform `null_resource` with Python Script**
   - Created `create_version.py` script
   - Attempted to call `bedrock_agent.create_agent_version()`
   - **Result**: Method does not exist in boto3 SDK

2. **AWS CLI Direct Commands**
   - Searched for `aws bedrock-agent create-agent-version`
   - **Result**: Command does not exist

3. **Direct boto3 API Calls**
   - Attempted `client.create_agent_version()`
   - **Result**: `'AgentsforBedrock' object has no attribute 'create_agent_version'`

4. **Upgrading boto3**
   - Upgraded from boto3 1.40.61 to 1.40.63
   - **Result**: Still no `create_agent_version` method

### Discovery: The Alias Creation Trick

After extensive research and experimentation, we discovered that **creating a new agent alias automatically triggers version creation** from the current DRAFT.

---

## The Workaround

### How It Works

When you create a new alias for a Bedrock Agent, AWS automatically:
1. Takes a snapshot of the current DRAFT configuration
2. Creates a new numbered version (e.g., version 2)
3. Points the new alias to this version

This behavior can be exploited to create versions programmatically.

### Step-by-Step Process

#### 1. Prepare the Agent

Ensure your DRAFT has all the changes you want to version:

```bash
aws bedrock-agent prepare-agent \
  --agent-id <YOUR_AGENT_ID> \
  --region us-east-1
```

Wait for the agent to reach `PREPARED` status (usually 10-30 seconds).

#### 2. Create a Temporary Alias

Creating an alias triggers version creation:

```bash
aws bedrock-agent create-agent-alias \
  --agent-id <YOUR_AGENT_ID> \
  --agent-alias-name "version-X-temp" \
  --description "Temporary alias to create version X" \
  --region us-east-1
```

**Important Notes:**
- Use a descriptive temporary name (e.g., `version-2-temp`)
- AWS will auto-create the next sequential version number
- The alias creation happens immediately, but version creation takes a few seconds

#### 3. Verify Version Creation

Wait 10-15 seconds, then check:

```bash
aws bedrock-agent list-agent-versions \
  --agent-id <YOUR_AGENT_ID> \
  --region us-east-1 | jq '.agentVersionSummaries[] | {version: .agentVersion, status: .agentStatus}'
```

You should see the new version (e.g., version 2) with status `PREPARED`.

#### 4. Update Your Primary Alias

Point your production/main alias to the new version:

```bash
aws bedrock-agent update-agent-alias \
  --agent-id <YOUR_AGENT_ID> \
  --agent-alias-id <YOUR_PRIMARY_ALIAS_ID> \
  --agent-alias-name "<YOUR_ALIAS_NAME>" \
  --routing-configuration agentVersion=2 \
  --region us-east-1
```

#### 5. Delete the Temporary Alias

Clean up the temporary alias:

```bash
aws bedrock-agent delete-agent-alias \
  --agent-id <YOUR_AGENT_ID> \
  --agent-alias-id <TEMP_ALIAS_ID> \
  --region us-east-1
```

#### 6. Update Terraform Configuration

Update your Terraform to track the new version:

```terraform
# In your main.tf
module "bedrock" {
  source = "../../modules/bedrock"

  create_agent_version = true
  agent_version_number = "2"  # ← Update this
}
```

Then apply:

```bash
cd chat-api/terraform/environments/dev
terraform apply
```

---

## Example: BuffettGPT Version 2 Creation

Here's the exact sequence used to create Version 2 for the BuffettGPT agent:

```bash
# Agent ID: QTFYZ6BBSE
# Primary Alias ID: GBR5BNBNYM

# 1. Prepare agent (DRAFT already has Claude 4.5 Haiku + memory)
aws bedrock-agent prepare-agent --agent-id QTFYZ6BBSE --region us-east-1

# 2. Create temporary alias (triggers version 2 creation)
aws bedrock-agent create-agent-alias \
  --agent-id QTFYZ6BBSE \
  --agent-alias-name "version-2-temp" \
  --description "Temporary alias to create version 2 - Claude 4.5 Haiku with memory" \
  --region us-east-1

# Output: agentAliasId: 6LOVELOC5F

# 3. Wait 15 seconds
sleep 15

# 4. Verify version 2 was created
aws bedrock-agent list-agent-versions --agent-id QTFYZ6BBSE --region us-east-1

# Output shows version 2 created!

# 5. Update primary alias to point to version 2
aws bedrock-agent update-agent-alias \
  --agent-id QTFYZ6BBSE \
  --agent-alias-id GBR5BNBNYM \
  --agent-alias-name "buffett-advisor-alias" \
  --routing-configuration agentVersion=2 \
  --region us-east-1

# 6. Delete temporary alias
aws bedrock-agent delete-agent-alias \
  --agent-id QTFYZ6BBSE \
  --agent-alias-id 6LOVELOC5F \
  --region us-east-1

# 7. Update Terraform
# Edit: chat-api/terraform/environments/dev/main.tf
#   agent_version_number = "2"

# 8. Apply Terraform
cd chat-api/terraform/environments/dev
terraform apply
```

**Result**: Version 2 successfully created and deployed with:
- Claude 4.5 Haiku (`anthropic.claude-haiku-4-5-20251001-v1:0`)
- Memory enabled (SESSION_SUMMARY, 30-day retention)
- Updated prompt from `buffett_advisor_instruction.txt`

---

## Automation Script

For convenience, you can create a bash script to automate this process:

```bash
#!/bin/bash
# create_bedrock_agent_version.sh

set -e

AGENT_ID="${1:-QTFYZ6BBSE}"
ALIAS_ID="${2:-GBR5BNBNYM}"
ALIAS_NAME="${3:-buffett-advisor-alias}"
VERSION="${4:-auto}"
REGION="us-east-1"

echo "Creating new version for agent $AGENT_ID..."

# 1. Prepare agent
echo "Preparing agent..."
aws bedrock-agent prepare-agent --agent-id "$AGENT_ID" --region "$REGION"

# Wait for prepared status
echo "Waiting for PREPARED status..."
for i in {1..20}; do
    STATUS=$(aws bedrock-agent get-agent --agent-id "$AGENT_ID" --region "$REGION" | jq -r '.agent.agentStatus')
    echo "  Status: $STATUS"
    if [ "$STATUS" == "PREPARED" ]; then
        break
    fi
    sleep 3
done

# 2. Create temporary alias
TEMP_ALIAS_NAME="version-temp-$(date +%s)"
echo "Creating temporary alias: $TEMP_ALIAS_NAME..."
TEMP_ALIAS_ID=$(aws bedrock-agent create-agent-alias \
    --agent-id "$AGENT_ID" \
    --agent-alias-name "$TEMP_ALIAS_NAME" \
    --description "Temporary alias for version creation" \
    --region "$REGION" | jq -r '.agentAlias.agentAliasId')

echo "Temporary alias created: $TEMP_ALIAS_ID"

# 3. Wait for version creation
echo "Waiting for version creation..."
sleep 15

# 4. Get the new version number
NEW_VERSION=$(aws bedrock-agent list-agent-versions --agent-id "$AGENT_ID" --region "$REGION" | \
    jq -r '[.agentVersionSummaries[] | select(.agentVersion != "DRAFT")] | sort_by(.createdAt) | .[-1].agentVersion')

echo "New version created: $NEW_VERSION"

# 5. Update primary alias
echo "Updating primary alias to point to version $NEW_VERSION..."
aws bedrock-agent update-agent-alias \
    --agent-id "$AGENT_ID" \
    --agent-alias-id "$ALIAS_ID" \
    --agent-alias-name "$ALIAS_NAME" \
    --routing-configuration agentVersion="$NEW_VERSION" \
    --region "$REGION"

# 6. Delete temporary alias
echo "Deleting temporary alias..."
aws bedrock-agent delete-agent-alias \
    --agent-id "$AGENT_ID" \
    --agent-alias-id "$TEMP_ALIAS_ID" \
    --region "$REGION"

echo "✓ Success! Version $NEW_VERSION is now active."
echo ""
echo "Next steps:"
echo "1. Update Terraform configuration:"
echo "   agent_version_number = \"$NEW_VERSION\""
echo "2. Run: cd chat-api/terraform/environments/dev && terraform apply"
```

Usage:
```bash
chmod +x create_bedrock_agent_version.sh
./create_bedrock_agent_version.sh QTFYZ6BBSE GBR5BNBNYM buffett-advisor-alias
```

---

## Limitations and Considerations

### Limitations

1. **No Direct Version Control**: You cannot specify which version number to create (AWS auto-increments)
2. **Cannot Create Multiple Versions Simultaneously**: Each alias creation creates one version
3. **Temporary Alias Required**: Must create and delete a temporary alias each time
4. **No Version Rollback API**: To rollback, you must update alias routing, not delete versions
5. **Version Deletion Restrictions**: Cannot delete versions that aliases point to

### Best Practices

1. **Always Prepare First**: Ensure agent is in PREPARED state before creating versions
2. **Descriptive Version Comments**: Include version description in alias description
3. **Sequential Versioning**: Let AWS handle version numbering automatically
4. **Test in DRAFT First**: Always test changes in DRAFT before creating versions
5. **Document Version Changes**: Maintain a CHANGELOG for version updates
6. **Terraform Sync**: Always update Terraform after manual version creation

### Cost Considerations

- **Alias Creation**: No additional cost
- **Version Storage**: Versions are stored indefinitely (no per-version cost)
- **Inference**: Billed per inference request regardless of version

---

## Alternative Approaches Considered

### 1. AWS Console Manual Creation

**Status**: Not Available
The AWS Bedrock Console does not provide a "Create Version" button. Versions can only be created via alias operations.

### 2. Terraform Custom Provider

**Status**: Not Feasible
Would require maintaining a custom Terraform provider that wraps the alias creation logic.

### 3. CloudFormation Custom Resource

**Status**: Possible but Complex
Could create a Lambda-backed custom resource, but adds complexity.

### 4. Wait for AWS API Update

**Status**: Monitoring
AWS may add `create-agent-version` API in future. Monitor:
- [AWS Bedrock Roadmap](https://github.com/aws/aws-sdk/issues)
- boto3 release notes
- AWS CLI changelog

---

## Troubleshooting

### Problem: Version Not Created After Alias Creation

**Symptoms**: No new version appears after creating temporary alias

**Solutions**:
1. Ensure agent was in PREPARED state
2. Wait longer (up to 60 seconds)
3. Check for errors in alias creation response
4. Verify agent has changes in DRAFT vs previous version

### Problem: Alias Update Fails with Version Not Found

**Symptoms**: Error when updating alias to point to new version

**Solutions**:
1. Verify version exists: `aws bedrock-agent list-agent-versions`
2. Wait for version status to be PREPARED
3. Check version number is a string (e.g., `"2"` not `2`)

### Problem: Terraform Drift After Manual Version Creation

**Symptoms**: Terraform shows changes after creating version manually

**Solution**:
Always update Terraform configuration to match AWS state:
```terraform
agent_version_number = "X"  # Match the version you created
```
Then run `terraform apply` to sync state.

---

## Related Resources

- **Terraform Bedrock Versioning Strategy**: `chat-api/terraform/BEDROCK_VERSIONING_STRATEGY.md`
- **Agent Configuration**: `chat-api/terraform/environments/dev/main.tf`
- **Prompt Files**: `chat-api/terraform/modules/bedrock/prompts/`
- **Version Update Script**: `chat-api/backend/scripts/update_buffettgpt_version.py`

---

## Change Log

### October 31, 2025
- **Discovery**: Documented alias creation workaround
- **Tested**: Successfully created BuffettGPT Version 2 using this method
- **Automation**: Created bash script for future version creation
- **Status**: Active workaround, production-ready

---

## Future Considerations

**If AWS adds native version creation API:**
1. Update automation scripts to use native API
2. Deprecate alias creation workaround
3. Update Terraform modules to use native resource
4. Migrate existing version management workflows

**Monitor for updates:**
- AWS Bedrock service announcements
- boto3 SDK release notes (check for `create_agent_version` method)
- Terraform AWS provider updates (check for `aws_bedrockagent_agent_version` resource)

---

## Contact

For questions or issues with this workaround:
- Review git history for implementation details
- Check AWS support documentation
- Test in development environment before production use

**Last Verified**: October 31, 2025 with:
- boto3 version: 1.40.63
- AWS CLI version: Latest
- Terraform AWS Provider: 5.x
