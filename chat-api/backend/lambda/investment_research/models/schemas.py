"""
Data models and schemas for Investment Research API.

Includes Pydantic models for request/response validation
and JSON serialization utilities for DynamoDB Decimal types.
"""
import json
from decimal import Decimal
from datetime import datetime
from typing import Optional, Any, List
from pydantic import BaseModel, Field


class DecimalEncoder(json.JSONEncoder):
    """
    Custom JSON encoder that handles Decimal types from DynamoDB.

    Also handles datetime objects for consistent serialization.
    """
    def default(self, obj):
        if isinstance(obj, Decimal):
            # Convert to int if whole number, else float
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat() + 'Z'
        return super().default(obj)


def json_dumps(obj: Any) -> str:
    """JSON dumps with DecimalEncoder for DynamoDB compatibility."""
    return json.dumps(obj, cls=DecimalEncoder)


class FollowUpRequest(BaseModel):
    """Request model for follow-up question endpoint."""
    ticker: str = Field(..., description="Stock ticker symbol (e.g., AAPL)")
    question: str = Field(..., description="Follow-up question about the report")
    conversation_id: Optional[str] = Field(
        None,
        description="Conversation ID for maintaining context across questions"
    )
    section_id: Optional[str] = Field(
        None,
        description="Currently active section ID for additional context"
    )
    fiscal_year: Optional[int] = Field(
        None,
        description="Fiscal year of the report (default: current year)"
    )


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str = Field(..., description="Service status")
    timestamp: str = Field(..., description="ISO timestamp")
    environment: str = Field(..., description="Environment (dev/staging/prod)")
    service: str = Field(default="investment-research", description="Service name")


class RatingInfo(BaseModel):
    """Individual domain rating information."""
    rating: str = Field(..., description="Rating: Very Strong/Strong/Stable/Weak/Very Weak")
    confidence: str = Field(..., description="Confidence level: High/Medium/Low")
    key_factors: List[str] = Field(default_factory=list, description="Key factors for the rating")


class ReportMetadata(BaseModel):
    """Metadata for a cached report."""
    ticker: str
    fiscal_year: int
    generated_at: Optional[str] = None
    model: Optional[str] = None
    overall_verdict: Optional[str] = None  # BUY/HOLD/SELL
    conviction: Optional[str] = None  # High/Medium/Low
