#!/usr/bin/env python3
"""
v3.6.5 Step 5: Train Models with Expanded HOLD Data
====================================================

Trains XGBoost classifiers using the v3.6.5 training data that includes
expanded AXP (1995-2025) and COST (2000-2020) HOLD samples.

Key changes from v3.6.4:
- ~154 additional HOLD samples (AXP: ~120, COST: ~34 new)
- Better class balance (HOLD increases from 22% to ~30%)
- Same features and hyperparameters as v3.6.4

Author: Claude Code
Date: 2025-11-24
Version: v3.6.5
"""

import pandas as pd
import numpy as np
import pickle
import json
from pathlib import Path
from datetime import datetime
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
import xgboost as xgb


# Bootstrap CI parameters
BOOTSTRAP_N_ITERATIONS = 1000
BOOTSTRAP_CI_LEVEL = 0.95


def bootstrap_accuracy_ci(y_true, y_pred, n_iterations=1000, ci_level=0.95):
    """
    Calculate bootstrap confidence interval for accuracy.

    Args:
        y_true: True labels
        y_pred: Predicted labels
        n_iterations: Number of bootstrap samples
        ci_level: Confidence level (e.g., 0.95 for 95% CI)

    Returns:
        tuple: (point_estimate, lower_bound, upper_bound)
    """
    np.random.seed(42)
    n_samples = len(y_true)
    accuracies = []

    for _ in range(n_iterations):
        # Resample with replacement
        indices = np.random.choice(n_samples, size=n_samples, replace=True)
        y_true_boot = y_true[indices]
        y_pred_boot = y_pred[indices]

        # Calculate accuracy on bootstrap sample
        acc = accuracy_score(y_true_boot, y_pred_boot)
        accuracies.append(acc)

    accuracies = np.array(accuracies)

    # Calculate percentiles for CI
    alpha = 1 - ci_level
    lower = np.percentile(accuracies, alpha / 2 * 100)
    upper = np.percentile(accuracies, (1 - alpha / 2) * 100)
    point_estimate = accuracy_score(y_true, y_pred)

    return point_estimate, lower, upper


# Setup paths
script_dir = Path(__file__).parent
project_dir = script_dir.parent.parent
data_dir = project_dir / 'data' / 'v3.6.5_expanded_hold'
models_dir = project_dir / 'models' / 'v3.6.5_lifecycle'


# v3.6 conservative hyperparameters (same as v3.6.3/v3.6.4)
XGB_PARAMS = {
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
    'random_state': 42,
    'eval_metric': 'mlogloss',
    'early_stopping_rounds': 20,
    'verbosity': 0
}


# Binary features by agent (won't be scaled)
BINARY_FEATURES = {
    'debt': [
        'is_deleveraging', 'is_leverage_increasing',
        'is_liquidity_deteriorating', 'debt_growth_faster_than_equity'
    ],
    'cashflow': ['fcf_trend_4q'],
    'growth': [
        'revenue_growth_trend', 'growth_momentum_positive', 'growth_deceleration_warning',
        'margin_momentum_positive', 'is_margin_expanding', 'is_growth_accelerating',
        'is_profitability_improving'
    ]
}


def train_agent(agent_name, training_file, output_prefix):
    """Train a single agent model with random stratified split."""
    print(f"\n{'=' * 80}")
    print(f"TRAINING AGENT: {agent_name.upper()}")
    print(f"{'=' * 80}")

    # Load data
    df = pd.read_csv(training_file)
    df['date'] = pd.to_datetime(df['date'])

    print(f"\nData: {len(df)} samples, {df['symbol'].nunique()} companies")

    # Label distribution
    print(f"\nLabel Distribution:")
    for label in [0, 1, 2]:
        label_name = {0: 'SELL', 1: 'HOLD', 2: 'BUY'}.get(label)
        count = (df['label'] == label).sum()
        pct = count / len(df) * 100
        print(f"  {label_name}: {count:4d} ({pct:5.1f}%)")

    # Identify feature columns
    metadata_cols = ['symbol', 'company', 'date', 'year', 'label', 'label_name']
    feature_cols = [c for c in df.columns if c not in metadata_cols and not c.startswith('Unnamed')]

    # Remove any duplicate columns
    feature_cols = list(dict.fromkeys(feature_cols))

    # Remove columns with too many NaN values (< 10% coverage)
    valid_features = []
    for col in feature_cols:
        coverage = df[col].notna().sum() / len(df)
        if coverage >= 0.10:
            valid_features.append(col)

    feature_cols = valid_features
    print(f"\nFeatures: {len(feature_cols)}")

    # Get binary vs continuous features
    agent_key = 'debt' if 'debt' in agent_name.lower() else \
                'cashflow' if 'cashflow' in agent_name.lower() else 'growth'
    binary_features = [f for f in BINARY_FEATURES.get(agent_key, []) if f in feature_cols]
    continuous_features = [f for f in feature_cols if f not in binary_features]

    print(f"  Binary: {len(binary_features)}")
    print(f"  Continuous: {len(continuous_features)}")

    # Extract features and labels
    X = df[feature_cols].copy()
    y = df['label'].values

    # Standard random stratified train-test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print(f"\n  Train: {len(X_train)} samples")
    print(f"  Test:  {len(X_test)} samples")

    # Scale continuous features
    scaler = StandardScaler()
    X_train_scaled = X_train.copy()
    X_test_scaled = X_test.copy()

    if continuous_features:
        X_train_scaled[continuous_features] = scaler.fit_transform(X_train[continuous_features])
        X_test_scaled[continuous_features] = scaler.transform(X_test[continuous_features])

    # Train model
    print(f"\n  Training XGBoost...")
    model = xgb.XGBClassifier(**XGB_PARAMS)
    model.fit(
        X_train_scaled, y_train,
        eval_set=[(X_test_scaled, y_test)],
        verbose=False
    )
    print(f"  Best iteration: {model.best_iteration}")

    # Evaluate
    y_train_pred = model.predict(X_train_scaled)
    y_test_pred = model.predict(X_test_scaled)

    train_acc = accuracy_score(y_train, y_train_pred)
    test_acc = accuracy_score(y_test, y_test_pred)

    print(f"\n  Accuracy:")
    print(f"    Train: {train_acc*100:.1f}%")
    print(f"    Test:  {test_acc*100:.1f}%")
    print(f"    Gap:   {(train_acc - test_acc)*100:.1f}%")

    # Bootstrap CI for test accuracy
    print(f"\n  Bootstrap 95% CI ({BOOTSTRAP_N_ITERATIONS} iterations):")
    test_point, test_lower, test_upper = bootstrap_accuracy_ci(
        y_test, y_test_pred,
        n_iterations=BOOTSTRAP_N_ITERATIONS,
        ci_level=BOOTSTRAP_CI_LEVEL
    )
    print(f"    Test Accuracy: {test_point*100:.1f}% [{test_lower*100:.1f}% - {test_upper*100:.1f}%]")

    train_point, train_lower, train_upper = bootstrap_accuracy_ci(
        y_train, y_train_pred,
        n_iterations=BOOTSTRAP_N_ITERATIONS,
        ci_level=BOOTSTRAP_CI_LEVEL
    )
    print(f"    Train Accuracy: {train_point*100:.1f}% [{train_lower*100:.1f}% - {train_upper*100:.1f}%]")

    # Cross-validation
    cv_params = {k: v for k, v in XGB_PARAMS.items() if k != 'early_stopping_rounds'}
    cv_model = xgb.XGBClassifier(**cv_params)
    cv_scores = cross_val_score(cv_model, X_train_scaled, y_train, cv=5)
    print(f"\n  5-Fold CV: {cv_scores.mean()*100:.1f}% (+/- {cv_scores.std()*100:.1f}%)")

    # Classification report
    print(f"\n  Classification Report (Test):")
    target_names = ['SELL', 'HOLD', 'BUY']
    report = classification_report(y_test, y_test_pred, target_names=target_names)
    for line in report.split('\n'):
        print(f"  {line}")

    # Confusion matrix
    cm = confusion_matrix(y_test, y_test_pred)
    print(f"\n  Confusion Matrix:")
    print(f"             Predicted")
    print(f"             SELL  HOLD  BUY")
    print(f"  Actual SELL  {cm[0,0]:4d}  {cm[0,1]:4d}  {cm[0,2]:4d}")
    print(f"         HOLD  {cm[1,0]:4d}  {cm[1,1]:4d}  {cm[1,2]:4d}")
    print(f"         BUY   {cm[2,0]:4d}  {cm[2,1]:4d}  {cm[2,2]:4d}")

    # Feature importance
    importance = model.feature_importances_
    importance_df = pd.DataFrame({
        'feature': feature_cols,
        'importance': importance
    }).sort_values('importance', ascending=False)

    print(f"\n  Top 10 Features:")
    for i, (_, row) in enumerate(importance_df.head(10).iterrows(), 1):
        print(f"    {i:2d}. {row['feature']}: {row['importance']*100:.2f}%")

    # Save model artifacts
    models_dir.mkdir(parents=True, exist_ok=True)

    # Model
    model_path = models_dir / f'{output_prefix}_model.pkl'
    with open(model_path, 'wb') as f:
        pickle.dump(model, f)

    # Scaler
    scaler_path = models_dir / f'{output_prefix}_scaler.pkl'
    with open(scaler_path, 'wb') as f:
        pickle.dump(scaler, f)

    # Features
    features_path = models_dir / f'{output_prefix}_features.pkl'
    with open(features_path, 'wb') as f:
        pickle.dump({
            'feature_cols': feature_cols,
            'continuous_features': continuous_features,
            'binary_features': binary_features
        }, f)

    # Save feature importance
    importance_df.to_csv(data_dir / f'{output_prefix}_feature_importance.csv', index=False)

    print(f"\n  Saved: {model_path.name}, {scaler_path.name}, {features_path.name}")

    return {
        'agent': agent_name,
        'samples': len(df),
        'companies': df['symbol'].nunique(),
        'features': len(feature_cols),
        'train_acc': train_acc,
        'test_acc': test_acc,
        'gap': train_acc - test_acc,
        'cv_mean': cv_scores.mean(),
        'cv_std': cv_scores.std(),
        'test_ci_lower': test_lower,
        'test_ci_upper': test_upper,
        'train_ci_lower': train_lower,
        'train_ci_upper': train_upper
    }


def main():
    """Train all three agent models."""
    print("=" * 80)
    print("v3.6.5: TRAIN ALL THREE AGENT MODELS (EXPANDED HOLD DATA)")
    print("=" * 80)
    print(f"\nData directory: {data_dir}")
    print(f"Model directory: {models_dir}")
    print(f"\nExpanded data: AXP (1995-2025) + COST (2000-2020) HOLD labels")
    print(f"\nXGBoost Hyperparameters (v3.6 conservative):")
    for k, v in list(XGB_PARAMS.items())[:8]:
        print(f"  {k}: {v}")

    results = []

    # Train Debt Agent
    results.append(train_agent(
        'Debt Analyzer (Agent 1)',
        data_dir / 'agent1_debt_v365.csv',
        'debt'
    ))

    # Train Cashflow Agent
    results.append(train_agent(
        'Cashflow Analyzer (Agent 2)',
        data_dir / 'agent2_cashflow_v365.csv',
        'cashflow'
    ))

    # Train Growth Agent
    results.append(train_agent(
        'Growth Analyzer (Agent 5)',
        data_dir / 'agent5_growth_v365.csv',
        'growth'
    ))

    # Save metadata
    metadata = {
        'version': 'v3.6.5',
        'date': datetime.now().isoformat(),
        'description': 'v3.6.5 models with expanded AXP/COST HOLD data',
        'total_companies': results[0]['companies'],
        'total_samples': results[0]['samples'],
        'expanded_data': {
            'AXP': '1995-2025 (HOLD)',
            'COST': '2000-2020 (HOLD)'
        },
        'split_method': 'random_stratified',
        'test_size': 0.2,
        'agents': {
            'debt': {
                'features': results[0]['features'],
                'test_accuracy': results[0]['test_acc'],
                'test_ci_95': [results[0]['test_ci_lower'], results[0]['test_ci_upper']],
                'train_accuracy': results[0]['train_acc'],
                'gap': results[0]['gap'],
                'cv_mean': results[0]['cv_mean']
            },
            'cashflow': {
                'features': results[1]['features'],
                'test_accuracy': results[1]['test_acc'],
                'test_ci_95': [results[1]['test_ci_lower'], results[1]['test_ci_upper']],
                'train_accuracy': results[1]['train_acc'],
                'gap': results[1]['gap'],
                'cv_mean': results[1]['cv_mean']
            },
            'growth': {
                'features': results[2]['features'],
                'test_accuracy': results[2]['test_acc'],
                'test_ci_95': [results[2]['test_ci_lower'], results[2]['test_ci_upper']],
                'train_accuracy': results[2]['train_acc'],
                'gap': results[2]['gap'],
                'cv_mean': results[2]['cv_mean']
            }
        },
        'bootstrap_ci': {
            'n_iterations': BOOTSTRAP_N_ITERATIONS,
            'confidence_level': BOOTSTRAP_CI_LEVEL
        },
        'hyperparameters': {k: v for k, v in XGB_PARAMS.items() if k != 'verbosity'}
    }

    with open(models_dir / 'metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)

    # Summary
    print("\n" + "=" * 80)
    print("TRAINING SUMMARY (v3.6.5 - Expanded HOLD Data)")
    print("=" * 80)

    print("\n| Agent    | Test Acc | 95% CI | Train Acc | Gap   | CV Mean |")
    print("|----------|----------|--------|-----------|-------|---------|")
    for r in results:
        ci_str = f"[{r['test_ci_lower']*100:.1f}-{r['test_ci_upper']*100:.1f}]"
        print(f"| {r['agent'][:8]:8s} | {r['test_acc']*100:7.1f}% | {ci_str:14s} | "
              f"{r['train_acc']*100:8.1f}% | {r['gap']*100:4.1f}% | {r['cv_mean']*100:6.1f}% |")

    # Comparison with v3.6.4
    print("\n" + "=" * 80)
    print("COMPARISON: v3.6.5 vs v3.6.4")
    print("=" * 80)

    v364_metadata_path = project_dir / 'models' / 'v3.6.4_lifecycle_random' / 'metadata.json'
    if v364_metadata_path.exists():
        with open(v364_metadata_path) as f:
            v364_meta = json.load(f)

        print("\n| Agent    | Metric    | v3.6.4 | v3.6.5 | Change  |")
        print("|----------|-----------|--------|--------|---------|")

        agents = [('debt', 'Debt', 0), ('cashflow', 'Cashflow', 1), ('growth', 'Growth', 2)]
        for agent_key, agent_name, idx in agents:
            v364_test = v364_meta['agents'][agent_key]['test_accuracy']
            v365_test = results[idx]['test_acc']
            v364_samples = v364_meta.get('total_samples', 1326)
            v365_samples = results[idx]['samples']

            test_change = (v365_test - v364_test) * 100

            print(f"| {agent_name:8s} | Test Acc  | {v364_test*100:5.1f}% | {v365_test*100:5.1f}% | {test_change:+6.1f}% |")

        print(f"\n| Metric        | v3.6.4 | v3.6.5 | Change |")
        print(f"|---------------|--------|--------|--------|")
        print(f"| Total Samples | {v364_samples} | {results[0]['samples']} | +{results[0]['samples'] - v364_samples} |")

        # Calculate HOLD % change
        v364_hold_pct = 22.2  # From v3.6.4 documentation
        # Estimate v3.6.5 HOLD %
        df_debt = pd.read_csv(data_dir / 'agent1_debt_v365.csv')
        v365_hold_pct = (df_debt['label'] == 1).sum() / len(df_debt) * 100
        print(f"| HOLD %        | {v364_hold_pct:.1f}% | {v365_hold_pct:.1f}% | +{v365_hold_pct - v364_hold_pct:.1f}% |")

    print(f"\n  All models saved to: {models_dir}")

    print(f"\n{'=' * 80}")
    print("TRAINING COMPLETE")
    print(f"{'=' * 80}")


if __name__ == '__main__':
    main()
