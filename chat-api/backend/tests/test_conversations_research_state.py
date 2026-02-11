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
    get_conversation_messages,
    save_conversation_message,
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
# SECURITY: get_user_id TESTS (CRIT-1 - identity spoofing prevention)
# =============================================================================

class TestGetUserIdSecurity:
    """Verify get_user_id only trusts API Gateway authorizer context."""

    def test_returns_user_id_from_authorizer_lambda_context(self):
        """AC-4: Properly authenticated request returns correct user_id."""
        event = create_mock_event('GET', '/conversations', user_id='real-user-456')
        assert get_user_id(event) == 'real-user-456'

    def test_rejects_forged_jwt_in_authorization_header(self):
        """AC-1: Forged JWT (no signature verification) must NOT return a user_id."""
        import base64
        # Craft a JWT with a fake user_id — valid structure, no valid signature
        fake_payload = base64.urlsafe_b64encode(
            json.dumps({'user_id': 'victim-123', 'sub': 'victim-123'}).encode()
        ).rstrip(b'=').decode()
        forged_jwt = f'eyJhbGciOiJIUzI1NiJ9.{fake_payload}.fakesignature'

        event = {
            'requestContext': {'http': {'method': 'GET', 'path': '/conversations'}},
            'pathParameters': {},
            'queryStringParameters': {},
            'headers': {'authorization': f'Bearer {forged_jwt}'}
        }
        # No authorizer context → must return None, NOT the forged user_id
        assert get_user_id(event) is None

    def test_rejects_user_id_from_query_params(self):
        """AC-3: user_id in query params must be ignored."""
        event = {
            'requestContext': {'http': {'method': 'GET', 'path': '/conversations'}},
            'pathParameters': {},
            'queryStringParameters': {'user_id': 'spoofed-user'},
            'headers': {}
        }
        assert get_user_id(event) is None

    def test_rejects_x_user_id_header(self):
        """AC-3: x-user-id header must be ignored."""
        event = {
            'requestContext': {'http': {'method': 'GET', 'path': '/conversations'}},
            'pathParameters': {},
            'queryStringParameters': {},
            'headers': {'x-user-id': 'spoofed-user'}
        }
        assert get_user_id(event) is None

    def test_returns_none_when_no_authorizer(self):
        """AC-5: No auth context returns None (handler will respond 401)."""
        event = {
            'requestContext': {'http': {'method': 'GET', 'path': '/conversations'}},
            'pathParameters': {},
            'queryStringParameters': {},
            'headers': {}
        }
        assert get_user_id(event) is None


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
# GET CONVERSATION MESSAGES PAGINATION TESTS
# =============================================================================

class TestGetConversationMessagesPagination:
    """Tests for GET /conversations/{id}/messages with limit and cursor pagination."""

    def _make_event(self, user_id='test-user-123', conversation_id='test-conv-123',
                    query_params=None):
        """Helper to create a GET messages event with optional query params."""
        event = create_mock_event(
            method='GET',
            path=f'/conversations/{conversation_id}/messages',
            user_id=user_id,
            path_params={'conversation_id': conversation_id}
        )
        if query_params:
            event['queryStringParameters'] = query_params
        return event

    def test_default_limit_is_200(self):
        """Verify default limit of 200 is passed to DynamoDB query."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        mock_conv_table = MagicMock()
        mock_conv_table.get_item.return_value = {
            'Item': {'conversation_id': conversation_id, 'user_id': user_id}
        }

        mock_msg_table = MagicMock()
        mock_msg_table.query.return_value = {'Items': [], 'Count': 0}

        event = self._make_event(user_id=user_id, conversation_id=conversation_id)

        with patch('src.handlers.conversations_handler.conversations_table', mock_conv_table), \
             patch('src.handlers.conversations_handler.messages_table', mock_msg_table):
            response = get_conversation_messages(event)

            assert response['statusCode'] == 200

            # Verify Limit=200 was passed to DynamoDB query
            query_kwargs = mock_msg_table.query.call_args.kwargs
            assert query_kwargs['Limit'] == 200

    def test_custom_limit_passed_to_query(self):
        """Verify custom limit from query params is passed to DynamoDB."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        mock_conv_table = MagicMock()
        mock_conv_table.get_item.return_value = {
            'Item': {'conversation_id': conversation_id, 'user_id': user_id}
        }

        mock_msg_table = MagicMock()
        mock_msg_table.query.return_value = {'Items': [], 'Count': 0}

        event = self._make_event(
            user_id=user_id,
            conversation_id=conversation_id,
            query_params={'limit': '50'}
        )

        with patch('src.handlers.conversations_handler.conversations_table', mock_conv_table), \
             patch('src.handlers.conversations_handler.messages_table', mock_msg_table):
            response = get_conversation_messages(event)

            assert response['statusCode'] == 200
            query_kwargs = mock_msg_table.query.call_args.kwargs
            assert query_kwargs['Limit'] == 50

    def test_limit_clamped_to_max_500(self):
        """Verify limit is clamped to maximum of 500."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        mock_conv_table = MagicMock()
        mock_conv_table.get_item.return_value = {
            'Item': {'conversation_id': conversation_id, 'user_id': user_id}
        }

        mock_msg_table = MagicMock()
        mock_msg_table.query.return_value = {'Items': [], 'Count': 0}

        event = self._make_event(
            user_id=user_id,
            conversation_id=conversation_id,
            query_params={'limit': '9999'}
        )

        with patch('src.handlers.conversations_handler.conversations_table', mock_conv_table), \
             patch('src.handlers.conversations_handler.messages_table', mock_msg_table):
            response = get_conversation_messages(event)

            assert response['statusCode'] == 200
            query_kwargs = mock_msg_table.query.call_args.kwargs
            assert query_kwargs['Limit'] == 500

    def test_limit_clamped_to_min_1(self):
        """Verify limit is clamped to minimum of 1."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        mock_conv_table = MagicMock()
        mock_conv_table.get_item.return_value = {
            'Item': {'conversation_id': conversation_id, 'user_id': user_id}
        }

        mock_msg_table = MagicMock()
        mock_msg_table.query.return_value = {'Items': [], 'Count': 0}

        event = self._make_event(
            user_id=user_id,
            conversation_id=conversation_id,
            query_params={'limit': '0'}
        )

        with patch('src.handlers.conversations_handler.conversations_table', mock_conv_table), \
             patch('src.handlers.conversations_handler.messages_table', mock_msg_table):
            response = get_conversation_messages(event)

            assert response['statusCode'] == 200
            query_kwargs = mock_msg_table.query.call_args.kwargs
            assert query_kwargs['Limit'] == 1

    def test_next_cursor_returned_when_more_results(self):
        """Verify next_cursor is returned when DynamoDB has LastEvaluatedKey."""
        import base64
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        mock_conv_table = MagicMock()
        mock_conv_table.get_item.return_value = {
            'Item': {'conversation_id': conversation_id, 'user_id': user_id}
        }

        last_key = {'conversation_id': conversation_id, 'timestamp': 1234567890}
        mock_msg_table = MagicMock()
        mock_msg_table.query.return_value = {
            'Items': [{'conversation_id': conversation_id, 'timestamp': 1234567890,
                        'content': 'hello', 'message_type': 'user'}],
            'Count': 1,
            'LastEvaluatedKey': last_key
        }

        event = self._make_event(user_id=user_id, conversation_id=conversation_id)

        with patch('src.handlers.conversations_handler.conversations_table', mock_conv_table), \
             patch('src.handlers.conversations_handler.messages_table', mock_msg_table):
            response = get_conversation_messages(event)

            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert 'next_cursor' in body

            # Decode the cursor and verify it matches the LastEvaluatedKey
            decoded = json.loads(base64.b64decode(body['next_cursor']).decode('utf-8'))
            assert decoded['conversation_id'] == conversation_id
            assert decoded['timestamp'] == 1234567890

    def test_no_next_cursor_when_no_more_results(self):
        """Verify next_cursor is absent when DynamoDB has no LastEvaluatedKey."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        mock_conv_table = MagicMock()
        mock_conv_table.get_item.return_value = {
            'Item': {'conversation_id': conversation_id, 'user_id': user_id}
        }

        mock_msg_table = MagicMock()
        mock_msg_table.query.return_value = {
            'Items': [{'conversation_id': conversation_id, 'timestamp': 1234567890,
                        'content': 'hello', 'message_type': 'user'}],
            'Count': 1
        }

        event = self._make_event(user_id=user_id, conversation_id=conversation_id)

        with patch('src.handlers.conversations_handler.conversations_table', mock_conv_table), \
             patch('src.handlers.conversations_handler.messages_table', mock_msg_table):
            response = get_conversation_messages(event)

            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert 'next_cursor' not in body

    def test_cursor_passed_as_exclusive_start_key(self):
        """Verify cursor is decoded and passed as ExclusiveStartKey."""
        import base64
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        mock_conv_table = MagicMock()
        mock_conv_table.get_item.return_value = {
            'Item': {'conversation_id': conversation_id, 'user_id': user_id}
        }

        mock_msg_table = MagicMock()
        mock_msg_table.query.return_value = {'Items': [], 'Count': 0}

        # Encode a cursor
        start_key = {'conversation_id': conversation_id, 'timestamp': 1000000}
        encoded_cursor = base64.b64encode(
            json.dumps(start_key).encode('utf-8')
        ).decode('utf-8')

        event = self._make_event(
            user_id=user_id,
            conversation_id=conversation_id,
            query_params={'cursor': encoded_cursor}
        )

        with patch('src.handlers.conversations_handler.conversations_table', mock_conv_table), \
             patch('src.handlers.conversations_handler.messages_table', mock_msg_table):
            response = get_conversation_messages(event)

            assert response['statusCode'] == 200
            query_kwargs = mock_msg_table.query.call_args.kwargs
            assert 'ExclusiveStartKey' in query_kwargs
            assert query_kwargs['ExclusiveStartKey'] == start_key

    def test_invalid_cursor_returns_400(self):
        """Verify invalid (non-base64/non-JSON) cursor returns 400."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        mock_conv_table = MagicMock()
        mock_conv_table.get_item.return_value = {
            'Item': {'conversation_id': conversation_id, 'user_id': user_id}
        }

        mock_msg_table = MagicMock()

        event = self._make_event(
            user_id=user_id,
            conversation_id=conversation_id,
            query_params={'cursor': 'not-valid-base64!!!'}
        )

        with patch('src.handlers.conversations_handler.conversations_table', mock_conv_table), \
             patch('src.handlers.conversations_handler.messages_table', mock_msg_table):
            response = get_conversation_messages(event)

            assert response['statusCode'] == 400
            body = json.loads(response['body'])
            assert 'Invalid cursor' in body['error']

    def test_access_denied_for_non_owner(self):
        """Verify 403 when user does not own the conversation."""
        owner_id = 'owner-user-123'
        requester_id = 'other-user-456'
        conversation_id = 'test-conv-123'

        mock_conv_table = MagicMock()
        mock_conv_table.get_item.return_value = {
            'Item': {'conversation_id': conversation_id, 'user_id': owner_id}
        }

        mock_msg_table = MagicMock()

        event = self._make_event(user_id=requester_id, conversation_id=conversation_id)

        with patch('src.handlers.conversations_handler.conversations_table', mock_conv_table), \
             patch('src.handlers.conversations_handler.messages_table', mock_msg_table):
            response = get_conversation_messages(event)

            assert response['statusCode'] == 403
            # Messages table should NOT be queried
            mock_msg_table.query.assert_not_called()


# =============================================================================
# SAVE MESSAGE OWNERSHIP CHECK TESTS (ConditionExpression pattern)
# =============================================================================

class TestSaveMessageOwnershipCheck:
    """Tests for POST /conversations/{id}/messages with ConditionExpression ownership."""

    def _make_event(self, user_id='test-user-123', conversation_id='test-conv-123',
                    body=None):
        """Helper to create a POST message event."""
        if body is None:
            body = {'content': 'Test message', 'message_type': 'user'}
        return create_mock_event(
            method='POST',
            path=f'/conversations/{conversation_id}/messages',
            user_id=user_id,
            body=body,
            path_params={'conversation_id': conversation_id}
        )

    def test_save_message_succeeds_for_owner(self):
        """Verify message is saved when user owns the conversation."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        mock_conv_table = MagicMock()
        mock_msg_table = MagicMock()

        event = self._make_event(user_id=user_id, conversation_id=conversation_id)

        with patch('src.handlers.conversations_handler.conversations_table', mock_conv_table), \
             patch('src.handlers.conversations_handler.messages_table', mock_msg_table):
            response = save_conversation_message(event)

            assert response['statusCode'] == 201
            body = json.loads(response['body'])
            assert 'message_id' in body
            assert body['conversation_id'] == conversation_id

            # Verify put_item was called on messages table
            mock_msg_table.put_item.assert_called_once()

            # Verify update_item was called with ConditionExpression
            mock_conv_table.update_item.assert_called_once()
            update_kwargs = mock_conv_table.update_item.call_args.kwargs
            assert update_kwargs['ConditionExpression'] == 'user_id = :user'
            assert update_kwargs['ExpressionAttributeValues'][':user'] == user_id

    def test_save_message_put_item_before_update_item(self):
        """Verify messages_table.put_item is called BEFORE conversations_table.update_item."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        call_order = []

        mock_conv_table = MagicMock()
        mock_conv_table.update_item.side_effect = lambda **kw: call_order.append('update_item')

        mock_msg_table = MagicMock()
        mock_msg_table.put_item.side_effect = lambda **kw: call_order.append('put_item')

        event = self._make_event(user_id=user_id, conversation_id=conversation_id)

        with patch('src.handlers.conversations_handler.conversations_table', mock_conv_table), \
             patch('src.handlers.conversations_handler.messages_table', mock_msg_table):
            response = save_conversation_message(event)

            assert response['statusCode'] == 201
            assert call_order == ['put_item', 'update_item']

    def test_save_message_returns_403_when_condition_fails(self):
        """Verify 403 when ConditionExpression fails (wrong user)."""
        user_id = 'wrong-user-456'
        conversation_id = 'test-conv-123'

        mock_conv_table = MagicMock()
        mock_conv_table.update_item.side_effect = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException',
                       'Message': 'The conditional request failed'}},
            'UpdateItem'
        )

        mock_msg_table = MagicMock()

        event = self._make_event(user_id=user_id, conversation_id=conversation_id)

        with patch('src.handlers.conversations_handler.conversations_table', mock_conv_table), \
             patch('src.handlers.conversations_handler.messages_table', mock_msg_table):
            response = save_conversation_message(event)

            assert response['statusCode'] == 403
            body = json.loads(response['body'])
            assert 'Access denied' in body['error']

    def test_save_message_returns_400_for_missing_content(self):
        """Verify 400 when message content is missing."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        event = self._make_event(
            user_id=user_id,
            conversation_id=conversation_id,
            body={'message_type': 'user'}  # No 'content'
        )

        mock_conv_table = MagicMock()
        mock_msg_table = MagicMock()

        with patch('src.handlers.conversations_handler.conversations_table', mock_conv_table), \
             patch('src.handlers.conversations_handler.messages_table', mock_msg_table):
            response = save_conversation_message(event)

            assert response['statusCode'] == 400
            body = json.loads(response['body'])
            assert 'content' in body['error'].lower()

    def test_save_message_other_client_error_returns_500(self):
        """Verify non-ConditionalCheckFailed ClientError returns 500."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        mock_conv_table = MagicMock()
        mock_conv_table.update_item.side_effect = ClientError(
            {'Error': {'Code': 'ProvisionedThroughputExceededException',
                       'Message': 'Throughput exceeded'}},
            'UpdateItem'
        )

        mock_msg_table = MagicMock()

        event = self._make_event(user_id=user_id, conversation_id=conversation_id)

        with patch('src.handlers.conversations_handler.conversations_table', mock_conv_table), \
             patch('src.handlers.conversations_handler.messages_table', mock_msg_table):
            response = save_conversation_message(event)

            assert response['statusCode'] == 500


# =============================================================================
# UPDATE CONVERSATION PROJECTION EXPRESSION TESTS
# =============================================================================

class TestUpdateConversationProjection:
    """Tests for update_conversation GetItem using ProjectionExpression."""

    def test_get_item_uses_projection_expression(self):
        """Verify GetItem fetches only user_id and metadata using ProjectionExpression."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        existing_conv = {
            'user_id': user_id,
            'metadata': {'source': 'research'}
        }

        event = create_mock_event(
            method='PUT',
            path=f'/conversations/{conversation_id}',
            user_id=user_id,
            body={'title': 'Updated Title'},
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': existing_conv}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = update_conversation(event)

            assert response['statusCode'] == 200

            # Verify get_item was called with ProjectionExpression
            get_item_kwargs = mock_table.get_item.call_args.kwargs
            assert get_item_kwargs['ProjectionExpression'] == 'user_id, #metadata'
            assert get_item_kwargs['ExpressionAttributeNames'] == {'#metadata': 'metadata'}

    def test_projection_returns_only_needed_fields(self):
        """Verify update works when GetItem returns only projected fields (no title, etc)."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        # Simulates DynamoDB returning only projected fields
        projected_item = {
            'user_id': user_id,
            'metadata': {}
        }

        event = create_mock_event(
            method='PUT',
            path=f'/conversations/{conversation_id}',
            user_id=user_id,
            body={'metadata': {'research_state': {'ticker': 'MSFT'}}},
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': projected_item}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = update_conversation(event)

            assert response['statusCode'] == 200
            mock_table.update_item.assert_called_once()

            call_kwargs = mock_table.update_item.call_args.kwargs
            merged_metadata = call_kwargs['ExpressionAttributeValues'][':metadata']
            assert merged_metadata['research_state']['ticker'] == 'MSFT'


# =============================================================================
# GET CONVERSATION PROJECTION EXPRESSION TESTS
# =============================================================================

class TestGetConversationProjection:
    """Tests for get_conversation using ProjectionExpression to reduce payload."""

    def test_get_item_uses_projection_expression(self):
        """Verify GetItem fetches only essential fields using ProjectionExpression."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        conversation = {
            'conversation_id': conversation_id,
            'user_id': user_id,
            'title': 'Research: AAPL',
            'metadata': {'research_state': {'ticker': 'AAPL'}},
            'created_at': '2026-01-01T00:00:00Z',
            'updated_at': '2026-01-01T00:00:00Z',
        }

        event = create_mock_event(
            method='GET',
            path=f'/conversations/{conversation_id}',
            user_id=user_id,
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': conversation}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = get_conversation(event)

            assert response['statusCode'] == 200

            # Verify get_item was called with ProjectionExpression
            get_item_kwargs = mock_table.get_item.call_args.kwargs
            assert 'ProjectionExpression' in get_item_kwargs
            assert 'conversation_id' in get_item_kwargs['ProjectionExpression']
            assert 'user_id' in get_item_kwargs['ProjectionExpression']
            assert 'title' in get_item_kwargs['ProjectionExpression']
            assert '#metadata' in get_item_kwargs['ProjectionExpression']
            assert 'message_count' in get_item_kwargs['ProjectionExpression']
            assert get_item_kwargs['ExpressionAttributeNames'] == {'#metadata': 'metadata'}

    def test_projection_returns_metadata_with_research_state(self):
        """Verify research_state metadata is included in projected response."""
        user_id = 'test-user-123'
        conversation_id = 'test-conv-123'

        research_state = {
            'ticker': 'AAPL',
            'toc': [{'section_id': '01_executive_summary', 'title': 'Executive Summary'}],
            'visible_sections': ['01_executive_summary', '06_growth'],
            'active_section_id': '06_growth',
        }
        conversation = {
            'conversation_id': conversation_id,
            'user_id': user_id,
            'title': 'Research: AAPL',
            'metadata': {'research_state': research_state},
            'created_at': '2026-01-01T00:00:00Z',
            'updated_at': '2026-01-01T00:00:00Z',
        }

        event = create_mock_event(
            method='GET',
            path=f'/conversations/{conversation_id}',
            user_id=user_id,
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': conversation}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = get_conversation(event)

            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['metadata']['research_state']['ticker'] == 'AAPL'
            assert body['metadata']['research_state']['visible_sections'] == ['01_executive_summary', '06_growth']

    def test_get_conversation_access_denied(self):
        """Verify 403 when requesting user doesn't own the conversation."""
        owner_id = 'owner-123'
        requester_id = 'other-456'
        conversation_id = 'test-conv-123'

        conversation = {
            'conversation_id': conversation_id,
            'user_id': owner_id,
            'title': 'Private convo',
        }

        event = create_mock_event(
            method='GET',
            path=f'/conversations/{conversation_id}',
            user_id=requester_id,
            path_params={'conversation_id': conversation_id}
        )

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': conversation}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            response = get_conversation(event)
            assert response['statusCode'] == 403

    def test_get_conversation_not_found(self):
        """Verify 404 when conversation doesn't exist."""
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


# =============================================================================
# RUN TESTS DIRECTLY
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
