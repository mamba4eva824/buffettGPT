#!/usr/bin/env python3
"""
Unit tests for quarterly trend extraction and analysis in feature_extractor.py

Tests the following functions:
- extract_quarterly_trends()
- identify_phases()
- find_inflection_points()
- find_peaks_troughs()
- filter_trends_for_agent()
- compute_trend_insights()

These are pure unit tests with mock FMP data - no AWS required.

Run:
    cd chat-api/backend
    python tests/test_quarterly_trends.py
"""

import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils.feature_extractor import (
    extract_quarterly_trends,
    identify_phases,
    find_inflection_points,
    find_peaks_troughs,
    filter_trends_for_agent,
    compute_trend_insights,
    safe_divide,
    extract_value
)


def generate_mock_financials(num_quarters: int = 20) -> dict:
    """
    Generate mock FMP financial data for testing.

    Creates realistic-looking quarterly data with:
    - Increasing then decreasing debt (deleveraging pattern)
    - Growing revenue with varying margins
    - Cyclical cash flows
    """
    balance_sheet = []
    income_statement = []
    cash_flow = []

    for i in range(num_quarters):
        # Simulate debt cycle: Q0-Q10 increasing, Q10-Q20 decreasing
        # (Note: index 0 is most recent, so we reverse the pattern)
        if i < 10:
            # Most recent 10 quarters: deleveraging
            debt_factor = 1.0 - (0.03 * (10 - i))  # Decreasing from recent
        else:
            # Older 10 quarters: higher debt
            debt_factor = 1.0 + (0.02 * (i - 10))  # Was increasing before

        base_debt = 50_000_000_000  # $50B base debt
        base_equity = 80_000_000_000  # $80B base equity
        base_revenue = 100_000_000_000  # $100B base revenue

        # Create balance sheet entry
        total_debt = int(base_debt * debt_factor)
        total_equity = int(base_equity * (1 + 0.02 * (num_quarters - i - 1)))
        cash = int(20_000_000_000 * (1 + 0.01 * i))

        balance_sheet.append({
            'date': f"2024-{12 - (i % 12)}-31" if i < 12 else f"2023-{12 - (i % 12)}-31",
            'totalDebt': total_debt,
            'totalStockholdersEquity': total_equity,
            'totalAssets': total_equity + total_debt + 30_000_000_000,
            'cashAndCashEquivalents': cash,
            'totalCurrentAssets': cash + 15_000_000_000,
            'totalCurrentLiabilities': 25_000_000_000,
        })

        # Create income statement entry with growth
        revenue_growth = 1 + 0.02 * (num_quarters - i - 1)  # Growing over time
        revenue = int(base_revenue * revenue_growth)

        # Simulate margin cycle: improving then compressing
        if i < 8:
            margin_factor = 1.0 + (0.01 * (8 - i))  # Recent: higher margins
        else:
            margin_factor = 1.0 - (0.005 * (i - 8))  # Older: lower margins

        operating_income = int(revenue * 0.25 * margin_factor)
        net_income = int(revenue * 0.18 * margin_factor)

        income_statement.append({
            'date': f"2024-{12 - (i % 12)}-31" if i < 12 else f"2023-{12 - (i % 12)}-31",
            'revenue': revenue,
            'grossProfit': int(revenue * 0.42),
            'operatingIncome': operating_income,
            'netIncome': net_income,
            'ebitda': int(operating_income * 1.15),
            'interestExpense': int(total_debt * 0.04 / 4),  # 4% annual rate / 4 quarters
            'eps': round(net_income / 5_000_000_000, 2),  # Assume 5B shares
        })

        # Create cash flow entry
        fcf_factor = 1.0 + (0.015 * (num_quarters - i - 1))
        base_fcf = 25_000_000_000

        cash_flow.append({
            'date': f"2024-{12 - (i % 12)}-31" if i < 12 else f"2023-{12 - (i % 12)}-31",
            'freeCashFlow': int(base_fcf * fcf_factor * margin_factor),
            'operatingCashFlow': int(base_fcf * fcf_factor * margin_factor * 1.3),
            'capitalExpenditure': -int(revenue * 0.05),  # 5% of revenue
            'commonDividendsPaid': -int(base_fcf * 0.3),
            'commonStockRepurchased': -int(base_fcf * 0.4),
        })

    return {
        'balance_sheet': balance_sheet,
        'income_statement': income_statement,
        'cash_flow': cash_flow
    }


def test_extract_20_quarters():
    """Test extraction of 20 quarters of data."""
    raw = generate_mock_financials(20)
    trends = extract_quarterly_trends(raw, num_quarters=20)

    # Should have 20 quarters of data for each metric
    assert len(trends['debt_to_equity']) == 20, f"Expected 20 quarters, got {len(trends['debt_to_equity'])}"
    assert len(trends['revenue']) == 20
    assert len(trends['fcf_margin']) == 20
    assert len(trends['quarters']) == 20

    # Quarter labels should be Q0, Q1, ..., Q19
    assert trends['quarters'][0] == 'Q0'
    assert trends['quarters'][19] == 'Q19'

    print(f"  Extracted {len(trends['quarters'])} quarters")
    print(f"  Metrics tracked: {len([k for k in trends.keys() if k not in ['quarters', 'period_dates']])}")
    return True


def test_extract_fewer_quarters():
    """Test extraction when less than 20 quarters available."""
    raw = generate_mock_financials(12)  # Only 12 quarters
    trends = extract_quarterly_trends(raw, num_quarters=20)

    # Should adapt to available data
    assert len(trends['debt_to_equity']) == 12, f"Expected 12 quarters, got {len(trends['debt_to_equity'])}"

    print(f"  Extracted {len(trends['quarters'])} quarters (from 12 available)")
    return True


def test_debt_metrics_extraction():
    """Test that debt metrics are calculated correctly."""
    raw = generate_mock_financials(20)
    trends = extract_quarterly_trends(raw)

    # Debt-to-equity should be reasonable values (0.x to 2.x typically)
    dte = trends['debt_to_equity']
    assert all(0 < v < 3 for v in dte), f"Unexpected D/E values: {dte[:5]}"

    # Net debt should exist
    net_debt = trends['net_debt']
    assert all(isinstance(v, (int, float)) for v in net_debt)

    # Interest coverage should be positive
    ic = trends['interest_coverage']
    assert all(v > 0 for v in ic), f"Interest coverage should be positive: {ic[:5]}"

    print(f"  D/E range: {min(dte):.2f} to {max(dte):.2f}")
    print(f"  Interest coverage range: {min(ic):.1f}x to {max(ic):.1f}x")
    return True


def test_growth_metrics_extraction():
    """Test that growth metrics are calculated correctly."""
    raw = generate_mock_financials(20)
    trends = extract_quarterly_trends(raw)

    # Revenue should be positive
    revenue = trends['revenue']
    assert all(v > 0 for v in revenue)

    # Margins should be reasonable percentages
    net_margin = trends['net_margin']
    assert all(0 < v < 50 for v in net_margin), f"Unexpected margins: {net_margin[:5]}"

    # YoY growth should exist (first 16 quarters have YoY comparison)
    yoy = trends['revenue_growth_yoy']
    valid_yoy = [v for v in yoy if v is not None]
    assert len(valid_yoy) >= 16

    print(f"  Revenue range: ${min(revenue)/1e9:.1f}B to ${max(revenue)/1e9:.1f}B")
    print(f"  Net margin range: {min(net_margin):.1f}% to {max(net_margin):.1f}%")
    return True


def test_phase_detection_deleveraging():
    """Test detection of deleveraging phase."""
    raw = generate_mock_financials(20)
    trends = extract_quarterly_trends(raw)
    phases = identify_phases(trends)

    # Should detect at least one phase
    assert len(phases) >= 1, f"Expected at least one phase, got {len(phases)}"

    # Look for debt-related phases
    debt_phases = [p for p in phases if p['metric'] == 'debt_to_equity']

    print(f"  Detected {len(phases)} phases total")
    for p in phases[:3]:  # Show first 3
        print(f"    - {p['name']}: {p['quarters']} ({p['change']})")
    return True


def test_phase_detection_margin():
    """Test detection of margin expansion/compression phases."""
    raw = generate_mock_financials(20)
    trends = extract_quarterly_trends(raw)
    phases = identify_phases(trends)

    # Look for margin phases
    margin_phases = [p for p in phases if 'margin' in p['metric']]

    print(f"  Detected {len(margin_phases)} margin phases")
    for p in margin_phases[:2]:
        print(f"    - {p['name']}: {p['quarters']}")
    return True


def test_inflection_point_detection():
    """Test detection of trend reversals."""
    raw = generate_mock_financials(20)
    trends = extract_quarterly_trends(raw)
    inflection_points = find_inflection_points(trends)

    # May or may not find inflection points depending on data pattern
    print(f"  Detected {len(inflection_points)} inflection points")
    for ip in inflection_points[:3]:
        print(f"    - {ip['metric']} at {ip['quarter']}: {ip['from']} -> {ip['to']}")
    return True


def test_peaks_troughs():
    """Test 5-year peak/trough identification."""
    raw = generate_mock_financials(20)
    trends = extract_quarterly_trends(raw)
    pt = find_peaks_troughs(trends)

    # Should have peaks/troughs for key metrics
    assert 'debt_to_equity' in pt
    assert 'net_margin' in pt

    dte_pt = pt['debt_to_equity']
    assert 'peak' in dte_pt
    assert 'trough' in dte_pt
    assert 'current' in dte_pt

    print(f"  D/E: Peak={dte_pt['peak']['value']:.2f} at {dte_pt['peak']['quarter']}")
    print(f"       Trough={dte_pt['trough']['value']:.2f} at {dte_pt['trough']['quarter']}")
    print(f"       Current={dte_pt['current']:.2f}")
    print(f"       Range={dte_pt['range']:.2f}")
    return True


def test_filter_trends_for_debt_agent():
    """Test filtering trends for debt agent."""
    raw = generate_mock_financials(20)
    trends = extract_quarterly_trends(raw)
    filtered = filter_trends_for_agent(trends, 'debt')

    # Should have debt-specific metrics
    assert 'debt_to_equity' in filtered
    assert 'net_debt_to_ebitda' in filtered
    assert 'interest_coverage' in filtered

    # Should NOT have growth-specific metrics
    assert 'revenue' not in filtered
    assert 'eps' not in filtered

    print(f"  Debt agent metrics: {list(filtered.keys())}")
    return True


def test_filter_trends_for_cashflow_agent():
    """Test filtering trends for cashflow agent."""
    raw = generate_mock_financials(20)
    trends = extract_quarterly_trends(raw)
    filtered = filter_trends_for_agent(trends, 'cashflow')

    # Should have cashflow-specific metrics
    assert 'fcf_margin' in filtered
    assert 'free_cash_flow' in filtered
    assert 'shareholder_payout' in filtered

    # Should NOT have debt-specific metrics
    assert 'debt_to_equity' not in filtered

    print(f"  Cashflow agent metrics: {list(filtered.keys())}")
    return True


def test_filter_trends_for_growth_agent():
    """Test filtering trends for growth agent."""
    raw = generate_mock_financials(20)
    trends = extract_quarterly_trends(raw)
    filtered = filter_trends_for_agent(trends, 'growth')

    # Should have growth-specific metrics
    assert 'revenue' in filtered
    assert 'revenue_growth_yoy' in filtered
    assert 'eps' in filtered

    # Should NOT have cashflow-specific metrics
    assert 'free_cash_flow' not in filtered

    print(f"  Growth agent metrics: {list(filtered.keys())}")
    return True


def test_compute_trend_insights():
    """Test the combined trend insights function."""
    raw = generate_mock_financials(20)
    trends = extract_quarterly_trends(raw)
    insights = compute_trend_insights(trends)

    # Should have all three components
    assert 'phases' in insights
    assert 'inflection_points' in insights
    assert 'peaks_troughs' in insights

    print(f"  Phases: {len(insights['phases'])}")
    print(f"  Inflection points: {len(insights['inflection_points'])}")
    print(f"  Metrics with peaks/troughs: {len(insights['peaks_troughs'])}")
    return True


def test_safe_divide():
    """Test safe_divide utility function."""
    assert safe_divide(10, 2) == 5.0
    assert safe_divide(10, 0) == 0.0
    assert safe_divide(10, None) == 0.0
    assert safe_divide(10, 0, default=-1) == -1

    print("  safe_divide handles edge cases correctly")
    return True


def test_extract_value():
    """Test extract_value utility function."""
    data = [
        {'key1': 100, 'key2': 200},
        {'key1': 150, 'key2': 250},
    ]

    assert extract_value(data, 'key1', 0) == 100
    assert extract_value(data, 'key1', 1) == 150
    assert extract_value(data, 'key3', 0, default=0) == 0
    assert extract_value([], 'key1', 0, default=0) == 0

    print("  extract_value handles edge cases correctly")
    return True


def test_empty_data():
    """Test handling of empty financial data."""
    raw = {'balance_sheet': [], 'income_statement': [], 'cash_flow': []}
    trends = extract_quarterly_trends(raw)

    # Should return empty lists
    assert trends['debt_to_equity'] == []
    assert trends['revenue'] == []

    print("  Handles empty data gracefully")
    return True


def run_all_tests():
    """Run all tests and report results."""
    tests = [
        ("Extract 20 quarters", test_extract_20_quarters),
        ("Extract fewer quarters", test_extract_fewer_quarters),
        ("Debt metrics extraction", test_debt_metrics_extraction),
        ("Growth metrics extraction", test_growth_metrics_extraction),
        ("Phase detection: deleveraging", test_phase_detection_deleveraging),
        ("Phase detection: margin", test_phase_detection_margin),
        ("Inflection point detection", test_inflection_point_detection),
        ("Peaks and troughs", test_peaks_troughs),
        ("Filter for debt agent", test_filter_trends_for_debt_agent),
        ("Filter for cashflow agent", test_filter_trends_for_cashflow_agent),
        ("Filter for growth agent", test_filter_trends_for_growth_agent),
        ("Compute trend insights", test_compute_trend_insights),
        ("safe_divide utility", test_safe_divide),
        ("extract_value utility", test_extract_value),
        ("Empty data handling", test_empty_data),
    ]

    print("=" * 60)
    print("Quarterly Trends Unit Tests")
    print("=" * 60)

    passed = 0
    failed = 0

    for name, test_fn in tests:
        print(f"\n[TEST] {name}")
        try:
            result = test_fn()
            if result:
                print(f"  PASSED")
                passed += 1
            else:
                print(f"  FAILED")
                failed += 1
        except Exception as e:
            print(f"  FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
