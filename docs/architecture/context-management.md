# Context Management

This document covers Bedrock agent context and memory management strategies.

## Overview

Bedrock agents maintain conversation context across turns. Effective context management is crucial for:

- Multi-turn conversations
- Accurate follow-up responses
- Token budget optimization

## Context Window

Claude models have finite context windows. The system manages context by:

1. **Session Memory** - Maintains conversation history within a session
2. **Selective Retrieval** - Fetches only relevant report sections
3. **Token Budgeting** - Limits context size to prevent truncation

## Memory Strategies

### Session-Based Memory

Each conversation session maintains its own memory:

- User questions and agent responses
- Retrieved report sections
- Conversation metadata

### Retrieval Augmentation

The action group Lambda retrieves context on-demand:

- Report sections fetched per question
- Historical metrics queried as needed
- Ratings retrieved once per session

## Token Optimization

To stay within context limits:

1. **Chunk responses** - Stream in 256-char chunks
2. **Lazy loading** - Load sections only when referenced
3. **Summarization** - Condense long responses

## Related

- [Token Limiter](../investment-research/token-limiter.md)
- [Follow-up Agent](followup-agent.md)
