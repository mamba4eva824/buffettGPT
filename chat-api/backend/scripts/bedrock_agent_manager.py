#!/usr/bin/env python3
"""
Bedrock Agent Version Manager
Manages agent versions, aliases, and knowledge base associations
"""

import json
import time
import sys
import argparse
import boto3
from typing import Dict, List, Optional, Any

class BedrockAgentManager:
    def __init__(self, agent_id: str, region: str = 'us-east-1'):
        self.agent_id = agent_id
        self.region = region
        self.client = boto3.client('bedrock-agent', region_name=region)

    def get_agent_status(self) -> Dict[str, Any]:
        """Get current agent status and configuration"""
        try:
            response = self.client.get_agent(agentId=self.agent_id)
            agent = response['agent']
            return {
                'status': agent.get('agentStatus'),
                'name': agent.get('agentName'),
                'model': agent.get('foundationModel'),
                'prepared_at': agent.get('preparedAt'),
                'guardrail': agent.get('guardrailConfiguration')
            }
        except Exception as e:
            print(f"Error getting agent status: {e}")
            return {}

    def list_versions(self) -> List[Dict[str, Any]]:
        """List all agent versions"""
        try:
            response = self.client.list_agent_versions(agentId=self.agent_id)
            versions = []
            for v in response.get('agentVersionSummaries', []):
                versions.append({
                    'version': v.get('agentVersion'),
                    'name': v.get('agentName'),
                    'status': v.get('agentStatus'),
                    'model': v.get('foundationModel'),
                    'created_at': v.get('createdAt'),
                    'guardrail': v.get('guardrailConfiguration')
                })
            return sorted(versions, key=lambda x: x['version'])
        except Exception as e:
            print(f"Error listing versions: {e}")
            return []

    def get_knowledge_bases(self, version: str = 'DRAFT') -> List[Dict[str, Any]]:
        """Get knowledge base associations for a specific version"""
        try:
            response = self.client.list_agent_knowledge_bases(
                agentId=self.agent_id,
                agentVersion=version
            )
            kbs = []
            for kb in response.get('agentKnowledgeBaseSummaries', []):
                kbs.append({
                    'id': kb.get('knowledgeBaseId'),
                    'state': kb.get('knowledgeBaseState'),
                    'description': kb.get('description'),
                    'updated_at': kb.get('updatedAt')
                })
            return kbs
        except Exception as e:
            print(f"Error getting knowledge bases for version {version}: {e}")
            return []

    def update_agent(self,
                    foundation_model: Optional[str] = None,
                    instruction: Optional[str] = None,
                    description: Optional[str] = None) -> bool:
        """Update agent DRAFT configuration"""
        try:
            update_params = {'agentId': self.agent_id}

            # Get current configuration
            current = self.client.get_agent(agentId=self.agent_id)['agent']

            # Only include parameters that are being changed
            if foundation_model:
                update_params['foundationModel'] = foundation_model
            else:
                update_params['foundationModel'] = current['foundationModel']

            if instruction:
                update_params['instruction'] = instruction
            else:
                update_params['instruction'] = current.get('instruction', '')

            if description:
                update_params['description'] = description
            else:
                update_params['description'] = current.get('description', '')

            # Preserve required fields
            update_params['agentName'] = current['agentName']
            update_params['agentResourceRoleArn'] = current['agentResourceRoleArn']

            self.client.update_agent(**update_params)
            print(f"Agent updated successfully")
            return True
        except Exception as e:
            print(f"Error updating agent: {e}")
            return False

    def associate_knowledge_base(self, kb_id: str, version: str = 'DRAFT') -> bool:
        """Associate a knowledge base with an agent version"""
        try:
            self.client.associate_agent_knowledge_base(
                agentId=self.agent_id,
                agentVersion=version,
                knowledgeBaseId=kb_id,
                knowledgeBaseState='ENABLED',
                description='Associated via bedrock_agent_manager'
            )
            print(f"Knowledge base {kb_id} associated with version {version}")
            return True
        except Exception as e:
            if 'already exists' in str(e):
                print(f"Knowledge base {kb_id} already associated with version {version}")
                return True
            print(f"Error associating knowledge base: {e}")
            return False

    def disassociate_knowledge_base(self, kb_id: str, version: str = 'DRAFT') -> bool:
        """Disassociate a knowledge base from an agent version"""
        try:
            self.client.disassociate_agent_knowledge_base(
                agentId=self.agent_id,
                agentVersion=version,
                knowledgeBaseId=kb_id
            )
            print(f"Knowledge base {kb_id} disassociated from version {version}")
            return True
        except Exception as e:
            print(f"Error disassociating knowledge base: {e}")
            return False

    def prepare_agent(self) -> bool:
        """Prepare agent (may trigger version creation)"""
        try:
            self.client.prepare_agent(agentId=self.agent_id)
            print("Agent preparation initiated")

            # Wait for preparation to complete
            max_attempts = 30
            for i in range(max_attempts):
                status = self.get_agent_status()
                if status['status'] == 'PREPARED':
                    print("Agent prepared successfully")
                    return True
                elif status['status'] == 'FAILED':
                    print("Agent preparation failed")
                    return False
                print(f"Waiting for agent preparation... ({i+1}/{max_attempts})")
                time.sleep(2)

            print("Agent preparation timed out")
            return False
        except Exception as e:
            print(f"Error preparing agent: {e}")
            return False

    def list_aliases(self) -> List[Dict[str, Any]]:
        """List all agent aliases"""
        try:
            response = self.client.list_agent_aliases(agentId=self.agent_id)
            aliases = []
            for a in response.get('agentAliasSummaries', []):
                aliases.append({
                    'id': a.get('agentAliasId'),
                    'name': a.get('agentAliasName'),
                    'status': a.get('agentAliasStatus'),
                    'routes_to': a.get('routingConfiguration', [{}])[0].get('agentVersion'),
                    'description': a.get('description')
                })
            return aliases
        except Exception as e:
            print(f"Error listing aliases: {e}")
            return []

    def update_alias(self, alias_id: str, version: str) -> bool:
        """Update an alias to point to a specific version"""
        try:
            # Get current alias details
            alias_response = self.client.get_agent_alias(
                agentId=self.agent_id,
                agentAliasId=alias_id
            )
            alias = alias_response['agentAlias']

            # Update alias
            self.client.update_agent_alias(
                agentId=self.agent_id,
                agentAliasId=alias_id,
                agentAliasName=alias['agentAliasName'],
                routingConfiguration=[{'agentVersion': version}]
            )
            print(f"Alias {alias_id} updated to point to version {version}")
            return True
        except Exception as e:
            print(f"Error updating alias: {e}")
            return False

    def create_alias(self, name: str, version: str, description: str = "") -> Optional[str]:
        """Create a new alias"""
        try:
            response = self.client.create_agent_alias(
                agentId=self.agent_id,
                agentAliasName=name,
                routingConfiguration=[{'agentVersion': version}],
                description=description
            )
            alias_id = response['agentAlias']['agentAliasId']
            print(f"Created alias '{name}' with ID {alias_id} pointing to version {version}")
            return alias_id
        except Exception as e:
            print(f"Error creating alias: {e}")
            return None

    def create_version_snapshot(self) -> Optional[str]:
        """Attempt to create a new version by preparing the agent"""
        print("Creating version snapshot...")

        # Get current version count
        versions_before = self.list_versions()
        numbered_versions = [v for v in versions_before if v['version'] not in ['DRAFT']]
        count_before = len(numbered_versions)

        # Prepare agent
        if not self.prepare_agent():
            print("Failed to prepare agent")
            return None

        # Check if a new version was created
        time.sleep(5)  # Give AWS time to create version
        versions_after = self.list_versions()
        numbered_versions_after = [v for v in versions_after if v['version'] not in ['DRAFT']]
        count_after = len(numbered_versions_after)

        if count_after > count_before:
            new_version = str(count_after)
            print(f"Version {new_version} created successfully!")
            return new_version
        else:
            print("No new version was created. This may happen if no significant changes were made.")
            print("To force version creation, make a change to the agent configuration and try again.")
            return None


def main():
    parser = argparse.ArgumentParser(description='Manage Bedrock Agent versions')
    parser.add_argument('--agent-id', required=True, help='Agent ID')
    parser.add_argument('--region', default='us-east-1', help='AWS Region')

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Status command
    subparsers.add_parser('status', help='Show agent status')

    # List versions command
    subparsers.add_parser('list-versions', help='List all versions')

    # List aliases command
    subparsers.add_parser('list-aliases', help='List all aliases')

    # Update agent command
    update_parser = subparsers.add_parser('update', help='Update agent configuration')
    update_parser.add_argument('--model', help='Foundation model')
    update_parser.add_argument('--instruction', help='Agent instruction')
    update_parser.add_argument('--description', help='Agent description')

    # Associate KB command
    associate_parser = subparsers.add_parser('associate-kb', help='Associate knowledge base')
    associate_parser.add_argument('--kb-id', required=True, help='Knowledge base ID')
    associate_parser.add_argument('--version', default='DRAFT', help='Agent version')

    # Prepare agent command
    subparsers.add_parser('prepare', help='Prepare agent')

    # Create version command
    subparsers.add_parser('create-version', help='Create new version snapshot')

    # Update alias command
    alias_parser = subparsers.add_parser('update-alias', help='Update alias routing')
    alias_parser.add_argument('--alias-id', required=True, help='Alias ID')
    alias_parser.add_argument('--version', required=True, help='Version to point to')

    # Create alias command
    create_alias_parser = subparsers.add_parser('create-alias', help='Create new alias')
    create_alias_parser.add_argument('--name', required=True, help='Alias name')
    create_alias_parser.add_argument('--version', required=True, help='Version to point to')
    create_alias_parser.add_argument('--description', default='', help='Alias description')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    manager = BedrockAgentManager(args.agent_id, args.region)

    if args.command == 'status':
        status = manager.get_agent_status()
        print(json.dumps(status, indent=2, default=str))

    elif args.command == 'list-versions':
        versions = manager.list_versions()
        for v in versions:
            print(f"\nVersion: {v['version']}")
            print(f"  Name: {v['name']}")
            print(f"  Model: {v.get('model', 'N/A')}")
            print(f"  Status: {v['status']}")
            print(f"  Created: {v.get('created_at', 'N/A')}")

            # Get KB associations
            kbs = manager.get_knowledge_bases(v['version'])
            if kbs:
                print(f"  Knowledge Bases:")
                for kb in kbs:
                    print(f"    - {kb['id']} ({kb['state']})")

    elif args.command == 'list-aliases':
        aliases = manager.list_aliases()
        for a in aliases:
            print(f"\nAlias: {a['name']}")
            print(f"  ID: {a['id']}")
            print(f"  Routes to: Version {a['routes_to']}")
            print(f"  Status: {a['status']}")
            if a.get('description'):
                print(f"  Description: {a['description']}")

    elif args.command == 'update':
        success = manager.update_agent(
            foundation_model=args.model,
            instruction=args.instruction,
            description=args.description
        )
        sys.exit(0 if success else 1)

    elif args.command == 'associate-kb':
        success = manager.associate_knowledge_base(args.kb_id, args.version)
        sys.exit(0 if success else 1)

    elif args.command == 'prepare':
        success = manager.prepare_agent()
        sys.exit(0 if success else 1)

    elif args.command == 'create-version':
        new_version = manager.create_version_snapshot()
        sys.exit(0 if new_version else 1)

    elif args.command == 'update-alias':
        success = manager.update_alias(args.alias_id, args.version)
        sys.exit(0 if success else 1)

    elif args.command == 'create-alias':
        alias_id = manager.create_alias(args.name, args.version, args.description)
        if alias_id:
            print(f"Created alias with ID: {alias_id}")
        sys.exit(0 if alias_id else 1)


if __name__ == '__main__':
    main()