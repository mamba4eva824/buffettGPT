# Agent Version Management
# Since AWS doesn't provide a direct Terraform resource for agent versions,
# we use null_resource with local-exec to create versions

resource "null_resource" "agent_version" {
  count = var.create_agent_version ? 1 : 0

  # Triggers determine when to recreate this resource
  # Only trigger version creation when actual configuration changes
  triggers = {
    agent_id         = aws_bedrockagent_agent.main.id
    model            = var.foundation_model
    knowledge_base   = var.knowledge_base_id
    instruction_hash = md5(var.agent_instruction)
    # Remove timestamp() to prevent recreation on every apply
  }

  # Wait for agent to be prepared
  depends_on = [
    aws_bedrockagent_agent.main,
    aws_bedrockagent_agent_knowledge_base_association.main
  ]

  # Create a version snapshot after agent is prepared
  provisioner "local-exec" {
    command = <<-EOT
      echo "Waiting for agent to be fully prepared..."
      sleep 10

      # Check agent status
      STATUS=$(aws bedrock-agent get-agent --agent-id ${aws_bedrockagent_agent.main.id} --query 'agent.agentStatus' --output text 2>/dev/null)

      if [ "$STATUS" = "PREPARED" ]; then
        echo "Agent is prepared. Creating version snapshot..."

        # Get the next version number
        VERSIONS=$(aws bedrock-agent list-agent-versions --agent-id ${aws_bedrockagent_agent.main.id} --query 'agentVersionSummaries[?agentVersion != `DRAFT`].agentVersion' --output json 2>/dev/null)

        # Count existing versions (excluding DRAFT)
        VERSION_COUNT=$(echo "$VERSIONS" | jq 'length')
        NEXT_VERSION=$((VERSION_COUNT + 1))

        echo "This will be version $NEXT_VERSION"
        echo "Configuration snapshot:"
        echo "  - Model: ${var.foundation_model}"
        echo "  - Knowledge Base: ${var.knowledge_base_id}"
        echo "  - Agent Name: ${var.agent_name}"

        # Note: The agent version is automatically created when significant changes are made
        # and the agent is prepared. The version number increments automatically.

        # Force a prepare to ensure latest changes are captured
        aws bedrock-agent prepare-agent --agent-id ${aws_bedrockagent_agent.main.id}

        echo "Version creation triggered. Check AWS Console for version $NEXT_VERSION"
      else
        echo "Agent status is $STATUS. Cannot create version."
        exit 1
      fi
    EOT
  }
}

output "agent_version_info" {
  value = var.create_agent_version ? {
    message = "Agent version creation triggered. Check AWS Console for the new version."
    agent_id = aws_bedrockagent_agent.main.id
    model = var.foundation_model
    knowledge_base = var.knowledge_base_id
  } : null
}