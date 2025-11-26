#!/usr/bin/env python3
"""
v3.6.5 Multi-Quarter Inference Pipeline with Bootstrap CI
==========================================================

Runs v3.6.5 production models on all quarters with Bootstrap CI.

v3.6.5 Model Improvements:
- Debt: 58 features (+ ROA, ROIC, DuPont components, debt coverage)
- Cashflow: 42 features (+ OCF efficiency, capex intensity, working capital)
- Growth: 63 features (+ margin trends, earnings stability, operating leverage)

Key Differences from v3.5:
- Uses v3.6.5 hyperparameters (min_child_weight=5, gamma=0.1)
- Expanded feature set with Buffett-core metrics
- Trained on 1,467 samples from 55 companies

Author: Claude Code
Date: 2025-11-25
Version: v3.6.5
"""

import os
import pickle
import json
import pandas as pd
import numpy as np
from pathlib import Path
import sys
from sklearn.utils import resample
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
import requests
from datetime import datetime
from dotenv import load_dotenv

# Get project root
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

# Load environment variables from .env file
load_dotenv(PROJECT_ROOT / '.env')

# Add paths for imports
sys.path.insert(0, str(PROJECT_ROOT / 'scripts' / 'v3.5'))
from extract_v35_features import (
    safe_divide,
    prepare_fmp_data,
    extract_debt_features_v35,
    extract_cashflow_features_v35,
    extract_growth_features_v361
)

# FMP API Key
FMP_API_KEY = os.getenv('FMP_API_KEY', '')


def fetch_quarterly_data(ticker, statement_type, quarters=20):
    """Fetch quarterly financial data from FMP stable API."""
    # Use stable endpoint (more reliable)
    url = f"https://financialmodelingprep.com/stable/{statement_type}"
    params = {'symbol': ticker, 'period': 'quarter', 'limit': quarters, 'apikey': FMP_API_KEY}
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def add_v365_debt_features(df):
    """
    Add v3.6.5 new Debt features (ROA, ROIC, DuPont, debt coverage).

    Adds 10 new features to base debt features.
    """
    df = df.sort_values(['symbol', 'date']).reset_index(drop=True)

    # Get raw values
    net_income = df.get('net_income', df.get('netIncome', 0))
    total_assets = df.get('total_assets', df.get('totalAssets', 0))
    total_equity = df.get('total_equity', df.get('totalStockholdersEquity', 0))
    total_debt = df.get('total_debt', df.get('totalDebt', 0))
    operating_income = df.get('operating_income', df.get('operatingIncome', 0))
    revenue = df.get('revenue', 0)
    free_cash_flow = df.get('free_cash_flow', df.get('freeCashFlow', 0))
    ebitda = df.get('ebitda', 0)
    interest_expense = df.get('interest_expense', df.get('interestExpense', 0))

    # ROA and ROIC
    df['roa'] = safe_divide(net_income, total_assets) * 100
    nopat = operating_income * (1 - 0.25)  # Assume 25% tax rate
    invested_capital = total_equity + total_debt
    df['roic'] = safe_divide(nopat, invested_capital) * 100

    # Temporal ROA/ROIC features
    df['roa_yoy'] = df.groupby('symbol')['roa'].pct_change(periods=4) * 100
    df['roa_trend_2yr'] = df.groupby('symbol')['roa'].diff(periods=8)
    df['roic_yoy'] = df.groupby('symbol')['roic'].pct_change(periods=4) * 100

    # DuPont components
    df['asset_turnover'] = safe_divide(revenue, total_assets)
    df['asset_turnover_yoy'] = df.groupby('symbol')['asset_turnover'].pct_change(periods=4) * 100
    df['equity_multiplier'] = safe_divide(total_assets, total_equity)

    # Debt coverage ratios
    df['fcf_to_debt'] = safe_divide(free_cash_flow, total_debt)
    df['ebitda_to_interest'] = safe_divide(ebitda, interest_expense)

    return df


def add_v365_cashflow_features(df):
    """
    Add v3.6.5 new Cashflow features (efficiency, capex intensity, working capital).

    Adds 7 new features to base cashflow features.
    """
    df = df.sort_values(['symbol', 'date']).reset_index(drop=True)

    operating_cash_flow = df.get('operating_cash_flow', df.get('operatingCashFlow', 0))
    revenue = df.get('revenue', 0)
    free_cash_flow = df.get('free_cash_flow', df.get('freeCashFlow', 0))
    capital_expenditures = df.get('capital_expenditures', df.get('capitalExpenditure', 0))
    cost_of_revenue = df.get('cost_of_revenue', df.get('costOfRevenue', 0))
    inventory = df.get('inventory', 0)
    current_assets = df.get('current_assets', df.get('totalCurrentAssets', 0))
    current_liabilities = df.get('current_liabilities', df.get('totalCurrentLiabilities', 0))

    # Cash efficiency
    df['ocf_to_revenue'] = safe_divide(operating_cash_flow, revenue) * 100
    df['ocf_to_revenue_yoy'] = df.groupby('symbol')['ocf_to_revenue'].pct_change(periods=4) * 100
    df['fcf_to_revenue'] = safe_divide(free_cash_flow, revenue) * 100

    # Capital intensity
    capex_abs = capital_expenditures.abs() if hasattr(capital_expenditures, 'abs') else abs(capital_expenditures)
    df['capex_intensity'] = safe_divide(capex_abs, revenue) * 100
    df['capex_intensity_trend'] = df.groupby('symbol')['capex_intensity'].diff(periods=4)

    # Working capital detail
    cost_denom = cost_of_revenue if isinstance(cost_of_revenue, pd.Series) and cost_of_revenue.sum() != 0 else revenue
    df['dio'] = safe_divide(inventory, cost_denom) * 365
    df['working_capital_to_revenue'] = safe_divide(current_assets - current_liabilities, revenue)

    return df


def add_v365_growth_features(df):
    """
    Add v3.6.5 new Growth features (long-term trends, earnings quality, leverage).

    Adds 6 new features to v3.6.1 growth features.
    """
    df = df.sort_values(['symbol', 'date']).reset_index(drop=True)

    gross_profit = df.get('gross_profit', df.get('grossProfit', 0))
    revenue = df.get('revenue', 0)
    operating_income = df.get('operating_income', df.get('operatingIncome', 0))
    net_income = df.get('net_income', df.get('netIncome', 0))
    total_assets = df.get('total_assets', df.get('totalAssets', 0))
    total_equity = df.get('total_equity', df.get('totalStockholdersEquity', 0))

    # Calculate margins if not present
    if 'gross_margin' not in df.columns:
        df['gross_margin'] = safe_divide(gross_profit, revenue) * 100
    if 'operating_margin' not in df.columns:
        df['operating_margin'] = safe_divide(operating_income, revenue) * 100
    if 'net_margin' not in df.columns:
        df['net_margin'] = safe_divide(net_income, revenue) * 100

    # Long-term margin trends (2-year)
    df['gross_margin_trend_2yr'] = df.groupby('symbol')['gross_margin'].diff(periods=8)
    df['operating_margin_trend_2yr'] = df.groupby('symbol')['operating_margin'].diff(periods=8)
    df['net_margin_trend_2yr'] = df.groupby('symbol')['net_margin'].diff(periods=8)

    # Earnings quality - ROE decomposed (DuPont)
    df['roe_decomposed'] = (
        safe_divide(net_income, revenue) *
        safe_divide(revenue, total_assets) *
        safe_divide(total_assets, total_equity)
    )

    # Earnings stability (coefficient of variation over 8 quarters)
    rolling_std = df.groupby('symbol')['net_income'].rolling(8, min_periods=4).std()
    rolling_mean = df.groupby('symbol')['net_income'].rolling(8, min_periods=4).mean().abs()
    df['earnings_stability'] = (rolling_std / rolling_mean).reset_index(level=0, drop=True)

    # Operating leverage (% change in EBIT / % change in revenue)
    ebit_pct = df.groupby('symbol')['operating_income'].pct_change(periods=4)
    rev_pct = df.groupby('symbol')['revenue'].pct_change(periods=4)
    df['operating_leverage'] = safe_divide(ebit_pct, rev_pct)

    return df


def extract_v365_features(balance_data, income_data, cashflow_data, ticker, company_name):
    """
    Extract all v3.6.5 features from FMP API data.

    Total features: 58 debt + 42 cashflow + 63 growth = 163 (with some overlap)

    Returns:
        Tuple of (debt_df, cashflow_df, growth_df) each with features + metadata
    """
    # Prepare raw data
    df = prepare_fmp_data(balance_data, income_data, cashflow_data, ticker, company_name)

    # Extract base features (v3.5/v3.6.1)
    debt_features = extract_debt_features_v35(df)
    cashflow_features = extract_cashflow_features_v35(df)
    growth_features = extract_growth_features_v361(df)

    # Add metadata columns
    for features_df in [debt_features, cashflow_features, growth_features]:
        features_df['symbol'] = df['symbol'].values
        features_df['date'] = df['date'].values
        features_df['company'] = df['company'].values

    # Add raw columns needed for v3.6.5 new features
    raw_cols_to_add = {
        'operating_cash_flow': 'operatingCashFlow',
        'free_cash_flow': 'freeCashFlow',
        'net_income': 'netIncome',
        'revenue': 'revenue',
        'capital_expenditures': 'capitalExpenditure',
        'gross_profit': 'grossProfit',
        'eps': 'eps',
        'gross_margin': None,  # calculated
        'net_margin': None,  # calculated
        'cost_of_revenue': 'costOfRevenue',
        'total_debt': 'totalDebt',
        'total_equity': 'totalStockholdersEquity',
        'total_assets': 'totalAssets',
        'cash': 'cashAndCashEquivalents',
        'interest_expense': 'interestExpense',
        'operating_income': 'operatingIncome',
        'ebitda': 'ebitda',
        'current_assets': 'totalCurrentAssets',
        'current_liabilities': 'totalCurrentLiabilities',
        'inventory': 'inventory',
    }

    # Add raw columns to all feature dataframes
    for feature_name, raw_name in raw_cols_to_add.items():
        if raw_name and raw_name in df.columns:
            for features_df in [debt_features, cashflow_features, growth_features]:
                if feature_name not in features_df.columns:
                    features_df[feature_name] = df[raw_name].values

    # Calculate margins - add to ALL feature dataframes (v3.6.5 models trained with merged data)
    gross_margin_vals = safe_divide(df['grossProfit'], df['revenue']) * 100
    net_margin_vals = safe_divide(df['netIncome'], df['revenue']) * 100
    operating_margin_vals = safe_divide(df['operatingIncome'], df['revenue']) * 100
    eps_to_revenue_vals = safe_divide(df['eps'], df['revenue'] / 1e9)
    cost_efficiency_vals = safe_divide(df['costOfRevenue'], df['revenue']) * 100

    for features_df in [debt_features, cashflow_features, growth_features]:
        if 'gross_margin' not in features_df.columns:
            features_df['gross_margin'] = gross_margin_vals.values
        if 'net_margin' not in features_df.columns:
            features_df['net_margin'] = net_margin_vals.values
        if 'operating_margin' not in features_df.columns:
            features_df['operating_margin'] = operating_margin_vals.values
        if 'eps_to_revenue' not in features_df.columns:
            features_df['eps_to_revenue'] = eps_to_revenue_vals.values
        if 'cost_efficiency' not in features_df.columns:
            features_df['cost_efficiency'] = cost_efficiency_vals.values

    # Add v3.6.5 specific features
    debt_features = add_v365_debt_features(debt_features)
    cashflow_features = add_v365_cashflow_features(cashflow_features)
    growth_features = add_v365_growth_features(growth_features)

    # Add year columns (handling potential merge issues)
    for features_df in [debt_features, cashflow_features, growth_features]:
        features_df['year_x'] = pd.to_datetime(features_df['date']).dt.year
        features_df['year_y'] = pd.to_datetime(features_df['date']).dt.year

    # Sort by date (newest first)
    debt_features = debt_features.sort_values('date', ascending=False).reset_index(drop=True)
    cashflow_features = cashflow_features.sort_values('date', ascending=False).reset_index(drop=True)
    growth_features = growth_features.sort_values('date', ascending=False).reset_index(drop=True)

    return debt_features, cashflow_features, growth_features


def bootstrap_ci_v365(features_df, model, scaler, feature_cols, continuous_cols,
                      binary_cols, df_train, n_iterations=50):
    """
    Calculate Bootstrap CI using company-level resampling.

    Trains bootstrap models on resampled training data and predicts on test features.

    Args:
        features_df: DataFrame with features for inference
        model: Production model (for reference)
        scaler: Production scaler (for reference)
        feature_cols: List of feature columns
        continuous_cols: List of continuous features to scale
        binary_cols: List of binary features (not scaled)
        df_train: Training data for bootstrap resampling
        n_iterations: Number of bootstrap iterations

    Returns:
        dict with CI results for each quarter
    """
    n_quarters = len(features_df)
    bootstrap_probas = np.zeros((n_iterations, n_quarters, 3))

    # v3.6.5 XGBoost hyperparameters
    xgb_params = {
        'objective': 'multi:softprob',
        'num_class': 3,
        'max_depth': 3,
        'learning_rate': 0.03,
        'n_estimators': 250,
        'subsample': 0.7,
        'colsample_bytree': 0.7,
        'min_child_weight': 5,
        'gamma': 0.1,
        'reg_alpha': 0.1,
        'reg_lambda': 1.0,
        'verbosity': 0
    }

    for i in range(n_iterations):
        # Resample companies with replacement
        unique_companies = df_train['symbol'].unique()
        resampled_companies = resample(
            unique_companies, n_samples=len(unique_companies),
            replace=True, random_state=i
        )

        # Collect all quarters for resampled companies
        resampled_data = []
        for company in resampled_companies:
            company_data = df_train[df_train['symbol'] == company].copy()
            resampled_data.append(company_data)
        df_bootstrap = pd.concat(resampled_data, ignore_index=True)

        # Prepare training data
        X_train = df_bootstrap[feature_cols].copy()
        y_train = df_bootstrap['label'].values

        # Scale continuous features
        boot_scaler = StandardScaler()
        if continuous_cols:
            X_train[continuous_cols] = boot_scaler.fit_transform(X_train[continuous_cols])

        # Train bootstrap model
        boot_model = xgb.XGBClassifier(**xgb_params, random_state=i)
        boot_model.fit(X_train, y_train, verbose=False)

        # Prepare test data
        X_test = features_df[feature_cols].copy()
        if continuous_cols:
            X_test[continuous_cols] = boot_scaler.transform(X_test[continuous_cols])

        # Predict
        bootstrap_probas[i] = boot_model.predict_proba(X_test)

    # Calculate CI for each quarter
    results = {}
    for q_idx in range(n_quarters):
        quarter_probas = bootstrap_probas[:, q_idx, :]
        point_estimate = np.mean(quarter_probas, axis=0)
        ci_lower = np.percentile(quarter_probas, 2.5, axis=0)
        ci_upper = np.percentile(quarter_probas, 97.5, axis=0)
        ci_width = ci_upper - ci_lower

        results[q_idx] = {
            'point_estimate': point_estimate,
            'ci_lower': ci_lower,
            'ci_upper': ci_upper,
            'ci_width': ci_width
        }

    return results


def run_v365_inference(ticker, company_name, n_bootstrap=50):
    """
    Run complete v3.6.5 inference pipeline with Bootstrap CI.

    Args:
        ticker: Stock ticker
        company_name: Company name
        n_bootstrap: Number of bootstrap iterations

    Returns:
        dict with all predictions and CI data
    """
    print(f"\n{'='*80}")
    print(f"v3.6.5 Inference Pipeline: {company_name} ({ticker})")
    print(f"{'='*80}")

    # Paths
    models_dir = PROJECT_ROOT / 'models' / 'v3.6.5_lifecycle'
    training_data_dir = PROJECT_ROOT / 'data' / 'v3.6.5_expanded_hold'
    output_dir = PROJECT_ROOT / 'data' / 'inference' / 'v3.6.5' / company_name
    output_dir.mkdir(parents=True, exist_ok=True)

    docs_dir = PROJECT_ROOT / 'docs' / 'inference' / 'v3.6.5' / company_name
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Fetch data from FMP API
    print("\n[1/6] Fetching data from FMP API...")
    try:
        balance_data = fetch_quarterly_data(ticker, 'balance-sheet-statement', quarters=20)
        income_data = fetch_quarterly_data(ticker, 'income-statement', quarters=20)
        cashflow_data = fetch_quarterly_data(ticker, 'cash-flow-statement', quarters=20)
        print(f"      Fetched {len(balance_data)} quarters")
    except Exception as e:
        print(f"      ERROR: {e}")
        return None

    # Step 2: Extract v3.6.5 features
    print("\n[2/6] Extracting v3.6.5 features...")
    try:
        debt_features, cashflow_features, growth_features = extract_v365_features(
            balance_data, income_data, cashflow_data, ticker, company_name
        )
        print(f"      Debt: {len(debt_features)} quarters, {len([c for c in debt_features.columns if c not in ['symbol', 'date', 'company']])} features")
        print(f"      Cashflow: {len(cashflow_features)} quarters, {len([c for c in cashflow_features.columns if c not in ['symbol', 'date', 'company']])} features")
        print(f"      Growth: {len(growth_features)} quarters, {len([c for c in growth_features.columns if c not in ['symbol', 'date', 'company']])} features")

        # Save features
        debt_features.to_csv(output_dir / f'{ticker}_debt_features.csv', index=False)
        cashflow_features.to_csv(output_dir / f'{ticker}_cashflow_features.csv', index=False)
        growth_features.to_csv(output_dir / f'{ticker}_growth_features.csv', index=False)
    except Exception as e:
        print(f"      ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None

    # Step 3: Load v3.6.5 models and training data
    print("\n[3/6] Loading v3.6.5 models and training data...")
    try:
        # Load models
        with open(models_dir / 'debt_model.pkl', 'rb') as f:
            debt_model = pickle.load(f)
        with open(models_dir / 'cashflow_model.pkl', 'rb') as f:
            cashflow_model = pickle.load(f)
        with open(models_dir / 'growth_model.pkl', 'rb') as f:
            growth_model = pickle.load(f)

        # Load scalers
        with open(models_dir / 'debt_scaler.pkl', 'rb') as f:
            debt_scaler = pickle.load(f)
        with open(models_dir / 'cashflow_scaler.pkl', 'rb') as f:
            cashflow_scaler = pickle.load(f)
        with open(models_dir / 'growth_scaler.pkl', 'rb') as f:
            growth_scaler = pickle.load(f)

        # Load feature definitions
        with open(models_dir / 'debt_features.pkl', 'rb') as f:
            debt_feat_def = pickle.load(f)
        with open(models_dir / 'cashflow_features.pkl', 'rb') as f:
            cashflow_feat_def = pickle.load(f)
        with open(models_dir / 'growth_features.pkl', 'rb') as f:
            growth_feat_def = pickle.load(f)

        # Load training data
        df_debt_train = pd.read_csv(training_data_dir / 'agent1_debt_v365.csv')
        df_cashflow_train = pd.read_csv(training_data_dir / 'agent2_cashflow_v365.csv')
        df_growth_train = pd.read_csv(training_data_dir / 'agent5_growth_v365.csv')

        print(f"      Models loaded from: {models_dir}")
        print(f"      Training data: {len(df_debt_train)} samples")
    except Exception as e:
        print(f"      ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None

    # Step 4: Run production inference (single prediction)
    print("\n[4/6] Running production inference...")
    try:
        # Prepare features for each agent
        def prepare_for_inference(features_df, feat_def, scaler):
            feature_cols = feat_def['feature_cols']
            continuous_cols = feat_def['continuous_features']

            X = features_df[feature_cols].copy()
            X[continuous_cols] = scaler.transform(X[continuous_cols])
            return X

        X_debt = prepare_for_inference(debt_features, debt_feat_def, debt_scaler)
        X_cashflow = prepare_for_inference(cashflow_features, cashflow_feat_def, cashflow_scaler)
        X_growth = prepare_for_inference(growth_features, growth_feat_def, growth_scaler)

        debt_proba = debt_model.predict_proba(X_debt)
        cashflow_proba = cashflow_model.predict_proba(X_cashflow)
        growth_proba = growth_model.predict_proba(X_growth)

        print(f"      Production predictions complete")
    except Exception as e:
        print(f"      ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None

    # Step 5: Bootstrap CI
    print(f"\n[5/6] Running Bootstrap CI ({n_bootstrap} iterations)...")
    try:
        print("      Debt agent...", end="", flush=True)
        debt_ci = bootstrap_ci_v365(
            debt_features, debt_model, debt_scaler,
            debt_feat_def['feature_cols'], debt_feat_def['continuous_features'],
            debt_feat_def['binary_features'], df_debt_train, n_bootstrap
        )
        print(" done")

        print("      Cashflow agent...", end="", flush=True)
        cashflow_ci = bootstrap_ci_v365(
            cashflow_features, cashflow_model, cashflow_scaler,
            cashflow_feat_def['feature_cols'], cashflow_feat_def['continuous_features'],
            cashflow_feat_def['binary_features'], df_cashflow_train, n_bootstrap
        )
        print(" done")

        print("      Growth agent...", end="", flush=True)
        growth_ci = bootstrap_ci_v365(
            growth_features, growth_model, growth_scaler,
            growth_feat_def['feature_cols'], growth_feat_def['continuous_features'],
            growth_feat_def['binary_features'], df_growth_train, n_bootstrap
        )
        print(" done")
    except Exception as e:
        print(f"\n      ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None

    # Step 6: Compile and save results
    print("\n[6/6] Compiling results...")

    all_quarters = []
    for q_idx in range(len(debt_features)):
        quarter_data = {
            'date': str(debt_features.iloc[q_idx]['date']),
            'year': int(pd.to_datetime(debt_features.iloc[q_idx]['date']).year),
            'debt': {
                'SELL': float(debt_ci[q_idx]['point_estimate'][0]),
                'HOLD': float(debt_ci[q_idx]['point_estimate'][1]),
                'BUY': float(debt_ci[q_idx]['point_estimate'][2]),
                'ci_width_SELL': float(debt_ci[q_idx]['ci_width'][0]),
                'ci_width_HOLD': float(debt_ci[q_idx]['ci_width'][1]),
                'ci_width_BUY': float(debt_ci[q_idx]['ci_width'][2]),
                'avg_ci_width': float(np.mean(debt_ci[q_idx]['ci_width']))
            },
            'cashflow': {
                'SELL': float(cashflow_ci[q_idx]['point_estimate'][0]),
                'HOLD': float(cashflow_ci[q_idx]['point_estimate'][1]),
                'BUY': float(cashflow_ci[q_idx]['point_estimate'][2]),
                'ci_width_SELL': float(cashflow_ci[q_idx]['ci_width'][0]),
                'ci_width_HOLD': float(cashflow_ci[q_idx]['ci_width'][1]),
                'ci_width_BUY': float(cashflow_ci[q_idx]['ci_width'][2]),
                'avg_ci_width': float(np.mean(cashflow_ci[q_idx]['ci_width']))
            },
            'growth': {
                'SELL': float(growth_ci[q_idx]['point_estimate'][0]),
                'HOLD': float(growth_ci[q_idx]['point_estimate'][1]),
                'BUY': float(growth_ci[q_idx]['point_estimate'][2]),
                'ci_width_SELL': float(growth_ci[q_idx]['ci_width'][0]),
                'ci_width_HOLD': float(growth_ci[q_idx]['ci_width'][1]),
                'ci_width_BUY': float(growth_ci[q_idx]['ci_width'][2]),
                'avg_ci_width': float(np.mean(growth_ci[q_idx]['ci_width']))
            }
        }

        # Calculate consensus
        signals = []
        for agent in ['debt', 'cashflow', 'growth']:
            probs = quarter_data[agent]
            signal = max(['SELL', 'HOLD', 'BUY'], key=lambda x: probs[x])
            signals.append(signal)

        vote_counts = {s: signals.count(s) for s in ['SELL', 'HOLD', 'BUY']}
        consensus = max(vote_counts, key=vote_counts.get)

        quarter_data['consensus'] = {
            'signal': consensus,
            'votes': vote_counts,
            'agreement': f"{vote_counts[consensus]}/3"
        }

        all_quarters.append(quarter_data)

    # Save JSON
    output_data = {
        'ticker': ticker,
        'company': company_name,
        'model_version': 'v3.6.5',
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
        'n_quarters': len(all_quarters),
        'n_bootstrap_iterations': n_bootstrap,
        'model_info': {
            'debt_features': len(debt_feat_def['feature_cols']),
            'cashflow_features': len(cashflow_feat_def['feature_cols']),
            'growth_features': len(growth_feat_def['feature_cols']),
            'training_samples': len(df_debt_train),
            'training_companies': df_debt_train['symbol'].nunique()
        },
        'quarters': all_quarters
    }

    with open(output_dir / f'{ticker}_v365_predictions.json', 'w') as f:
        json.dump(output_data, f, indent=2)

    # Save CSV (flattened)
    rows = []
    for q in all_quarters:
        row = {
            'date': q['date'],
            'year': q['year'],
            'debt_SELL': q['debt']['SELL'],
            'debt_HOLD': q['debt']['HOLD'],
            'debt_BUY': q['debt']['BUY'],
            'debt_ci_width': q['debt']['avg_ci_width'],
            'cashflow_SELL': q['cashflow']['SELL'],
            'cashflow_HOLD': q['cashflow']['HOLD'],
            'cashflow_BUY': q['cashflow']['BUY'],
            'cashflow_ci_width': q['cashflow']['avg_ci_width'],
            'growth_SELL': q['growth']['SELL'],
            'growth_HOLD': q['growth']['HOLD'],
            'growth_BUY': q['growth']['BUY'],
            'growth_ci_width': q['growth']['avg_ci_width'],
            'consensus': q['consensus']['signal'],
            'consensus_agreement': q['consensus']['agreement']
        }
        rows.append(row)

    df_results = pd.DataFrame(rows)
    df_results.to_csv(output_dir / f'{ticker}_v365_predictions.csv', index=False)

    print(f"      Saved to: {output_dir}")

    # Print summary
    print(f"\n{'='*80}")
    print(f"SUMMARY: {company_name} ({ticker}) - v3.6.5 ({n_bootstrap} Bootstrap Iterations)")
    print(f"{'='*80}")

    if all_quarters:
        latest = all_quarters[0]
        print(f"\nLatest Quarter: {latest['date']}")
        print(f"Consensus: {latest['consensus']['signal']} ({latest['consensus']['agreement']} agents)")

        print(f"\nAgent Predictions (Point Estimate [95% CI Width]):")
        print(f"  Debt:     SELL {latest['debt']['SELL']:.1%}, HOLD {latest['debt']['HOLD']:.1%}, BUY {latest['debt']['BUY']:.1%} [CI: {latest['debt']['avg_ci_width']:.1%}]")
        print(f"  Cashflow: SELL {latest['cashflow']['SELL']:.1%}, HOLD {latest['cashflow']['HOLD']:.1%}, BUY {latest['cashflow']['BUY']:.1%} [CI: {latest['cashflow']['avg_ci_width']:.1%}]")
        print(f"  Growth:   SELL {latest['growth']['SELL']:.1%}, HOLD {latest['growth']['HOLD']:.1%}, BUY {latest['growth']['BUY']:.1%} [CI: {latest['growth']['avg_ci_width']:.1%}]")

        # CI width summary
        avg_debt_ci = np.mean([q['debt']['avg_ci_width'] for q in all_quarters])
        avg_cashflow_ci = np.mean([q['cashflow']['avg_ci_width'] for q in all_quarters])
        avg_growth_ci = np.mean([q['growth']['avg_ci_width'] for q in all_quarters])

        print(f"\nAverage CI Width Across All Quarters:")
        print(f"  Debt:     {avg_debt_ci:.1%}")
        print(f"  Cashflow: {avg_cashflow_ci:.1%}")
        print(f"  Growth:   {avg_growth_ci:.1%}")

    print(f"\n{'='*80}\n")

    return output_data


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python run_v365_inference.py TICKER 'Company Name' [n_bootstrap]")
        print("Example: python run_v365_inference.py NVDA Nvidia 50")
        sys.exit(1)

    ticker = sys.argv[1]
    company_name = sys.argv[2]
    n_bootstrap = int(sys.argv[3]) if len(sys.argv) > 3 else 50

    run_v365_inference(ticker, company_name, n_bootstrap)
