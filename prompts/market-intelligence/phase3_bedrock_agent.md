# Phase 3: Market Intelligence Agent (Converse API + Tools) — GSD Prompt

Use this prompt to plan and implement the Market Intelligence agent using the Bedrock Converse API with inline tool definitions, SSE streaming, and token counting — matching the exact architecture of the existing follow-up agent.

---

## Goal

Create a new Lambda handler (`market_intel_chat.py`) that uses `converse_stream` with inline tool definitions to answer S&P 500 market analysis questions. The agent is named `market-intel-dev`, uses the same Converse API pattern as `analysis_followup.py`, and has its own tool set for screening, sector analysis, and cross-company queries.

---

## GSD Step 1: Audit Snapshot

### Knowns / Evidence

| What | Where | Details |
|------|-------|---------|
| Follow-up agent pattern | `chat-api/backend/src/handlers/analysis_followup.py` | Uses `converse_stream` (NOT `invoke_agent`). Manual orchestration loop with inline tool definitions. SSE streaming via Lambda Function URL with `RESPONSE_STREAM`. |
| Tool definition format | `analysis_followup.py:135-320` | Converse API `toolSpec` format — `name`, `description`, `inputSchema.json` with JSON Schema. NOT OpenAPI. |
| Tool executor pattern | `chat-api/backend/src/utils/tool_executor.py` | Routes tool names → Python functions → DynamoDB queries. Pure local execution, no Lambda invocation. |
| SSE streaming pattern | `analysis_followup.py:456-822` | First yield = `{statusCode, headers}`. Subsequent yields = `format_sse_event()` strings. Events: `chunk`, `complete`, `error`. |
| Token counting | `analysis_followup.py:688-693` | From `stream_event['metadata']['usage']`. Accumulated across orchestration turns. Written via `TokenUsageTracker`. |
| Orchestration loop | `analysis_followup.py:610-756` | `while turn_count < max_turns`: call converse_stream → stream text + accumulate tool calls → execute tools → append results → continue if `stopReason == 'tool_use'`. |
| Lambda Function URL | `modules/lambda/function_urls.tf` | `authorization_type = "NONE"`, `invoke_mode = "RESPONSE_STREAM"`, CORS configured. JWT validated inside Lambda. |
| Model | `analysis_followup.py:112` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` (Claude 4.5 Haiku via US cross-region inference). Configurable via env var. |
| metrics-history table | DynamoDB `metrics-history-dev` | 10,025 items. 498 S&P 500 tickers × 20 quarters. 9 categories per quarter. |
| sp500-aggregates table | DynamoDB `buffett-dev-sp500-aggregates` | 12 items. 11 sectors + 1 index overview with medians, top companies, earnings/dividend summaries. |
| SP500_SECTORS mapping | `investment_research/index_tickers.py` | 498 tickers with sector, industry, company name. |
| Bedrock Agent in Terraform | `modules/bedrock/main.tf` | Legacy — exists but NOT used by the follow-up handler. Do NOT create a Bedrock Agent resource for market-intel. |

### Unknowns / Gaps

1. **Separate tool_executor or shared?** The follow-up agent's `tool_executor.py` queries reports + metrics. The market intel agent needs different tools (screening, sectors, aggregates). Best to create a new `market_intel_tools.py`.
2. **Session/conversation memory**: The follow-up agent gets conversation history from the frontend. The market intel agent should follow the same pattern — messages passed in the request body.
3. **System prompt location**: Follow-up agent's system prompt is inline in Python (lines 522-601). Market intel agent should follow the same pattern.

### Constraints

- Use `converse_stream` with Converse API `toolSpec` format — NOT Bedrock Agents (`invoke_agent`).
- Agent name: `market-intel-dev`.
- Model: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (same as follow-up agent).
- All infrastructure via Terraform.
- Lambda packages in `chat-api/backend/build/`.
- SSE streaming via Lambda Function URL with `RESPONSE_STREAM`.
- Token counting via `TokenUsageTracker`.

### Risks

1. **Prompt engineering**: The market analysis persona needs careful tuning to use tools effectively and not hallucinate financial data.
2. **Tool response size**: Sector aggregates with top-5 companies and 14 metrics could be large. Need to keep tool responses concise.
3. **Orchestration turns**: Complex queries may require multiple tool calls. The follow-up agent caps at 10 turns — same limit is appropriate.

---

## GSD Step 2: PRD — Acceptance Criteria

```
AC-1: Given a deployed market-intel-dev Lambda, when invoked with "What sectors are performing
      best?", then the agent calls getSectorOverview, streams a response via SSE, and
      returns sector rankings with data citations.

AC-2: Given the agent, when asked "Show me companies with >20% FCF margin in tech",
      then the agent calls screenStocks with appropriate filters and returns matching
      companies with their FCF margin values.

AC-3: Given the agent, when asked "Top 10 companies by revenue growth",
      then the agent calls getTopCompanies and returns a ranked list.

AC-4: Given the agent, when asked "How is the S&P 500 doing overall?",
      then the agent calls getIndexSnapshot and returns index-level health metrics.

AC-5: Given the agent, when asked "Tell me about NVDA",
      then the agent calls getCompanyProfile and returns company + sector context.

AC-6: Given the agent, when asked "Compare AAPL and MSFT margins",
      then the agent calls compareCompanies and returns side-by-side data.

AC-7: Given the agent, when asked "How has NVDA's operating margin changed over 5 years?",
      then the agent calls getMetricTrend and returns 20 quarters of operating_margin values.

AC-8: Given the agent, when asked "Who had the biggest earnings beats this quarter?",
      then the agent calls getEarningsSurprises with sort=best and returns companies
      ranked by eps_surprise_pct.

AC-9: Given the agent, when asked "Compare tech vs healthcare profitability",
      then the agent calls compareSectors with those two sectors and returns
      side-by-side medians for margin metrics.

AC-10: Given streaming is enabled, when the agent responds, then SSE events are emitted:
      "chunk" (text deltas), "complete" (with token_usage), "error" (on failure).

AC-11: Given the agent completes a response, when checking token_usage in the "complete"
      event, then input_tokens and output_tokens are accurate counts from Bedrock metadata.

AC-12: Given the Lambda is deployed via Terraform, when running terraform plan, then
      the Lambda function, Function URL, and CloudWatch log group are managed as code.
```

---

## GSD Step 3: Implementation Plan

### Objective
Create a Lambda handler that uses `converse_stream` with 9 inline tools to answer S&P 500 market analysis questions, following the exact pattern of `analysis_followup.py`.

### Approach Summary
Create `market_intel_chat.py` by adapting the orchestration loop from `analysis_followup.py`. Define 9 tools in Converse API `toolSpec` format. Create `market_intel_tools.py` as the tool executor that queries `metrics-history` and `sp500-aggregates` tables. Write a market analysis system prompt. Add Terraform for the Lambda + Function URL.

### Steps

1. **Write the market analysis system prompt (inline in Python)**
   - Persona: Market analyst focused on S&P 500 data
   - Capabilities: Sector analysis, stock screening, rankings, comparisons, index health
   - Guidelines: Always cite data, explain metrics in plain English, flag data freshness
   - Tone: Professional, analytical, concise — not the Buffett persona
   - Include tool usage guidance (when to use which tool)

2. **Define 9 tools in Converse API `toolSpec` format**

   | Tool | Parameters | Source Table | Returns |
   |------|-----------|-------------|---------|
   | `screenStocks` | `metric`, `operator`, `value`, `sector` (optional), `limit` | metrics-history | Matching companies with metric values |
   | `getSectorOverview` | `sector` (optional — all if omitted) | sp500-aggregates | Sector medians, top companies, earnings/dividend summary |
   | `getTopCompanies` | `metric`, `n` (default 10), `sector` (optional) | metrics-history | Ranked company list |
   | `getIndexSnapshot` | none | sp500-aggregates | Overall S&P 500 health metrics |
   | `getCompanyProfile` | `ticker` | metrics-history + sp500-aggregates | Company metrics + sector context + rank |
   | `compareCompanies` | `tickers` (2-10), `metric_type` | metrics-history | Side-by-side metrics |
   | `getMetricTrend` | `ticker`, `metric`, `category`, `quarters` (default 20) | metrics-history | Quarterly trajectory of a metric for one company (e.g., 20 quarters of FCF margin) |
   | `getEarningsSurprises` | `sort` (`best`/`worst`), `n` (default 10), `sector` (optional) | metrics-history | Companies ranked by eps_surprise_pct — biggest beats or misses |
   | `compareSectors` | `sectors` (2-5), `metrics` (list of metric names) | sp500-aggregates | Side-by-side sector medians for selected metrics |

3. **Create `market_intel_tools.py` — tool executor**
   - Follow `tool_executor.py` pattern: `execute_tool(name, input) -> dict`
   - Each tool queries DynamoDB directly (no Lambda invocation)
   - `screenStocks`: Scan metrics-history, filter by metric threshold, sort + limit
   - `getSectorOverview`: Read SECTOR items from sp500-aggregates
   - `getTopCompanies`: Scan metrics-history for a metric, sort descending, take top N
   - `getIndexSnapshot`: Read INDEX/OVERALL from sp500-aggregates
   - `getCompanyProfile`: Query metrics-history for ticker + read sector aggregate for context
   - `compareCompanies`: Query metrics-history for each ticker
   - `getMetricTrend`: Query metrics-history for a single ticker, return N quarters of one metric (time series)
   - `getEarningsSurprises`: Scan metrics-history earnings_events, sort by eps_surprise_pct, return top N beats or worst N misses
   - `compareSectors`: Read multiple SECTOR items from sp500-aggregates, return side-by-side medians

4. **Create `market_intel_chat.py` — Lambda handler**
   - Adapt from `analysis_followup.py` orchestration loop
   - Use `converse_stream` with inline `MARKET_INTEL_TOOLS`
   - SSE streaming via generator pattern (first yield = headers)
   - Token counting from stream metadata
   - JWT validation for authenticated access
   - Subscription tier check (Phase 4 — for now, just require auth)
   - Session management: messages passed in request body

5. **Add Terraform infrastructure**
   - Lambda function entry in `lambda_configs` local (timeout: 120s, memory: 512MB)
   - `aws_lambda_function_url` with `invoke_mode = "RESPONSE_STREAM"` in `function_urls.tf`
   - Environment variables: `MARKET_INTEL_MODEL_ID`, `METRICS_HISTORY_CACHE_TABLE`, `SP500_AGGREGATES_TABLE`, `TOKEN_USAGE_TABLE`
   - Add to `build_lambdas.sh`

6. **Add output for frontend integration**
   - Lambda Function URL as Terraform output (needed by Phase 5 frontend)

### Files to Create/Modify

| File | Change |
|------|--------|
| `chat-api/backend/src/handlers/market_intel_chat.py` | **NEW** — Lambda handler with converse_stream orchestration loop |
| `chat-api/backend/src/utils/market_intel_tools.py` | **NEW** — Tool executor for market intelligence queries |
| `chat-api/terraform/modules/lambda/main.tf` | Add market_intel_chat Lambda config |
| `chat-api/terraform/modules/lambda/function_urls.tf` | Add Function URL with RESPONSE_STREAM |
| `chat-api/terraform/modules/lambda/outputs.tf` | Add market_intel_chat Function URL output |
| `chat-api/backend/scripts/build_lambdas.sh` | Add market_intel_chat to FUNCTIONS |

### Verification Commands

```bash
# Unit tests
cd chat-api/backend && make test

# Terraform validation
cd chat-api/terraform/environments/dev && terraform validate && terraform plan

# Build
cd chat-api/backend && ./scripts/build_lambdas.sh

# Local test (non-streaming, direct invocation)
python3 -c "
from src.handlers.market_intel_chat import lambda_handler
result = lambda_handler({
    'body': json.dumps({'message': 'What sectors have the best margins?'}),
    'requestContext': {'http': {'method': 'POST'}},
    'headers': {'authorization': 'Bearer <test-jwt>'}
}, None)
print(result)
"
```

---

## GSD Step 4: Task Graph

```
Task 1: Create market_intel_tools.py — tool executor with 9 tools
  Dependencies: Phase 2 complete (sp500-aggregates table populated)
  Files: src/utils/market_intel_tools.py
  Verify: unit tests pass
  Notes: 6 core tools (screenStocks, getSectorOverview, getTopCompanies,
         getIndexSnapshot, getCompanyProfile, compareCompanies) +
         3 intelligence tools (getMetricTrend, getEarningsSurprises, compareSectors)

Task 2: Create market_intel_chat.py — Lambda handler with converse_stream + SSE
  Dependencies: Task 1
  Files: src/handlers/market_intel_chat.py
  Verify: unit tests pass
  Notes: System prompt inline in Python. 9 tools defined in MARKET_INTEL_TOOLS dict.

Task 3: Add Terraform Lambda + Function URL + build pipeline
  Dependencies: Task 2
  Files: modules/lambda/main.tf, modules/lambda/function_urls.tf,
         modules/lambda/outputs.tf, scripts/build_lambdas.sh
  Verify: terraform validate && terraform plan && build zips

Task 4: Write unit tests for tools + handler
  Dependencies: Task 1, Task 2
  Files: tests/unit/test_market_intel_tools.py, tests/unit/test_market_intel_chat.py
  Verify: make test (all existing + new tests pass)

Task 5: Integration test against live DynamoDB
  Dependencies: Task 1
  Files: none (manual testing)
  Verify: invoke tools locally, verify correct data returned for all 9 tools

Task 6: Run evaluation queries against Claude Haiku 4.5 via converse API
  Dependencies: Task 2
  Files: none (evaluation script)
  Verify: Run 9+ representative queries (one per tool), capture:
    - Full agent response text
    - Which tool(s) were called and how many turns
    - Input tokens, output tokens, total tokens per query
    - Response latency

  Evaluation queries:
    1. "How is the S&P 500 doing overall?" → getIndexSnapshot
    2. "Show me the technology sector overview" → getSectorOverview
    3. "Compare tech vs healthcare vs energy profitability" → compareSectors
    4. "Top 10 companies by FCF margin" → getTopCompanies
    5. "Tell me about NVDA's position in the market" → getCompanyProfile
    6. "Compare AAPL, MSFT, and GOOGL margins" → compareCompanies
    7. "Companies with >30% operating margin in tech" → screenStocks
    8. "How has AAPL's revenue growth changed over 5 years?" → getMetricTrend
    9. "Who had the biggest earnings beats?" → getEarningsSurprises
    10. Multi-turn: "Show me tech sector" → "Now compare top 3 by FCF"

  Output: Token usage summary table for pricing evaluation
```

---

## GSD Step 5: Self-Critique / Red Team

### Fragile assumptions
- **screenStocks requires full table scan**: Filtering 500 tickers by arbitrary metric thresholds requires scanning metrics-history. At 10k items this is manageable (~5 seconds) but should be noted. Pre-computed rankings in sp500-aggregates handle the most common queries faster.
- **System prompt quality**: The market analysis persona needs extensive prompt engineering to route queries to the right tool. Include explicit tool selection guidance in the prompt.

### Failure modes
- **Agent calls wrong tool**: Mitigate with clear, non-overlapping tool descriptions and examples in the system prompt.
- **Large response truncation**: Cap `screenStocks` and `getTopCompanies` results at N items. Include "showing X of Y matches" in the response.
- **Token budget**: Multi-turn orchestration with large tool results could consume significant tokens. The `max_turns = 10` cap prevents runaway costs.

### Simplest 80% version
Start with 5 tools instead of 9: `getSectorOverview`, `getIndexSnapshot`, `getCompanyProfile`, `getTopCompanies`, `compareSectors`. These cover the most common market intelligence queries using data already in sp500-aggregates (fast reads, no scans). Add the remaining 4 (`screenStocks`, `compareCompanies`, `getMetricTrend`, `getEarningsSurprises`) as a fast follow — they require metrics-history scans and are more complex.

### Key Architecture Decisions (Already Made)
- **Converse API, not Bedrock Agents**: Uses `converse_stream` with inline tools for SSE streaming + token counting. No `invoke_agent`, no OpenAPI schemas, no action group Lambdas.
- **Inline system prompt**: System prompt lives in Python code, not Terraform, because `converse_stream` requires it at call time.
- **Separate tool executor**: `market_intel_tools.py` is separate from `tool_executor.py` to keep concerns clean. Different data sources (sp500-aggregates vs investment-reports).
- **Same model**: Claude 4.5 Haiku for cost efficiency, matching the follow-up agent.
