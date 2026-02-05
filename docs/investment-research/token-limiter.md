# Token Limiter System

The token limiter manages context window usage to prevent exceeding model limits.

## Overview

Claude models have finite context windows. The token limiter:

- Tracks token usage across requests
- Enforces per-request limits
- Provides usage analytics

## How It Works

### Token Counting

Tokens are counted before sending to Bedrock:

```python
from investment_research.token_limiter import TokenLimiter

limiter = TokenLimiter(max_tokens=100000)
token_count = limiter.count_tokens(prompt_text)

if limiter.would_exceed_limit(token_count):
    # Truncate or summarize content
    pass
```

### Budget Management

The system allocates token budgets for:

| Component | Budget |
|-----------|--------|
| System Prompt | ~2,000 tokens |
| Report Content | ~20,000 tokens |
| User Question | ~500 tokens |
| Response | ~4,000 tokens |

## Configuration

Token limits are configured per endpoint:

```python
TOKEN_LIMITS = {
    'followup': 100000,  # Follow-up Q&A
    'report_generation': 150000,  # Full report generation
}
```

## Analytics

The limiter tracks usage for optimization:

- Average tokens per request
- Peak usage times
- Truncation frequency

## Related

- [Follow-up Agent](followup-agent.md)
- [Context Management](../architecture/context-management.md)
