"""
Ensemble Metrics Computation

Computes consensus, confidence spread, and divergence metrics
from the three expert agents (debt, cashflow, growth).
"""

from typing import Dict, Any, List, Optional
from collections import Counter


def compute_ensemble_metrics(inference_results: Dict[str, Dict]) -> Dict[str, Any]:
    """
    Compute ensemble-level consensus and confidence metrics.

    Args:
        inference_results: Dict with keys 'debt', 'cashflow', 'growth',
                          each containing 'prediction', 'confidence', etc.

    Returns:
        Dict containing:
            - consensus: The majority prediction (SELL/HOLD/BUY)
            - unanimous: Whether all agents agree
            - predictions: Dict of each agent's prediction
            - confidence_by_agent: Dict of each agent's confidence
            - ensemble_average_confidence: Mean confidence across agents
            - confidence_spread: Max - Min confidence (disagreement indicator)
            - most_confident_agent: Agent with highest confidence
            - least_confident_agent: Agent with lowest confidence
            - divergence_alert: Warning if significant disagreement exists
            - voting_breakdown: Count of each signal type
            - weighted_consensus: Confidence-weighted signal
    """
    agents = ['debt', 'cashflow', 'growth']

    # Extract predictions and confidences
    predictions = {}
    confidences = {}
    probabilities = {}

    for agent in agents:
        result = inference_results.get(agent, {})
        predictions[agent] = result.get('prediction', 'HOLD')
        confidences[agent] = result.get('confidence', 0.33)
        probabilities[agent] = result.get('probabilities', {
            'SELL': 0.33, 'HOLD': 0.34, 'BUY': 0.33
        })

    # Voting breakdown
    vote_counts = Counter(predictions.values())
    voting_breakdown = {
        'SELL': vote_counts.get('SELL', 0),
        'HOLD': vote_counts.get('HOLD', 0),
        'BUY': vote_counts.get('BUY', 0)
    }

    # Determine consensus (majority vote)
    consensus = vote_counts.most_common(1)[0][0]

    # Check unanimity
    unanimous = len(set(predictions.values())) == 1

    # Confidence statistics
    confidence_values = list(confidences.values())
    ensemble_average_confidence = round(sum(confidence_values) / len(confidence_values), 2)
    confidence_spread = round(max(confidence_values) - min(confidence_values), 2)

    # Most/least confident agents
    most_confident_agent = max(confidences, key=confidences.get)
    least_confident_agent = min(confidences, key=confidences.get)

    # Weighted consensus (confidence-weighted voting)
    weighted_scores = {'SELL': 0.0, 'HOLD': 0.0, 'BUY': 0.0}
    for agent in agents:
        pred = predictions[agent]
        conf = confidences[agent]
        weighted_scores[pred] += conf

    weighted_consensus = max(weighted_scores, key=weighted_scores.get)
    weighted_confidence = round(weighted_scores[weighted_consensus] / len(agents), 2)

    # Divergence alert conditions
    divergence_alert = _compute_divergence_alert(
        predictions, confidences, vote_counts, confidence_spread
    )

    # Consensus strength interpretation
    consensus_strength = _interpret_consensus_strength(
        unanimous, vote_counts, ensemble_average_confidence, confidence_spread
    )

    # Probability-based ensemble (average probabilities)
    ensemble_probabilities = _compute_ensemble_probabilities(probabilities)

    return {
        'consensus': consensus,
        'unanimous': unanimous,
        'predictions': predictions,
        'confidence_by_agent': {k: round(v, 2) for k, v in confidences.items()},
        'ensemble_average_confidence': ensemble_average_confidence,
        'confidence_spread': confidence_spread,
        'most_confident_agent': most_confident_agent,
        'least_confident_agent': least_confident_agent,
        'divergence_alert': divergence_alert,
        'voting_breakdown': voting_breakdown,
        'weighted_consensus': weighted_consensus,
        'weighted_confidence': weighted_confidence,
        'consensus_strength': consensus_strength,
        'ensemble_probabilities': ensemble_probabilities
    }


def _compute_divergence_alert(
    predictions: Dict[str, str],
    confidences: Dict[str, float],
    vote_counts: Counter,
    confidence_spread: float
) -> Optional[Dict[str, Any]]:
    """
    Compute divergence alert if significant disagreement exists.

    Returns alert dict if divergence detected, None otherwise.
    """
    alerts = []

    # Alert 1: No majority (all different predictions)
    if vote_counts.most_common(1)[0][1] == 1:
        alerts.append({
            'type': 'three_way_split',
            'severity': 'high',
            'message': 'All three experts disagree - no clear consensus'
        })

    # Alert 2: High confidence disagreement
    high_conf_agents = [a for a, c in confidences.items() if c >= 0.6]
    if len(high_conf_agents) >= 2:
        high_conf_preds = [predictions[a] for a in high_conf_agents]
        if len(set(high_conf_preds)) > 1:
            alerts.append({
                'type': 'confident_disagreement',
                'severity': 'medium',
                'message': f'High-confidence experts disagree: {high_conf_agents}'
            })

    # Alert 3: Wide confidence spread
    if confidence_spread >= 0.3:
        alerts.append({
            'type': 'confidence_disparity',
            'severity': 'low',
            'message': f'Large confidence spread ({confidence_spread:.0%}) between experts'
        })

    # Alert 4: Opposing signals (BUY vs SELL)
    pred_set = set(predictions.values())
    if 'BUY' in pred_set and 'SELL' in pred_set:
        alerts.append({
            'type': 'opposing_signals',
            'severity': 'high',
            'message': 'Experts have opposing BUY and SELL signals'
        })

    if alerts:
        return {
            'has_divergence': True,
            'alert_count': len(alerts),
            'alerts': alerts,
            'highest_severity': max(a['severity'] for a in alerts)
        }

    return None


def _interpret_consensus_strength(
    unanimous: bool,
    vote_counts: Counter,
    avg_confidence: float,
    spread: float
) -> Dict[str, Any]:
    """
    Interpret the strength of the ensemble consensus.
    """
    # Determine strength level
    if unanimous and avg_confidence >= 0.7 and spread <= 0.15:
        strength = 'VERY_STRONG'
        description = 'All experts unanimously agree with high confidence'
    elif unanimous and avg_confidence >= 0.5:
        strength = 'STRONG'
        description = 'All experts agree with moderate to high confidence'
    elif vote_counts.most_common(1)[0][1] >= 2 and avg_confidence >= 0.6:
        strength = 'MODERATE'
        description = 'Majority agreement with good confidence'
    elif vote_counts.most_common(1)[0][1] >= 2:
        strength = 'WEAK'
        description = 'Majority agrees but confidence is mixed'
    else:
        strength = 'VERY_WEAK'
        description = 'No clear consensus - experts are divided'

    return {
        'level': strength,
        'description': description,
        'unanimous': unanimous,
        'majority_count': vote_counts.most_common(1)[0][1],
        'avg_confidence': avg_confidence,
        'confidence_spread': spread
    }


def _compute_ensemble_probabilities(
    probabilities: Dict[str, Dict[str, float]]
) -> Dict[str, float]:
    """
    Compute ensemble probabilities by averaging across agents.
    """
    signals = ['SELL', 'HOLD', 'BUY']
    ensemble_probs = {}

    for signal in signals:
        total = sum(probs.get(signal, 0.33) for probs in probabilities.values())
        ensemble_probs[signal] = round(total / len(probabilities), 2)

    return ensemble_probs


def format_ensemble_summary(metrics: Dict[str, Any]) -> str:
    """
    Format ensemble metrics as a human-readable summary.

    Args:
        metrics: Output from compute_ensemble_metrics()

    Returns:
        Formatted string summary
    """
    lines = []

    # Header
    consensus = metrics['consensus']
    unanimous = "UNANIMOUS" if metrics['unanimous'] else "MAJORITY"
    avg_conf = metrics['ensemble_average_confidence']
    lines.append(f"ENSEMBLE VERDICT: {consensus} ({unanimous}, {avg_conf:.0%} avg confidence)")
    lines.append("")

    # Individual predictions
    lines.append("Expert Breakdown:")
    for agent, pred in metrics['predictions'].items():
        conf = metrics['confidence_by_agent'][agent]
        marker = "←" if agent == metrics['most_confident_agent'] else ""
        lines.append(f"  • {agent.upper()}: {pred} ({conf:.0%}) {marker}")
    lines.append("")

    # Voting breakdown
    vb = metrics['voting_breakdown']
    lines.append(f"Votes: SELL={vb['SELL']} | HOLD={vb['HOLD']} | BUY={vb['BUY']}")

    # Consensus strength
    strength = metrics['consensus_strength']
    lines.append(f"Consensus Strength: {strength['level']} - {strength['description']}")

    # Divergence alerts
    if metrics['divergence_alert']:
        lines.append("")
        lines.append("⚠️ DIVERGENCE ALERTS:")
        for alert in metrics['divergence_alert']['alerts']:
            lines.append(f"  [{alert['severity'].upper()}] {alert['message']}")

    return "\n".join(lines)
