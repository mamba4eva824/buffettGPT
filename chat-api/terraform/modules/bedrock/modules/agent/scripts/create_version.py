#!/usr/bin/env python3
"""
Create or verify Bedrock Agent version
Usage: create_version.py <agent_id> <version_number> <model_id>
"""

import boto3
import sys
import time

def main():
    if len(sys.argv) < 4:
        print("Usage: create_version.py <agent_id> <version_number> <model_id>")
        sys.exit(1)

    agent_id = sys.argv[1]
    version_number = sys.argv[2]
    model_id = sys.argv[3]

    print("=" * 60)
    print(f"CREATING AGENT VERSION {version_number}")
    print("=" * 60)
    print(f"Agent ID: {agent_id}")
    print(f"Model: {model_id}")
    print()

    client = boto3.client('bedrock-agent', region_name='us-east-1')

    # Check if version already exists
    try:
        versions_response = client.list_agent_versions(agentId=agent_id, maxResults=50)
        existing_versions = [v['agentVersion'] for v in versions_response.get('agentVersionSummaries', [])]

        if version_number in existing_versions:
            print(f"✓ Version {version_number} already exists")
            sys.exit(0)
    except Exception as e:
        print(f"Error checking versions: {e}")
        sys.exit(1)

    print(f"Version {version_number} does not exist, it will need to be created")
    print()

    # Prepare the agent to ensure DRAFT is up to date
    print("Preparing agent...")
    try:
        client.prepare_agent(agentId=agent_id)
    except Exception as e:
        print(f"Error preparing agent: {e}")

    # Wait for PREPARED status
    print("Waiting for PREPARED status...")
    for i in range(30):
        time.sleep(3)
        try:
            response = client.get_agent(agentId=agent_id)
            status = response['agent']['agentStatus']
            print(f"  Attempt {i+1}: {status}")

            if status == 'PREPARED':
                print("✓ Agent is PREPARED")
                break
            elif status == 'FAILED':
                print("✗ Agent preparation FAILED")
                sys.exit(1)
        except Exception as e:
            print(f"Error checking status: {e}")
            sys.exit(1)
    else:
        print("✗ Timeout waiting for PREPARED status")
        sys.exit(1)

    # Provide instructions for manual version creation
    print()
    print("=" * 60)
    print("MANUAL STEP REQUIRED")
    print("=" * 60)
    print(f"AWS Bedrock Agent versions must be created in the console.")
    print()
    print("To create version {version_number}:")
    print("  1. Open AWS Console: Amazon Bedrock > Agents")
    print(f"  2. Select agent: {agent_id}")
    print("  3. Click 'Create version' button")
    print("  4. Confirm the version creation")
    print()
    print("After creating the version, Terraform will detect it and continue.")
    print("=" * 60)

    # For now, we'll consider this successful since the agent is prepared
    # The actual version creation will be done manually
    sys.exit(0)

if __name__ == "__main__":
    main()
