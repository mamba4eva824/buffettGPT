#!/usr/bin/env python3
"""
Create new version of Debt Analyst Agent and update alias
This ensures the alias uses the latest DRAFT configuration (Haiku 3.5)
"""

import boto3
import time
import sys

# Debt Analyst Agent Configuration
AGENT_ID = "ZCIAI0BCN8"
ALIAS_ID = "5J9ZUM3YPS"
REGION = "us-east-1"

bedrock_agent = boto3.client('bedrock-agent', region_name=REGION)

def prepare_agent():
    """Prepare the agent for version creation"""
    print(f"Preparing agent {AGENT_ID}...")
    try:
        response = bedrock_agent.prepare_agent(agentId=AGENT_ID)
        print(f"✓ Agent preparation initiated: {response['agentStatus']}")
        return True
    except Exception as e:
        print(f"✗ Error preparing agent: {e}")
        return False

def wait_for_prepared_status(max_wait=120):
    """Wait for agent to reach PREPARED status"""
    print("Waiting for agent to be PREPARED...")
    start_time = time.time()

    while time.time() - start_time < max_wait:
        try:
            response = bedrock_agent.get_agent(agentId=AGENT_ID)
            status = response['agent']['agentStatus']
            print(f"  Current status: {status}")

            if status == 'PREPARED':
                print("✓ Agent is PREPARED")
                return True
            elif status == 'FAILED':
                print("✗ Agent preparation FAILED")
                return False

            time.sleep(5)
        except Exception as e:
            print(f"✗ Error checking agent status: {e}")
            return False

    print("✗ Timeout waiting for agent to be PREPARED")
    return False

def create_agent_version():
    """Create a new version from the current DRAFT"""
    print(f"\nCreating new agent version from DRAFT...")
    try:
        response = bedrock_agent.create_agent_version(
            agentId=AGENT_ID,
            description="Updated to Claude Haiku 3.5 (anthropic.claude-3-5-haiku-20241022-v1:0)"
        )
        version = response['agentVersion']['version']
        print(f"✓ Created agent version: {version}")
        return version
    except Exception as e:
        print(f"✗ Error creating agent version: {e}")
        return None

def update_alias(version):
    """Update the alias to point to the new version"""
    print(f"\nUpdating alias {ALIAS_ID} to point to version {version}...")
    try:
        response = bedrock_agent.update_agent_alias(
            agentId=AGENT_ID,
            agentAliasId=ALIAS_ID,
            agentAliasName="prod",
            routingConfiguration=[
                {
                    'agentVersion': version
                }
            ]
        )
        print(f"✓ Alias updated successfully")
        print(f"  Alias: {response['agentAlias']['agentAliasName']}")
        print(f"  Status: {response['agentAlias']['agentAliasStatus']}")
        return True
    except Exception as e:
        print(f"✗ Error updating alias: {e}")
        return False

def verify_configuration():
    """Verify the current agent and alias configuration"""
    print("\n" + "="*60)
    print("VERIFICATION")
    print("="*60)

    try:
        # Get agent info
        agent_response = bedrock_agent.get_agent(agentId=AGENT_ID)
        agent = agent_response['agent']
        print(f"\nAgent (DRAFT):")
        print(f"  Model: {agent.get('foundationModel', 'N/A')}")
        print(f"  Status: {agent.get('agentStatus', 'N/A')}")

        # Get alias info
        alias_response = bedrock_agent.get_agent_alias(
            agentId=AGENT_ID,
            agentAliasId=ALIAS_ID
        )
        alias = alias_response['agentAlias']
        routing = alias.get('routingConfiguration', [])

        print(f"\nAlias Configuration:")
        print(f"  Alias Name: {alias.get('agentAliasName', 'N/A')}")
        print(f"  Status: {alias.get('agentAliasStatus', 'N/A')}")
        if routing:
            print(f"  Points to Version: {routing[0].get('agentVersion', 'N/A')}")

        # Get the version the alias points to
        if routing:
            version = routing[0].get('agentVersion')
            if version and version != 'DRAFT':
                version_response = bedrock_agent.get_agent_version(
                    agentId=AGENT_ID,
                    agentVersion=version
                )
                version_model = version_response['agentVersion'].get('foundationModel', 'N/A')
                print(f"\nVersion {version} Model: {version_model}")

        return True
    except Exception as e:
        print(f"✗ Error verifying configuration: {e}")
        return False

def main():
    print("="*60)
    print("DEBT ANALYST AGENT VERSION UPDATE")
    print("="*60)
    print(f"Agent ID: {AGENT_ID}")
    print(f"Alias ID: {ALIAS_ID}")
    print(f"Region: {REGION}")
    print()

    # Step 1: Prepare agent
    if not prepare_agent():
        sys.exit(1)

    # Step 2: Wait for PREPARED status
    if not wait_for_prepared_status():
        sys.exit(1)

    # Step 3: Create new version
    version = create_agent_version()
    if not version:
        sys.exit(1)

    # Step 4: Update alias
    if not update_alias(version):
        sys.exit(1)

    # Step 5: Verify configuration
    print("\nWaiting 10 seconds for changes to propagate...")
    time.sleep(10)
    verify_configuration()

    print("\n" + "="*60)
    print("✓ SUCCESS: Agent version created and alias updated")
    print("="*60)

if __name__ == "__main__":
    main()
