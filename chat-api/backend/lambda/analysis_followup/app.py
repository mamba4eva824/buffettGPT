"""
Analysis Follow-Up — FastAPI + Lambda Web Adapter (Docker)

Thin HTTP wrapper around the canonical handler in
`handlers.analysis_followup`. Translates HTTP requests into the
Lambda-event shape that `stream_followup_response` expects, then
streams its SSE output back through `EventSourceResponse`.
"""

import asyncio
import logging
import os
from typing import Optional

import jwt
from fastapi import FastAPI, Request
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from handlers.analysis_followup import get_jwt_secret, stream_followup_response

logging.basicConfig(level=os.environ.get('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

PUBLIC_PATHS = {'/health', '/docs', '/openapi.json'}

app = FastAPI(title='Analysis Follow-Up', version='1.0.0')


# The canonical handler at handlers.analysis_followup emits SSE events named
# `chunk` / `complete` / `error`. The Value Insights chat panel's SSE consumer
# (frontend/src/components/value-insights/InsightsChatPanel.jsx) listens for
# `followup_chunk` / `followup_end` / `error` — the names the original
# Docker app baked in. Map handler names → frontend names here so the
# canonical handler stays unchanged and the Docker image still talks the
# protocol the frontend expects.
_EVENT_NAME_MAP = {
    'chunk': 'followup_chunk',
    'complete': 'followup_end',
}


def _parse_sse_chunk(chunk: str) -> dict:
    """Parse a chunk emitted by handlers.analysis_followup.format_sse_event back
    into the {event, data} shape EventSourceResponse expects, and translate the
    event name into what the Value Insights chat panel listens for.

    format_sse_event always produces `event: <type>\\ndata: <json>\\n\\n` so we
    can split on newlines and pull each prefix.
    """
    event_type = 'message'
    data = ''
    for line in chunk.splitlines():
        if line.startswith('event: '):
            event_type = line[7:]
        elif line.startswith('data: '):
            data = line[6:]
    event_type = _EVENT_NAME_MAP.get(event_type, event_type)
    return {'event': event_type, 'data': data}


def verify_jwt_token(token: str) -> Optional[dict]:
    """Verify a bearer JWT and return its claims, or None if invalid."""
    try:
        secret = get_jwt_secret()
        return jwt.decode(token, secret, algorithms=['HS256'], options={'verify_exp': True})
    except jwt.ExpiredSignatureError:
        logger.warning('JWT token expired')
    except jwt.InvalidTokenError as e:
        logger.warning(f'Invalid JWT token: {e}')
    except Exception as e:
        logger.error(f'JWT verification error: {e}')
    return None


class JWTAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        auth_header = request.headers.get('authorization') or request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return JSONResponse({'error': 'Missing or invalid Authorization header'}, status_code=401)

        claims = verify_jwt_token(auth_header[7:])
        if not claims:
            return JSONResponse({'error': 'Invalid or expired token'}, status_code=401)

        request.state.user_claims = claims
        request.state.user_id = claims.get('user_id', 'anonymous')
        return await call_next(request)


app.add_middleware(JWTAuthMiddleware)


@app.get('/health')
async def health() -> Response:
    return JSONResponse({'status': 'ok'}, status_code=200)


@app.post('/')
async def followup(request: Request) -> Response:
    body_bytes = await request.body()
    event = {
        'body': body_bytes.decode('utf-8'),
        'isBase64Encoded': False,
        'headers': dict(request.headers),
        'requestContext': {'http': {'method': 'POST'}},
    }
    user_id = getattr(request.state, 'user_id', 'anonymous')

    sync_gen = stream_followup_response(event, None, user_id)
    # Discard the first yield (Lambda Function URL response metadata).
    try:
        next(sync_gen)
    except StopIteration:
        return JSONResponse({'error': 'No response from upstream handler'}, status_code=500)

    async def event_stream():
        async_iter = iterate_in_threadpool(sync_gen)
        try:
            async for chunk in async_iter:
                if isinstance(chunk, str):
                    yield _parse_sse_chunk(chunk)
                elif isinstance(chunk, dict):
                    yield chunk
                # Otherwise drop silently — should not happen per handler contract.
        except (GeneratorExit, asyncio.CancelledError):
            logger.info('Client disconnected; closing upstream stream')
            try:
                sync_gen.close()
            except Exception:
                pass
            raise
        except Exception as e:
            logger.error(f'Error while streaming followup response: {e}', exc_info=True)
            raise

    return EventSourceResponse(event_stream())
