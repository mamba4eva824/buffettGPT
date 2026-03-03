"""
Data seeding utilities for integration and E2E tests.

Provides functions to seed and clean up test data in DynamoDB tables.
Use unique ticker prefixes (e.g., 'E2EXXXX', 'INTXXXX') for data isolation.

Usage:
    from tests.fixtures.data_seeding import (
        seed_test_report,
        seed_test_metrics,
        seed_token_usage,
        cleanup_test_data,
        cleanup_messages,
    )
"""

import boto3
from datetime import datetime
from decimal import Decimal


def seed_test_report(ticker: str, environment: str = 'dev') -> dict:
    """
    Seed investment-reports-v2 table with test sections.

    Seeds 3 sections: 00_executive, 06_growth, 11_debt.

    Args:
        ticker: Stock ticker (use unique prefix like 'E2EXXXX')
        environment: Target environment ('dev', 'test')

    Returns:
        Dict with seeded ticker and section IDs
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table(f'investment-reports-v2-{environment}')

    sections = {
        '00_executive': {
            'ticker': ticker,
            'section_id': '00_executive',
            'company_name': f'Test Company {ticker}',
            'ratings': {
                'growth': 'Strong',
                'profitability': 'Exceptional',
                'cashflow': 'Strong',
                'debt': 'Moderate',
                'valuation': 'Fair',
                'overall_verdict': 'BUY',
                'conviction': 'High'
            },
            'generated_at': datetime.now().isoformat()
        },
        '06_growth': {
            'ticker': ticker,
            'section_id': '06_growth',
            'title': 'Growth Analysis',
            'content': f'{ticker} has demonstrated consistent revenue growth of 15% YoY...',
            'word_count': 450
        },
        '11_debt': {
            'ticker': ticker,
            'section_id': '11_debt',
            'title': 'Debt Analysis',
            'content': f'{ticker} maintains a debt-to-equity ratio of 0.45...',
            'word_count': 380
        }
    }

    for section_id, data in sections.items():
        table.put_item(Item=data)

    return {'ticker': ticker, 'sections': list(sections.keys())}


def seed_test_metrics(ticker: str, quarters: int = 8, environment: str = 'dev',
                      include_earnings: bool = True, include_dividends: bool = True) -> dict:
    """
    Seed metrics-history-cache table with quarterly data using nested-category schema.

    Uses the same embedded-category structure as production: each item has
    category maps (revenue_profit, cashflow, etc.) rather than flat metric keys.

    Args:
        ticker: Stock ticker
        quarters: Number of quarters to seed
        environment: Target environment
        include_earnings: Whether to include earnings_events category
        include_dividends: Whether to include dividend category

    Returns:
        Dict with seeded ticker and fiscal dates
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table(f'metrics-history-{environment}')

    fiscal_dates = []
    base_revenue = 50000000000  # $50B

    # Map quarter number to month for ISO date format
    quarter_end_months = {1: '03-31', 2: '06-30', 3: '09-30', 4: '12-31'}
    quarter_labels = {1: 'Q1', 2: 'Q2', 3: 'Q3', 4: 'Q4'}

    for q in range(quarters):
        year = 2025 - (q // 4)
        quarter_num = 4 - (q % 4)
        fiscal_date = f'{year}-{quarter_end_months[quarter_num]}'
        fiscal_dates.append(fiscal_date)

        revenue = int(base_revenue * (1 + 0.03 * q))
        net_income = int(base_revenue * 0.2 * (1 + 0.02 * q))
        fcf = int(base_revenue * 0.15 * (1 + 0.025 * q))

        item = {
            'ticker': ticker,
            'fiscal_date': fiscal_date,
            'fiscal_year': year,
            'fiscal_quarter': quarter_labels[quarter_num],
            'currency': 'USD',
            'revenue_profit': {
                'revenue': revenue,
                'net_income': net_income,
                'eps': Decimal(str(round(net_income / 15000000000, 2))),
                'gross_margin': Decimal('0.45'),
                'operating_margin': Decimal('0.30'),
                'net_margin': Decimal(str(round(net_income / revenue, 4))),
            },
            'cashflow': {
                'free_cash_flow': fcf,
                'operating_cash_flow': int(fcf * 1.3),
                'fcf_margin': Decimal(str(round(fcf / revenue, 4))),
                'dividends_paid': int(base_revenue * 0.02),
            },
            'balance_sheet': {
                'total_debt': int(base_revenue * 0.3),
                'total_equity': int(base_revenue * 0.6),
                'cash_position': int(base_revenue * 0.15),
                'net_debt': int(base_revenue * 0.15),
            },
            'debt_leverage': {
                'debt_to_equity': Decimal('0.5'),
                'interest_coverage': Decimal('15.0'),
                'current_ratio': Decimal('1.2'),
            },
            'earnings_quality': {
                'gaap_net_income': net_income,
                'adjusted_earnings': int(net_income * 1.05),
                'sbc_to_revenue_pct': Decimal('3.5'),
            },
            'dilution': {
                'diluted_shares': 15000000000,
                'dilution_pct': Decimal('0.3'),
            },
            'valuation': {
                'roe': Decimal('0.35'),
                'roic': Decimal('0.28'),
                'roa': Decimal('0.18'),
            },
        }

        # Add earnings_events category
        if include_earnings:
            # Earnings report ~30 days after quarter end
            earn_month = int(fiscal_date[5:7]) + 1
            earn_year = year
            if earn_month > 12:
                earn_month = 1
                earn_year += 1
            item['earnings_events'] = {
                'earnings_date': f'{earn_year}-{earn_month:02d}-28',
                'eps_actual': Decimal(str(round(net_income / 15000000000, 2))),
                'eps_estimated': Decimal(str(round(net_income / 15000000000 * 0.97, 2))),
                'eps_surprise_pct': Decimal('3.1'),
                'eps_beat': True,
                'revenue_actual': revenue,
                'revenue_estimated': int(revenue * 0.99),
                'revenue_surprise_pct': Decimal('1.0'),
            }

        # Add dividend category
        if include_dividends:
            item['dividend'] = {
                'dps': Decimal('0.25'),
                'payments_in_quarter': 1,
                'frequency': 'Quarterly',
                'dividend_yield': Decimal('0.6'),
                'annualized_dps': Decimal('1.0'),
            }

        table.put_item(Item=item)

    return {'ticker': ticker, 'fiscal_dates': fiscal_dates}


def seed_token_usage(user_id: str, total_tokens: int, limit: int = 50000,
                     environment: str = 'dev') -> dict:
    """
    Seed token usage for testing limit scenarios.

    Args:
        user_id: User identifier
        total_tokens: Current usage to set
        limit: Token limit to set
        environment: Target environment

    Returns:
        Dict with seeded usage data
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table(f'token-usage-{environment}-buffett')

    now = datetime.now()
    # billing_period uses YYYY-MM-DD format (anniversary-based, keyed to current day)
    billing_day = now.day
    billing_period = now.strftime(f'%Y-%m-{billing_day:02d}')

    table.put_item(Item={
        'user_id': user_id,
        'billing_period': billing_period,
        'billing_day': billing_day,
        'total_tokens': total_tokens,
        'token_limit': limit,
        'input_tokens': int(total_tokens * 0.7),
        'output_tokens': int(total_tokens * 0.3),
        'request_count': total_tokens // 500 if total_tokens > 0 else 0
    })

    return {
        'user_id': user_id,
        'billing_period': billing_period,
        'total_tokens': total_tokens,
        'remaining': limit - total_tokens
    }


def cleanup_test_data(ticker: str, user_id: str = None, environment: str = 'dev') -> None:
    """
    Remove test data after integration/E2E tests.

    Args:
        ticker: Stock ticker to clean up
        user_id: Optional user ID to clean up token usage
        environment: Target environment
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

    # Clean reports
    reports_table = dynamodb.Table(f'investment-reports-v2-{environment}')
    response = reports_table.query(
        KeyConditionExpression='ticker = :t',
        ExpressionAttributeValues={':t': ticker}
    )
    for item in response.get('Items', []):
        reports_table.delete_item(Key={
            'ticker': item['ticker'],
            'section_id': item['section_id']
        })

    # Clean metrics
    metrics_table = dynamodb.Table(f'metrics-history-{environment}')
    response = metrics_table.query(
        KeyConditionExpression='ticker = :t',
        ExpressionAttributeValues={':t': ticker}
    )
    for item in response.get('Items', []):
        metrics_table.delete_item(Key={
            'ticker': item['ticker'],
            'fiscal_date': item['fiscal_date']
        })

    # Clean token usage if user_id provided
    if user_id:
        token_table = dynamodb.Table(f'token-usage-{environment}-buffett')
        # Query all billing periods for this user and delete them
        response = token_table.query(
            KeyConditionExpression='user_id = :uid',
            ExpressionAttributeValues={':uid': user_id}
        )
        for item in response.get('Items', []):
            token_table.delete_item(Key={
                'user_id': item['user_id'],
                'billing_period': item['billing_period']
            })


def cleanup_messages(session_ids: list, environment: str = 'dev') -> None:
    """
    Remove chat messages for given session IDs.

    Args:
        session_ids: List of conversation_id values to clean up
        environment: Target environment
    """
    if not session_ids:
        return

    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    prefix = 'buffett' if environment == 'dev' else f'buffett-{environment}'
    table = dynamodb.Table(f'{prefix}-{environment}-chat-messages')

    for sid in session_ids:
        response = table.query(
            KeyConditionExpression='conversation_id = :sid',
            ExpressionAttributeValues={':sid': sid},
        )
        for item in response.get('Items', []):
            table.delete_item(Key={
                'conversation_id': item['conversation_id'],
                'timestamp': item['timestamp'],
            })
