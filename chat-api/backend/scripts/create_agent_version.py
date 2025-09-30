#!/usr/bin/env python3
"""
Script to create a new version of a Bedrock agent from the current DRAFT state.

This script works around the limitation that AWS CLI doesn't expose the create-agent-version API.
It uses boto3 SDK which has access to the full API surface.
"""

import boto3
import json
import sys
import time
from datetime import datetime

# Configuration
AGENT_ID = "P82I6ITJGO"
REGION = "us-east-1"

def get_agent_status(client, agent_id):
    """Get the current agent status"""
    try:
        response = client.get_agent(agentId=agent_id)
        return response['agent']['agentStatus']
    except Exception as e:
        print(f"Error getting agent status: {e}")
        return None

def prepare_agent_if_needed(client, agent_id):
    """Prepare the agent if it's not already prepared"""
    status = get_agent_status(client, agent_id)

    if status == "PREPARED":
        print(f"Agent is already in PREPARED state")
        return True
    elif status in ["NOT_PREPARED", "UPDATING"]:
        print(f"Agent is in {status} state. Preparing agent...")
        try:
            response = client.prepare_agent(agentId=agent_id)
            print(f"Agent preparation initiated. Status: {response['agentStatus']}")

            # Wait for preparation to complete
            max_attempts = 30
            attempt = 0
            while attempt < max_attempts:
                time.sleep(5)
                status = get_agent_status(client, agent_id)
                print(f"  Checking status... {status}")
                if status == "PREPARED":
                    print("Agent successfully prepared!")
                    return True
                elif status in ["FAILED", "DELETING", "DELETED"]:
                    print(f"Agent preparation failed with status: {status}")
                    return False
                attempt += 1

            print("Timeout waiting for agent preparation")
            return False
        except Exception as e:
            print(f"Error preparing agent: {e}")
            return False
    else:
        print(f"Unexpected agent status: {status}")
        return False

def create_agent_version(client, agent_id, description=None):
    """
    Create a new version of the agent from the current DRAFT.

    AWS Bedrock creates a numbered version when you call the create_agent_version API.
    This captures the current DRAFT configuration as an immutable version.
    """
    try:
        # First ensure the agent is prepared
        if not prepare_agent_if_needed(client, agent_id):
            print("Failed to prepare agent. Cannot create version.")
            return None

        print(f"\nCreating new version for agent {agent_id}...")

        # Build the request
        request = {
            'agentId': agent_id
        }

        if description:
            request['description'] = description

        # Create the version
        response = client.create_agent_version(**request)

        version_info = response['agentVersion']
        print(f"Successfully created agent version!")
        print(f"  Version: {version_info['agentVersion']}")
        print(f"  Name: {version_info['agentName']}")
        print(f"  Status: {version_info['agentStatus']}")
        print(f"  Created: {version_info['createdAt']}")

        return version_info

    except client.exceptions.ConflictException as e:
        print(f"Conflict error: {e}")
        print("This usually means the agent is being updated. Wait a moment and try again.")
        return None
    except client.exceptions.ThrottlingException as e:
        print(f"API throttling error: {e}")
        print("Too many requests. Wait a moment and try again.")
        return None
    except Exception as e:
        print(f"Error creating agent version: {e}")
        # Check if the error message indicates the API is not available
        if "Unknown operation" in str(e) or "InvalidAction" in str(e):
            print("\nThe create_agent_version API might not be available in the CLI.")
            print("However, it should be available in boto3 SDK.")
        return None

def list_agent_versions(client, agent_id):
    """List all versions of the agent"""
    try:
        response = client.list_agent_versions(agentId=agent_id, maxResults=10)
        versions = response['agentVersionSummaries']

        print(f"\nCurrent agent versions:")
        for v in versions:
            print(f"  Version {v['agentVersion']}: {v['agentName']} - Status: {v['agentStatus']} - Updated: {v['updatedAt']}")

        return versions
    except Exception as e:
        print(f"Error listing agent versions: {e}")
        return []

def main():
    """Main execution"""
    print("=" * 60)
    print("Bedrock Agent Version Creator")
    print("=" * 60)

    # Initialize boto3 client
    print(f"\nInitializing Bedrock Agent client for region {REGION}...")
    client = boto3.client('bedrock-agent', region_name=REGION)

    # List current versions
    print(f"\nChecking existing versions for agent {AGENT_ID}...")
    versions_before = list_agent_versions(client, AGENT_ID)

    # Get current agent details
    print(f"\nGetting current DRAFT configuration...")
    try:
        agent_response = client.get_agent(agentId=AGENT_ID)
        agent = agent_response['agent']

        print(f"  Agent Name: {agent['agentName']}")
        print(f"  Foundation Model: {agent['foundationModel']}")
        print(f"  Status: {agent['agentStatus']}")

        # Show knowledge base associations
        kb_response = client.list_agent_knowledge_bases(agentId=AGENT_ID)
        if 'agentKnowledgeBaseSummaries' in kb_response:
            kbs = kb_response['agentKnowledgeBaseSummaries']
            print(f"  Knowledge Bases: {len(kbs)}")
            for kb in kbs:
                print(f"    - {kb['knowledgeBaseId']}: {kb.get('description', 'No description')}")

    except Exception as e:
        print(f"Error getting agent details: {e}")
        return 1

    # Ask for confirmation
    print(f"\n" + "=" * 60)
    print("Ready to create a new version with:")
    print(f"  - Foundation Model: {agent['foundationModel']}")
    print(f"  - Current DRAFT configuration")
    print(f"  - All associated knowledge bases")
    print("=" * 60)

    confirm = input("\nDo you want to create a new version? (yes/no): ").strip().lower()
    if confirm != 'yes':
        print("Operation cancelled.")
        return 0

    # Get optional description
    description = input("Enter a description for the new version (or press Enter to skip): ").strip()
    if not description:
        description = f"Version created on {datetime.now().isoformat()} with Haiku model and updated Pinecone knowledge base"

    # Create the version
    version_info = create_agent_version(client, AGENT_ID, description)

    if version_info:
        print(f"\n" + "=" * 60)
        print("SUCCESS! New version created:")
        print(f"  Version Number: {version_info['agentVersion']}")
        print(f"  Version ARN: {version_info.get('agentArn', 'N/A')}")
        print("=" * 60)

        # List versions again to confirm
        print("\nUpdated version list:")
        list_agent_versions(client, AGENT_ID)

        print(f"\n✅ You can now update your aliases to point to version {version_info['agentVersion']}")
        print(f"   Use: aws bedrock-agent update-agent-alias --agent-id {AGENT_ID} --agent-alias-id <alias-id> --routing-configuration agentVersion={version_info['agentVersion']}")

        return 0
    else:
        print("\n❌ Failed to create agent version")
        return 1

if __name__ == "__main__":
    sys.exit(main())