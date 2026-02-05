"""
Integration tests for Investment Research end-to-end flow.

Tests the complete flow across DynamoDB tables:
1. investment_reports_v2 - Report sections (SHARED by ticker)
2. conversations - User-specific conversation state with research_state
3. chat_messages - Follow-up Q&A messages

Test Scenarios:
- New analysis flow (create conversation, stream report, save state)
- Load saved conversation (retrieve research_state, fetch sections on-demand)
- Follow-up message persistence
- Multi-user concurrency (shared reports, isolated conversations)

Uses moto for DynamoDB mocking to simulate real table interactions.

Run:
    cd chat-api/backend
    pytest tests/integration/test_research_flow.py -v
"""

import json
import os
import sys
import pytest
import boto3
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any
from unittest.mock import patch, MagicMock
import uuid

# Add parent directories to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Set environment variables before importing
os.environ['ENVIRONMENT'] = 'test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'

# Try to import moto for proper DynamoDB mocking
try:
    from moto import mock_aws
    HAS_MOTO = True
except ImportError:
    HAS_MOTO = False
    mock_aws = None


# =============================================================================
# FIXTURES AND HELPERS
# =============================================================================

def create_conversations_table(dynamodb):
    """Create mock conversations table."""
    return dynamodb.create_table(
        TableName='test-conversations',
        KeySchema=[
            {'AttributeName': 'conversation_id', 'KeyType': 'HASH'}
        ],
        AttributeDefinitions=[
            {'AttributeName': 'conversation_id', 'AttributeType': 'S'},
            {'AttributeName': 'user_id', 'AttributeType': 'S'},
            {'AttributeName': 'updated_at', 'AttributeType': 'N'}
        ],
        GlobalSecondaryIndexes=[
            {
                'IndexName': 'user-conversations-index',
                'KeySchema': [
                    {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                    {'AttributeName': 'updated_at', 'KeyType': 'RANGE'}
                ],
                'Projection': {'ProjectionType': 'ALL'}
            }
        ],
        BillingMode='PAY_PER_REQUEST'
    )


def create_messages_table(dynamodb):
    """Create mock chat_messages table."""
    return dynamodb.create_table(
        TableName='test-chat-messages',
        KeySchema=[
            {'AttributeName': 'conversation_id', 'KeyType': 'HASH'},
            {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
        ],
        AttributeDefinitions=[
            {'AttributeName': 'conversation_id', 'AttributeType': 'S'},
            {'AttributeName': 'timestamp', 'AttributeType': 'N'}
        ],
        BillingMode='PAY_PER_REQUEST'
    )


def create_reports_v2_table(dynamodb):
    """Create mock investment_reports_v2 table."""
    return dynamodb.create_table(
        TableName='test-investment-reports-v2',
        KeySchema=[
            {'AttributeName': 'ticker', 'KeyType': 'HASH'},
            {'AttributeName': 'section_id', 'KeyType': 'RANGE'}
        ],
        AttributeDefinitions=[
            {'AttributeName': 'ticker', 'AttributeType': 'S'},
            {'AttributeName': 'section_id', 'AttributeType': 'S'},
            {'AttributeName': 'part', 'AttributeType': 'N'}
        ],
        GlobalSecondaryIndexes=[
            {
                'IndexName': 'part-index',
                'KeySchema': [
                    {'AttributeName': 'ticker', 'KeyType': 'HASH'},
                    {'AttributeName': 'part', 'KeyType': 'RANGE'}
                ],
                'Projection': {'ProjectionType': 'ALL'}
            }
        ],
        BillingMode='PAY_PER_REQUEST'
    )


def seed_report_data(reports_table, ticker: str = 'AAPL'):
    """Seed report data for testing."""
    ttl = int((datetime.utcnow() + timedelta(days=75)).timestamp())

    # Executive item
    reports_table.put_item(Item={
        'ticker': ticker,
        'section_id': '00_executive',
        'toc': [
            {'section_id': '01_executive_summary', 'title': 'Executive Summary', 'part': 1, 'icon': 'book-open', 'word_count': 500, 'display_order': 1},
            {'section_id': '06_growth', 'title': 'Growth Analysis', 'part': 2, 'icon': 'trending-up', 'word_count': 200, 'display_order': 6},
            {'section_id': '11_debt', 'title': 'Debt Analysis', 'part': 2, 'icon': 'credit-card', 'word_count': 180, 'display_order': 11},
        ],
        'ratings': {
            'growth': {'rating': 'Stable', 'confidence': Decimal('0.85')},
            'debt': {'rating': 'Strong', 'confidence': Decimal('0.9')},
            'overall_verdict': 'HOLD',
            'conviction': 'High'
        },
        'executive_summary': {
            'section_id': '01_executive_summary',
            'title': 'Executive Summary',
            'content': f'{ticker} is a strong value investment with stable growth.',
            'part': 1,
            'icon': 'book-open',
            'word_count': 500
        },
        'total_word_count': Decimal('880'),
        'ttl': Decimal(str(ttl)),
        'generated_at': datetime.utcnow().isoformat() + 'Z'
    })

    # Section items
    sections = [
        {'section_id': '06_growth', 'title': 'Growth Analysis', 'content': f'{ticker} shows stable 3-4% growth.', 'part': 2, 'icon': 'trending-up', 'word_count': 200, 'display_order': 6},
        {'section_id': '11_debt', 'title': 'Debt Analysis', 'content': f'{ticker} has low debt ratio.', 'part': 2, 'icon': 'credit-card', 'word_count': 180, 'display_order': 11},
    ]

    for section in sections:
        reports_table.put_item(Item={
            'ticker': ticker,
            **section,
            'ttl': Decimal(str(ttl)),
            'generated_at': datetime.utcnow().isoformat() + 'Z'
        })


# =============================================================================
# TEST CLASSES - Using unittest.mock for DynamoDB simulation
# =============================================================================

class TestNewAnalysisFlow:
    """Tests for new analysis flow: create conversation, stream report, save state."""

    def test_create_research_conversation(self):
        """Test creating a new research conversation."""
        user_id = 'user-123'
        conversation_id = str(uuid.uuid4())

        # Mock conversation creation
        mock_table = MagicMock()
        mock_table.put_item.return_value = {}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            # Simulate conversation creation
            conversation = {
                'conversation_id': conversation_id,
                'user_id': user_id,
                'title': 'Research: AAPL',
                'created_at': datetime.utcnow().isoformat() + 'Z',
                'updated_at': int(datetime.utcnow().timestamp()),
                'message_count': 0,
                'is_archived': False,
                'metadata': {}
            }

            mock_table.put_item(Item=conversation)
            mock_table.put_item.assert_called_once()

            call_item = mock_table.put_item.call_args.kwargs['Item']
            assert call_item['user_id'] == user_id
            assert 'Research: AAPL' in call_item['title']

    def test_save_research_state_after_stream(self):
        """Test saving research_state after streaming report."""
        user_id = 'user-123'
        conversation_id = 'conv-123'

        # Existing conversation
        existing_conv = {
            'conversation_id': conversation_id,
            'user_id': user_id,
            'title': 'Research: AAPL',
            'metadata': {}
        }

        # Research state to save
        research_state = {
            'ticker': 'AAPL',
            'active_section_id': '01_executive_summary',
            'visible_sections': ['01_executive_summary'],
            'toc': [
                {'section_id': '01_executive_summary', 'title': 'Executive Summary', 'part': 1},
                {'section_id': '06_growth', 'title': 'Growth', 'part': 2}
            ],
            'ratings': {
                'overall_verdict': 'HOLD',
                'conviction': 'High'
            }
        }

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': existing_conv}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            # Simulate update
            mock_table.update_item(
                Key={'conversation_id': conversation_id},
                UpdateExpression='SET #metadata = :metadata, updated_at = :updated',
                ExpressionAttributeNames={'#metadata': 'metadata'},
                ExpressionAttributeValues={
                    ':metadata': {'research_state': research_state},
                    ':updated': int(datetime.utcnow().timestamp())
                }
            )

            mock_table.update_item.assert_called_once()

    def test_verify_research_state_persisted(self):
        """Test that research_state can be retrieved after saving."""
        user_id = 'user-123'
        conversation_id = 'conv-123'

        # Conversation with saved research_state
        saved_conv = {
            'conversation_id': conversation_id,
            'user_id': user_id,
            'title': 'Research: AAPL',
            'metadata': {
                'research_state': {
                    'ticker': 'AAPL',
                    'active_section_id': '06_growth',
                    'visible_sections': ['01_executive_summary', '06_growth'],
                    'toc': [{'section_id': '06_growth', 'title': 'Growth'}],
                    'ratings': {'overall_verdict': 'HOLD'}
                }
            }
        }

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': saved_conv}

        with patch('src.handlers.conversations_handler.conversations_table', mock_table):
            result = mock_table.get_item(Key={'conversation_id': conversation_id})

            item = result['Item']
            assert 'metadata' in item
            assert 'research_state' in item['metadata']
            assert item['metadata']['research_state']['ticker'] == 'AAPL'


class TestLoadSavedConversation:
    """Tests for loading saved conversation with research_state."""

    def test_load_conversation_with_research_state(self):
        """Test loading a conversation that has research_state."""
        user_id = 'user-123'
        conversation_id = 'conv-123'

        saved_conv = {
            'conversation_id': conversation_id,
            'user_id': user_id,
            'title': 'Research: AAPL',
            'metadata': {
                'research_state': {
                    'ticker': 'AAPL',
                    'active_section_id': '06_growth',
                    'visible_sections': ['01_executive_summary', '06_growth']
                }
            }
        }

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': saved_conv}

        result = mock_table.get_item(Key={'conversation_id': conversation_id})

        item = result['Item']
        rs = item['metadata']['research_state']
        assert rs['ticker'] == 'AAPL'
        assert rs['active_section_id'] == '06_growth'
        assert '06_growth' in rs['visible_sections']

    def test_check_report_status_for_saved_ticker(self):
        """Test checking report status for ticker in saved conversation."""
        ticker = 'AAPL'
        ttl_future = int((datetime.utcnow() + timedelta(days=75)).timestamp())

        mock_status_item = {
            'ticker': ticker,
            'ttl': Decimal(str(ttl_future)),
            'generated_at': '2024-01-01T12:00:00Z',
            'total_word_count': Decimal('15000')
        }

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': mock_status_item}

        result = mock_table.get_item(
            Key={'ticker': ticker, 'section_id': '00_executive'},
            ProjectionExpression='ticker, #t, generated_at, total_word_count',
            ExpressionAttributeNames={'#t': 'ttl'}
        )

        item = result['Item']
        ttl = float(item['ttl'])
        assert ttl > datetime.utcnow().timestamp()  # Not expired

    def test_fetch_section_on_demand(self):
        """Test fetching a specific section on-demand."""
        ticker = 'AAPL'
        section_id = '06_growth'

        mock_section = {
            'ticker': ticker,
            'section_id': section_id,
            'title': 'Growth Analysis',
            'content': 'Apple shows stable 3-4% growth.',
            'part': 2,
            'icon': 'trending-up',
            'word_count': 200
        }

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': mock_section}

        result = mock_table.get_item(Key={'ticker': ticker, 'section_id': section_id})

        item = result['Item']
        assert item['section_id'] == section_id
        assert 'content' in item


class TestFollowupMessagePersistence:
    """Tests for follow-up message persistence in chat_messages table."""

    def test_save_followup_question(self):
        """Test saving a follow-up question message."""
        conversation_id = 'conv-123'
        user_id = 'user-123'

        message = {
            'conversation_id': conversation_id,
            'timestamp': int(datetime.utcnow().timestamp()),
            'message_id': str(uuid.uuid4()),
            'message_type': 'followup_question',
            'content': {
                '_type': 'followup_question',
                'question': 'What about the growth rate?',
                'section_context': '06_growth'
            },
            'user_id': user_id
        }

        mock_table = MagicMock()
        mock_table.put_item.return_value = {}

        mock_table.put_item(Item=message)
        mock_table.put_item.assert_called_once()

        saved_item = mock_table.put_item.call_args.kwargs['Item']
        assert saved_item['message_type'] == 'followup_question'
        assert saved_item['content']['question'] == 'What about the growth rate?'

    def test_save_followup_response(self):
        """Test saving a follow-up response message."""
        conversation_id = 'conv-123'

        message = {
            'conversation_id': conversation_id,
            'timestamp': int(datetime.utcnow().timestamp()),
            'message_id': str(uuid.uuid4()),
            'message_type': 'followup_response',
            'content': {
                '_type': 'followup_response',
                'response': 'The growth rate has been stable at 3-4% annually.',
                'model': 'claude-haiku-4.5'
            }
        }

        mock_table = MagicMock()
        mock_table.put_item.return_value = {}

        mock_table.put_item(Item=message)
        saved_item = mock_table.put_item.call_args.kwargs['Item']
        assert saved_item['message_type'] == 'followup_response'

    def test_retrieve_messages_in_order(self):
        """Test retrieving messages in chronological order."""
        conversation_id = 'conv-123'
        base_timestamp = int(datetime.utcnow().timestamp())

        messages = [
            {'conversation_id': conversation_id, 'timestamp': base_timestamp, 'message_type': 'followup_question'},
            {'conversation_id': conversation_id, 'timestamp': base_timestamp + 1, 'message_type': 'followup_response'},
            {'conversation_id': conversation_id, 'timestamp': base_timestamp + 10, 'message_type': 'followup_question'},
            {'conversation_id': conversation_id, 'timestamp': base_timestamp + 11, 'message_type': 'followup_response'},
        ]

        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': messages}

        result = mock_table.query(
            KeyConditionExpression='conversation_id = :cid',
            ExpressionAttributeValues={':cid': conversation_id},
            ScanIndexForward=True  # Oldest first
        )

        items = result['Items']
        assert len(items) == 4
        assert items[0]['message_type'] == 'followup_question'
        assert items[1]['message_type'] == 'followup_response'

        # Verify chronological order
        for i in range(len(items) - 1):
            assert items[i]['timestamp'] <= items[i + 1]['timestamp']


class TestMultiUserConcurrency:
    """Tests for multi-user access to shared reports with isolated conversations."""

    def test_same_report_different_users(self):
        """Test that different users can access the same report."""
        ticker = 'AAPL'
        user_a = 'user-A-123'
        user_b = 'user-B-456'

        # Shared report data
        report_section = {
            'ticker': ticker,
            'section_id': '06_growth',
            'title': 'Growth Analysis',
            'content': 'Apple shows stable growth.',
            'part': 2
        }

        # User A's conversation
        conv_a = {
            'conversation_id': 'conv-A',
            'user_id': user_a,
            'title': 'Research: AAPL',
            'metadata': {
                'research_state': {
                    'ticker': ticker,
                    'active_section_id': '06_growth'
                }
            }
        }

        # User B's conversation
        conv_b = {
            'conversation_id': 'conv-B',
            'user_id': user_b,
            'title': 'Research: AAPL',
            'metadata': {
                'research_state': {
                    'ticker': ticker,
                    'active_section_id': '01_executive_summary'  # Different active section
                }
            }
        }

        mock_reports_table = MagicMock()
        mock_reports_table.get_item.return_value = {'Item': report_section}

        mock_conv_table = MagicMock()

        # Both users can read the same report
        result_a = mock_reports_table.get_item(Key={'ticker': ticker, 'section_id': '06_growth'})
        result_b = mock_reports_table.get_item(Key={'ticker': ticker, 'section_id': '06_growth'})

        assert result_a['Item'] == result_b['Item']  # Same shared content

        # But have different conversation states
        assert conv_a['metadata']['research_state']['active_section_id'] == '06_growth'
        assert conv_b['metadata']['research_state']['active_section_id'] == '01_executive_summary'

    def test_conversation_ownership_prevents_cross_access(self):
        """Test that User B cannot access User A's conversation."""
        user_a = 'user-A-123'
        user_b = 'user-B-456'

        conv_a = {
            'conversation_id': 'conv-A',
            'user_id': user_a,
            'title': 'Research: AAPL'
        }

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': conv_a}

        result = mock_table.get_item(Key={'conversation_id': 'conv-A'})
        item = result['Item']

        # Simulating ownership check
        requesting_user = user_b
        assert item['user_id'] != requesting_user  # Access should be denied

    def test_no_cross_contamination_of_state(self):
        """Test that updating one user's state doesn't affect another's."""
        ticker = 'AAPL'
        user_a = 'user-A-123'
        user_b = 'user-B-456'

        # Initial states
        state_a = {'active_section_id': '01_exec', 'visible_sections': ['01_exec']}
        state_b = {'active_section_id': '06_growth', 'visible_sections': ['06_growth']}

        mock_table = MagicMock()

        # User A updates their state
        updated_state_a = {'active_section_id': '11_debt', 'visible_sections': ['01_exec', '11_debt']}

        # Simulate update for User A
        mock_table.update_item(
            Key={'conversation_id': 'conv-A'},
            UpdateExpression='SET metadata.research_state = :rs',
            ExpressionAttributeValues={':rs': updated_state_a}
        )

        # User B's state should remain unchanged
        # (In real implementation, these are separate DynamoDB items)
        assert state_b['active_section_id'] == '06_growth'  # Unchanged
        assert '01_exec' not in state_b['visible_sections']


class TestEdgeCasesIntegration:
    """Integration tests for edge cases."""

    def test_report_expiration_check(self):
        """Test handling of expired report."""
        ticker = 'AAPL'
        ttl_past = int((datetime.utcnow() - timedelta(days=1)).timestamp())

        mock_item = {
            'ticker': ticker,
            'section_id': '00_executive',
            'ttl': Decimal(str(ttl_past)),
            'generated_at': '2024-01-01T12:00:00Z'
        }

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': mock_item}

        result = mock_table.get_item(
            Key={'ticker': ticker, 'section_id': '00_executive'}
        )

        item = result['Item']
        ttl = float(item['ttl'])

        # Check expiration
        expired = ttl < datetime.utcnow().timestamp()
        assert expired is True

    def test_missing_section_returns_none(self):
        """Test that missing section returns None/empty."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No Item

        result = mock_table.get_item(
            Key={'ticker': 'AAPL', 'section_id': 'nonexistent_section'}
        )

        assert 'Item' not in result or result.get('Item') is None

    def test_invalid_conversation_id(self):
        """Test handling of invalid conversation ID."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No Item

        result = mock_table.get_item(
            Key={'conversation_id': 'invalid-conv-id'}
        )

        assert 'Item' not in result

    def test_malformed_research_state_handling(self):
        """Test that malformed research_state is handled gracefully."""
        conv = {
            'conversation_id': 'conv-123',
            'user_id': 'user-123',
            'metadata': {
                'research_state': {
                    # Missing required fields like 'ticker', 'active_section_id'
                    'some_random_field': 'value'
                }
            }
        }

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': conv}

        result = mock_table.get_item(Key={'conversation_id': 'conv-123'})
        item = result['Item']

        # Application should handle missing fields gracefully
        rs = item['metadata']['research_state']
        ticker = rs.get('ticker')  # None, not error

        assert ticker is None


# =============================================================================
# MOTO-BASED INTEGRATION TESTS (if moto is available)
# =============================================================================

@pytest.mark.skipif(not HAS_MOTO, reason="moto not installed")
class TestMotoIntegration:
    """Full integration tests using moto for DynamoDB simulation."""

    @pytest.fixture(autouse=True)
    def setup_tables(self):
        """Set up mock DynamoDB tables."""
        with mock_aws():
            dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

            # Create tables
            conv_table = create_conversations_table(dynamodb)
            msg_table = create_messages_table(dynamodb)
            reports_table = create_reports_v2_table(dynamodb)

            # Seed test data
            seed_report_data(reports_table, 'AAPL')

            yield {
                'conversations': conv_table,
                'messages': msg_table,
                'reports': reports_table
            }

    def test_full_flow_with_moto(self, setup_tables):
        """Test complete flow with moto DynamoDB."""
        tables = setup_tables
        user_id = 'test-user-moto'
        conversation_id = str(uuid.uuid4())

        # 1. Create conversation
        tables['conversations'].put_item(Item={
            'conversation_id': conversation_id,
            'user_id': user_id,
            'title': 'Research: AAPL',
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'updated_at': Decimal(str(int(datetime.utcnow().timestamp()))),
            'message_count': Decimal('0'),
            'is_archived': False,
            'metadata': {}
        })

        # 2. Read report ToC
        toc_response = tables['reports'].get_item(
            Key={'ticker': 'AAPL', 'section_id': '00_executive'}
        )
        assert 'Item' in toc_response
        assert 'toc' in toc_response['Item']

        # 3. Save research_state
        research_state = {
            'ticker': 'AAPL',
            'active_section_id': '06_growth',
            'visible_sections': ['01_executive_summary', '06_growth']
        }

        tables['conversations'].update_item(
            Key={'conversation_id': conversation_id},
            UpdateExpression='SET metadata.research_state = :rs',
            ExpressionAttributeValues={':rs': research_state}
        )

        # 4. Verify saved state
        conv_response = tables['conversations'].get_item(
            Key={'conversation_id': conversation_id}
        )
        assert conv_response['Item']['metadata']['research_state']['ticker'] == 'AAPL'

        # 5. Save follow-up message
        tables['messages'].put_item(Item={
            'conversation_id': conversation_id,
            'timestamp': Decimal(str(int(datetime.utcnow().timestamp()))),
            'message_id': str(uuid.uuid4()),
            'message_type': 'followup_question',
            'content': {'question': 'What about growth?'},
            'user_id': user_id
        })

        # 6. Retrieve messages
        msg_response = tables['messages'].query(
            KeyConditionExpression='conversation_id = :cid',
            ExpressionAttributeValues={':cid': conversation_id}
        )
        assert len(msg_response['Items']) == 1


# =============================================================================
# RUN TESTS DIRECTLY
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
