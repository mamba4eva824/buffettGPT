"""
Unit tests for conversation research_state persistence in conversations_handler.

Tests DynamoDB operations for the conversations table:
- PUT /conversations/{id} with research_state in metadata
- Partial metadata updates (nested attribute update expression)
- Float to Decimal conversion for DynamoDB
- Research state schema validation

Key tests:
1. Metadata creation when it doesn't exist
2. Partial metadata updates without clobbering existing keys
3. research_state nested structure saved correctly
4. User ownership verification

Run:
    cd chat-api/backend
    pytest tests/test_conversations_research_state.py -v
"""

import json
import os
import sys
import pytest
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set environment variables before importing
os.environ['ENVIRONMENT'] = 'test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['CONVERSATIONS_TABLE'] = 'test-conversations'
os.environ['CHAT_MESSAGES_TABLE'] = 'test-chat-messages'
os.environ['PROJECT_NAME'] = 'buffett-test'

# Import after setting env vars
from src.handlers.conversations_handler import (
    update_conversation,
    get_conversation,
    create_conversation,
    create_response,
    get_user_id,
    convert_floats_to_decimal
)


# =============================================================================
# TEST DATA - Mock research_state structures
# =============================================================================

def get_mock_research_state() -> Dict[str, Any]:
    """Generate a mock research_state structure."""
    return {
        'ticker': 'AAPL',
        'active_section_id': '06_growth',
        'visible_sections': ['01_executive_summary', '06_growth', '11_debt'],
        'toc': [
            {'section_id': '01_executive_summary', 'title': 'Executive Summary', 'part': 1},
            {'section_id': '06_growth', 'title': 'Growth Analysis', 'part': 2},
            {'section_id': '11_debt', 'title': 'Debt Analysis', 'part': 2},
        ],
        'ratings': {
            'growth': {'rating': 'Stable', 'confidence': 0.85},
            'debt': {'rating': 'Strong', 'confidence': 0.9},
            'overall_verdict': 'HOLD',
            'conviction': 'High'
        },
        'report_generated_at': '2024-01-01T12:00:00Z',
        'report_expires_at': '2024-04-01T12:00:00Z'
    }


def get_mock_conversation(user_id: str, with_metadata: bool = False, with_research_state: bool = False) -> Dict[str, Any]:
    """Generate a mock conversation record."""
    conv = {
        'conversation_id': 'test-conv-123',
        'user_id': user_id,
        'title': 'Research: AAPL',
        'created_at': '2024-01-01T10:00:00Z',
        'updated_at': 1704099600,  # Unix timestamp
        'message_count': 5,
        'is_archived': False,
        'user_type': 'authenticated'
    }

    if with_metadata:
        conv['metadata'] = {'source': 'research', 'version': '2.0'}
        if with_research_state:
            conv['metadata']['research_state'] = get_mock_research_state()

    return conv


def create_mock_event(
    method: str,
    path: str,
    user_id: str = 'test-user-123',
    body: Dict = None,
    path_params: Dict = None
) -> Dict[str, Any]:
    """Create a mock API Gateway event."""
    event = {
        'requestContext': {
            'http': {
                'method': method,
                'path': path
            },
            'authorizer': {
                'lambda': {
                    'user_id': user_id
                }
            }
        },
        'pathParameters': path_params or {},
        'queryStringParameters': {},
        'headers': {}
    }

    if body:
        event['body'] = json.dumps(body)

    return event


# =============================================================================
# FLOAT TO DECIMAL CONVERSION TESTS
# =============================================================================

class TestConvertFloatsToDecimal:
    """Tests for convert_floats_to_decimal utility function."""

    def test_converts_simple_float(self):
        """Verify simple float is converted to Decimal."""
        result = convert_floats_to_decimal(0.85)

        assert isinstance(result, Decimal)
        assert result == Decimal('0.85')

    def test_converts_nested_floats(self):
        """Verify nested floats in dicts are converted."""
        data = {
            'ratings': {
                'confidence': 0.9,
                'score': 8.5
            }
        }

        result = convert_floats_to_decimal(data)

        assert isinstance(result['ratings']['confidence'], Decimal)
        assert isinstance(result['ratings']['score'], Decimal)

    def test_converts_floats_in_lists(self):
        """Verify floats in lists are converted."""
        data = [0.1, 0.2, 0.3]

        result = convert_floats_to_decimal(data)

        assert all(isinstance(x, Decimal) for x in result)

    def test_preserves_non_float_types(self):
        """Verify non-float types are preserved."""
        data = {
            'ticker': 'AAPL',
            'count': 100,
            'active': True,
            'items': ['a', 'b', 'c']
        }

        result = convert_floats_to_decimal(data)

        assert result['ticker'] == 'AAPL'
        assert result['count'] == 100
        assert result['active'] is True
        assert result['items'] == ['a', 'b', 'c']

    def test_converts_research_state(self):
        """Verify research_state with floats is converted correctly."""
        research_state = get_mock_research_state()

        result = convert_floats_to_decimal(research_state)

        # Check confidence values are Decimals
        assert isinstance(result['ratings']['growth']['confidence'], Decimal)
        assert isinstance(result['ratings']['debt']['confidence'], Decimal)


# =============================================================================
# UPDATE CONVERSATION TESTS
# =============================================================================

class TestUpdateConversationWithResearchState:
    """Tests for PUT /conversations/{id} with research_state."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock Lambda context."""
        context = MagicMock()
        context.aws_request_id = 'test-request-id'
        return context

    def test_creates_metadata_when_not_exists(self, mock_context):
        """Verify metadata is created when conversation has no metadata."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        # Existing conversation WITHOUT metadata
        existing_conv = get_mock_conversation(user_id, with_metadata=False)

        # Request body with metadata
        body = {
            'metadata': {
                'research_state': get_mock_research_state()
            }
        }

        event = create_mock_event(
            method='PUT',
            path=f'/conversations/{conversation_id}',
            user_id=user_id,
            body=body,
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': existing_conv}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = update_conversation(event)

            assert response['statusCode'] == 200

            # Verify update_item was called
            mock_table.update_item.assert_called_once()

            # Get the call kwargs
            call_kwargs = mock_table.update_item.call_args.kwargs
            update_expr = call_kwargs['UpdateExpression']
            attr_values = call_kwargs['ExpressionAttributeValues']

            # When metadata doesn't exist, should set the whole metadata object
            assert '#metadata = :metadata' in update_expr
            assert ':metadata' in attr_values
            assert 'research_state' in attr_values[':metadata']

    def test_partial_metadata_update_preserves_existing_keys(self, mock_context):
        """Verify partial metadata update doesn't clobber other keys."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        # Existing conversation WITH metadata (but no research_state)
        existing_conv = get_mock_conversation(user_id, with_metadata=True, with_research_state=False)

        # Request to add research_state
        body = {
            'metadata': {
                'research_state': get_mock_research_state()
            }
        }

        event = create_mock_event(
            method='PUT',
            path=f'/conversations/{conversation_id}',
            user_id=user_id,
            body=body,
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': existing_conv}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = update_conversation(event)

            assert response['statusCode'] == 200

            # Verify update_item was called with merge + replace approach
            mock_table.update_item.assert_called_once()

            call_kwargs = mock_table.update_item.call_args.kwargs
            update_expr = call_kwargs['UpdateExpression']
            attr_names = call_kwargs.get('ExpressionAttributeNames', {})
            attr_values = call_kwargs['ExpressionAttributeValues']

            # Should use merge + replace approach (not nested paths)
            assert '#metadata = :metadata' in update_expr
            assert '#metadata' in attr_names

            # Verify existing metadata keys were preserved in merged value
            merged_metadata = attr_values[':metadata']
            assert 'source' in merged_metadata  # Original key preserved
            assert 'version' in merged_metadata  # Original key preserved
            assert 'research_state' in merged_metadata  # New key added

    def test_research_state_floats_converted_to_decimal(self, mock_context):
        """Verify float values in research_state are converted to Decimal."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        existing_conv = get_mock_conversation(user_id, with_metadata=False)

        # Research state with float confidence values
        body = {
            'metadata': {
                'research_state': {
                    'ticker': 'AAPL',
                    'ratings': {
                        'confidence': 0.85  # This is a float
                    }
                }
            }
        }

        event = create_mock_event(
            method='PUT',
            path=f'/conversations/{conversation_id}',
            user_id=user_id,
            body=body,
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': existing_conv}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = update_conversation(event)

            assert response['statusCode'] == 200

            # Verify Decimals in the update
            call_kwargs = mock_table.update_item.call_args.kwargs
            attr_values = call_kwargs['ExpressionAttributeValues']

            # Find the metadata value
            metadata_value = attr_values.get(':metadata') or attr_values.get(':meta_research_state')
            if metadata_value:
                # Check if float was converted
                if isinstance(metadata_value, dict) and 'research_state' in metadata_value:
                    rs = metadata_value['research_state']
                elif isinstance(metadata_value, dict) and 'ratings' in metadata_value:
                    rs = metadata_value
                else:
                    rs = metadata_value

                if 'ratings' in rs:
                    confidence = rs['ratings'].get('confidence')
                    assert isinstance(confidence, Decimal), f"Expected Decimal, got {type(confidence)}"

    def test_research_state_toc_saved_correctly(self, mock_context):
        """Verify ToC structure is saved correctly in research_state."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        existing_conv = get_mock_conversation(user_id, with_metadata=False)

        toc = [
            {'section_id': '01_exec', 'title': 'Executive Summary', 'part': 1},
            {'section_id': '06_growth', 'title': 'Growth', 'part': 2}
        ]

        body = {
            'metadata': {
                'research_state': {
                    'ticker': 'AAPL',
                    'toc': toc,
                    'active_section_id': '01_exec',
                    'visible_sections': ['01_exec']
                }
            }
        }

        event = create_mock_event(
            method='PUT',
            path=f'/conversations/{conversation_id}',
            user_id=user_id,
            body=body,
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': existing_conv}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = update_conversation(event)

            assert response['statusCode'] == 200

            # Verify ToC was included
            call_kwargs = mock_table.update_item.call_args.kwargs
            attr_values = call_kwargs['ExpressionAttributeValues']
            metadata_value = attr_values.get(':metadata')

            assert metadata_value is not None
            assert 'research_state' in metadata_value
            assert 'toc' in metadata_value['research_state']
            assert len(metadata_value['research_state']['toc']) == 2


    def test_merge_preserves_all_existing_metadata_keys(self, mock_context):
        """Verify merge approach preserves ALL existing metadata keys, not just some."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        # Existing conversation with multiple metadata keys
        existing_conv = {
            'conversation_id': conversation_id,
            'user_id': user_id,
            'title': 'Research: AAPL',
            'created_at': '2024-01-01T10:00:00Z',
            'updated_at': 1704099600,
            'metadata': {
                'source': 'research',
                'version': '2.0',
                'theme': 'dark',
                'custom_key': {'nested': 'value'}
            }
        }

        # Request to add research_state (should not clobber existing keys)
        body = {
            'metadata': {
                'research_state': get_mock_research_state()
            }
        }

        event = create_mock_event(
            method='PUT',
            path=f'/conversations/{conversation_id}',
            user_id=user_id,
            body=body,
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': existing_conv}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = update_conversation(event)

            assert response['statusCode'] == 200

            call_kwargs = mock_table.update_item.call_args.kwargs
            attr_values = call_kwargs['ExpressionAttributeValues']
            merged_metadata = attr_values[':metadata']

            # All original keys must be preserved
            assert merged_metadata['source'] == 'research'
            assert merged_metadata['version'] == '2.0'
            assert merged_metadata['theme'] == 'dark'
            assert merged_metadata['custom_key'] == {'nested': 'value'}
            # New key added
            assert 'research_state' in merged_metadata

    def test_update_overwrites_existing_research_state(self, mock_context):
        """Verify updating research_state overwrites the previous value."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        # Existing conversation WITH research_state already
        existing_conv = get_mock_conversation(user_id, with_metadata=True, with_research_state=True)

        # New research_state that should overwrite the old one
        new_research_state = {
            'ticker': 'AAPL',
            'active_section_id': '11_debt',  # Changed from 06_growth
            'visible_sections': ['01_executive_summary', '11_debt', '12_realtalk'],  # Different sections
        }

        body = {
            'metadata': {
                'research_state': new_research_state
            }
        }

        event = create_mock_event(
            method='PUT',
            path=f'/conversations/{conversation_id}',
            user_id=user_id,
            body=body,
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': existing_conv}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = update_conversation(event)

            assert response['statusCode'] == 200

            call_kwargs = mock_table.update_item.call_args.kwargs
            attr_values = call_kwargs['ExpressionAttributeValues']
            merged_metadata = attr_values[':metadata']

            # research_state should be the new one
            rs = merged_metadata['research_state']
            assert rs['active_section_id'] == '11_debt'
            assert '12_realtalk' in rs['visible_sections']
            # Original metadata key preserved
            assert 'source' in merged_metadata

    def test_handles_empty_existing_metadata(self, mock_context):
        """Verify update works when existing metadata is empty dict."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        # Existing conversation with empty metadata
        existing_conv = {
            'conversation_id': conversation_id,
            'user_id': user_id,
            'title': 'Research: AAPL',
            'metadata': {}  # Empty but exists
        }

        body = {
            'metadata': {
                'research_state': get_mock_research_state()
            }
        }

        event = create_mock_event(
            method='PUT',
            path=f'/conversations/{conversation_id}',
            user_id=user_id,
            body=body,
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': existing_conv}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = update_conversation(event)

            assert response['statusCode'] == 200

            call_kwargs = mock_table.update_item.call_args.kwargs
            attr_values = call_kwargs['ExpressionAttributeValues']
            merged_metadata = attr_values[':metadata']

            # Should have the new research_state
            assert 'research_state' in merged_metadata
            assert merged_metadata['research_state']['ticker'] == 'AAPL'


# =============================================================================
# GET CONVERSATION TESTS
# =============================================================================

class TestGetConversationWithResearchState:
    """Tests for GET /conversations/{id} with research_state."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock Lambda context."""
        context = MagicMock()
        context.aws_request_id = 'test-request-id'
        return context

    def test_returns_research_state_in_metadata(self, mock_context):
        """Verify research_state is returned in conversation metadata."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        existing_conv = get_mock_conversation(user_id, with_metadata=True, with_research_state=True)

        event = create_mock_event(
            method='GET',
            path=f'/conversations/{conversation_id}',
            user_id=user_id,
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': existing_conv}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = get_conversation(event)

            assert response['statusCode'] == 200

            body = json.loads(response['body'])
            assert 'metadata' in body
            assert 'research_state' in body['metadata']
            assert body['metadata']['research_state']['ticker'] == 'AAPL'

    def test_returns_empty_metadata_when_not_exists(self, mock_context):
        """Verify empty metadata doesn't cause errors."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        existing_conv = get_mock_conversation(user_id, with_metadata=False)

        event = create_mock_event(
            method='GET',
            path=f'/conversations/{conversation_id}',
            user_id=user_id,
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': existing_conv}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = get_conversation(event)

            assert response['statusCode'] == 200


# =============================================================================
# OWNERSHIP VERIFICATION TESTS
# =============================================================================

class TestConversationOwnership:
    """Tests for conversation ownership verification."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock Lambda context."""
        context = MagicMock()
        context.aws_request_id = 'test-request-id'
        return context

    def test_access_denied_for_different_user(self, mock_context):
        """Verify 403 is returned when user doesn't own conversation."""
        owner_id = 'owner-user-123'
        requester_id = 'other-user-456'
        conversation_id = 'test-conv-123'

        existing_conv = get_mock_conversation(owner_id)

        event = create_mock_event(
            method='GET',
            path=f'/conversations/{conversation_id}',
            user_id=requester_id,
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': existing_conv}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = get_conversation(event)

            assert response['statusCode'] == 403
            body = json.loads(response['body'])
            assert 'Access denied' in body['error']

    def test_update_denied_for_different_user(self, mock_context):
        """Verify 403 is returned when trying to update another user's conversation."""
        owner_id = 'owner-user-123'
        requester_id = 'other-user-456'
        conversation_id = 'test-conv-123'

        existing_conv = get_mock_conversation(owner_id)

        event = create_mock_event(
            method='PUT',
            path=f'/conversations/{conversation_id}',
            user_id=requester_id,
            body={'title': 'Hacked title'},
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': existing_conv}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = update_conversation(event)

            assert response['statusCode'] == 403

    def test_access_allowed_for_owner(self, mock_context):
        """Verify access is allowed for conversation owner."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        existing_conv = get_mock_conversation(user_id)

        event = create_mock_event(
            method='GET',
            path=f'/conversations/{conversation_id}',
            user_id=user_id,
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': existing_conv}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = get_conversation(event)

            assert response['statusCode'] == 200


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================

class TestErrorHandling:
    """Tests for error handling in conversations handler."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock Lambda context."""
        context = MagicMock()
        context.aws_request_id = 'test-request-id'
        return context

    def test_returns_404_for_nonexistent_conversation(self, mock_context):
        """Verify 404 is returned for non-existent conversation."""
        user_id = 'test-user-123'
        conversation_id = 'nonexistent-conv'

        event = create_mock_event(
            method='GET',
            path=f'/conversations/{conversation_id}',
            user_id=user_id,
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No Item

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = get_conversation(event)

            assert response['statusCode'] == 404

    def test_handles_dynamodb_error(self, mock_context):
        """Verify DynamoDB errors are handled gracefully."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        event = create_mock_event(
            method='GET',
            path=f'/conversations/{conversation_id}',
            user_id=user_id,
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'DynamoDB error'}},
            'GetItem'
        )

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = get_conversation(event)

            assert response['statusCode'] == 500


# =============================================================================
# CREATE CONVERSATION TESTS
# =============================================================================

class TestCreateConversationWithMetadata:
    """Tests for POST /conversations with initial metadata."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock Lambda context."""
        context = MagicMock()
        context.aws_request_id = 'test-request-id'
        return context

    def test_creates_conversation_with_initial_metadata(self, mock_context):
        """Verify conversation can be created with initial metadata."""
        user_id = 'test-user-123'

        body = {
            'title': 'Research: AAPL',
            'metadata': {
                'source': 'research',
                'research_state': get_mock_research_state()
            }
        }

        event = create_mock_event(
            method='POST',
            path='/conversations',
            user_id=user_id,
            body=body
        )

        mock_table = MagicMock()

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = create_conversation(event)

            assert response['statusCode'] == 201

            # Verify put_item was called
            mock_table.put_item.assert_called_once()

            # Verify metadata was included
            call_kwargs = mock_table.put_item.call_args.kwargs
            item = call_kwargs['Item']
            assert 'metadata' in item
            assert 'research_state' in item['metadata']


# =============================================================================
# RUN TESTS DIRECTLY
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
