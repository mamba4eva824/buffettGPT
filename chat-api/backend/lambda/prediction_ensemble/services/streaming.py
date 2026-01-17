"""
SSE (Server-Sent Events) formatting utilities.

EXTRACTED FROM: handler.py line 502-504
- format_sse_event(): line 502-504

Provides consistent SSE event formatting for streaming responses.
"""
import json
from datetime import datetime
from typing import Any, Dict

from models.schemas import DecimalEncoder


def format_sse_event(data: str, event_type: str = "message") -> str:
    """
    Format data as Server-Sent Event.

    Args:
        data: The data string (usually JSON) to send
        event_type: SSE event type (default: "message")

    Returns:
        SSE-formatted string: "event: {type}\ndata: {data}\n\n"
    """
    return f"event: {event_type}\ndata: {data}\n\n"


def json_sse_event(data: Dict[str, Any], event_type: str = "message") -> str:
    """
    Format a dict as JSON SSE event.

    Args:
        data: Dictionary to serialize as JSON
        event_type: SSE event type

    Returns:
        SSE-formatted string with JSON data
    """
    return format_sse_event(json.dumps(data, cls=DecimalEncoder), event_type)


# Typed event helpers for common event types

def connected_event() -> str:
    """Send connection established event."""
    return json_sse_event({
        "type": "connected",
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }, "connected")


def status_event(message: str, step: str = None) -> str:
    """Send status update event."""
    data = {
        "type": "status",
        "message": message,
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }
    if step:
        data["step"] = step
    return json_sse_event(data, "status")


def inference_event(agent_type: str, ticker: str, result: dict, features: dict = None) -> str:
    """Send ML inference result event."""
    data = {
        "type": "inference",
        "agent_type": agent_type,
        "ticker": ticker,
        "prediction": result.get('prediction'),
        "confidence": result.get('confidence'),
        "ci_width": result.get('ci_width'),
        "confidence_interpretation": result.get('confidence_interpretation'),
        "probabilities": result.get('probabilities'),
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }
    if features:
        data["features"] = features
    return json_sse_event(data, "inference")


def chunk_event(text: str, agent_type: str = None) -> str:
    """Send streaming text chunk event."""
    data = {
        "type": "chunk",
        "text": text,
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }
    if agent_type:
        data["agent_type"] = agent_type
    return json_sse_event(data, "chunk")


def error_event(message: str, code: str = None) -> str:
    """Send error event."""
    data = {
        "type": "error",
        "message": message,
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }
    if code:
        data["code"] = code
    return json_sse_event(data, "error")


def complete_event(data: dict = None) -> str:
    """Send completion event."""
    event_data = {
        "type": "complete",
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }
    if data:
        event_data.update(data)
    return json_sse_event(event_data, "complete")
