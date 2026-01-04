"""
Data models, schemas, and serialization utilities.
"""
import json
from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import numpy as np


class DecimalEncoder(json.JSONEncoder):
    """Handle Decimal, numpy types, and NaN/infinity for JSON serialization.

    IMPORTANT: Standard JSON does not support NaN or Infinity values.
    This encoder converts them to None to produce valid JSON that
    Bedrock action groups can parse.
    """
    def default(self, obj):
        if isinstance(obj, Decimal):
            f = float(obj)
            # Handle NaN and infinity from Decimal
            if f != f or f == float('inf') or f == float('-inf'):
                return None
            return f
        if isinstance(obj, np.floating):
            f = float(obj)
            # Handle NaN and infinity from numpy
            if np.isnan(f) or np.isinf(f):
                return None
            return f
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, datetime):
            return obj.isoformat() + 'Z'
        # Handle Python float NaN/inf that might slip through
        if isinstance(obj, float):
            if obj != obj or obj == float('inf') or obj == float('-inf'):
                return None
            return obj
        return super().default(obj)


@dataclass
class AnalysisRequest:
    """Request model for analysis endpoint."""
    company: str
    agent_type: Optional[str] = None
    fiscal_year: Optional[int] = None
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    mode: Optional[str] = None  # 'single', 'parallel', 'supervisor'

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AnalysisRequest':
        return cls(
            company=data.get('company', data.get('ticker', '')).strip(),
            agent_type=data.get('agent_type', 'debt'),
            fiscal_year=data.get('fiscal_year', datetime.now().year),
            session_id=data.get('session_id'),
            conversation_id=data.get('conversation_id'),
            mode=data.get('mode', 'single')
        )


@dataclass
class InferenceResult:
    """Result from XGBoost model inference."""
    prediction: str  # BUY, HOLD, SELL
    confidence: float
    ci_width: float
    confidence_interpretation: str  # STRONG, MODERATE, WEAK
    probabilities: Dict[str, float]
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'prediction': self.prediction,
            'confidence': self.confidence,
            'ci_width': self.ci_width,
            'confidence_interpretation': self.confidence_interpretation,
            'probabilities': self.probabilities,
            'error': self.error
        }


@dataclass
class ExpertResult:
    """Result from an expert agent analysis."""
    agent_type: str
    inference: InferenceResult
    analysis: str
    timestamp: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'agent_type': self.agent_type,
            'inference': self.inference.to_dict() if self.inference else None,
            'analysis': self.analysis,
            'timestamp': self.timestamp,
            'error': self.error
        }


def sanitize_for_json(obj: Any) -> Any:
    """
    Recursively sanitize data for JSON serialization.

    Converts NaN/infinity values to None since standard JSON doesn't support them.
    This is necessary because json.dumps serializes Python floats directly
    without calling the encoder's default() method.
    """
    import math

    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (np.floating, np.integer)):
        f = float(obj)
        if math.isnan(f) or math.isinf(f):
            return None
        return f if isinstance(obj, np.floating) else int(obj)
    if isinstance(obj, Decimal):
        f = float(obj)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    return obj


def json_dumps(obj: Any) -> str:
    """JSON dumps with DecimalEncoder and NaN sanitization."""
    sanitized = sanitize_for_json(obj)
    return json.dumps(sanitized, cls=DecimalEncoder)


def format_calendar_quarters(period_dates: list) -> list:
    """
    Convert period dates to calendar quarter format (e.g., "Q3 2024").

    Args:
        period_dates: List of date strings in various formats (e.g., "2024-09-30", "2024-Q3")

    Returns:
        List of calendar quarter strings (e.g., ["Q3 2024", "Q2 2024", ...])
    """
    calendar_quarters = []
    for date_str in period_dates:
        try:
            if not date_str:
                calendar_quarters.append("")
                continue

            # Handle different date formats
            if 'Q' in str(date_str):
                # Already in quarter format like "2024-Q3" or "Q3 2024"
                if '-Q' in date_str:
                    year, quarter = date_str.split('-Q')
                    calendar_quarters.append(f"Q{quarter} {year}")
                else:
                    calendar_quarters.append(date_str)
            else:
                # Parse as date (e.g., "2024-09-30")
                date_obj = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
                quarter = (date_obj.month - 1) // 3 + 1
                calendar_quarters.append(f"Q{quarter} {date_obj.year}")
        except Exception:
            calendar_quarters.append(str(date_str))

    return calendar_quarters
