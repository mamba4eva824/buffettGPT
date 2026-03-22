# Phase 5: Market Intelligence Frontend Tab — GSD Prompt

Use this prompt to plan and implement the new "Market Intelligence" tab in the frontend, combining a chat interface with the Bedrock agent and integrated data visualizations.

---

## Goal

Add a new "Market Intelligence" tab/mode to the React frontend that provides:
1. A chat interface for querying the Market Intelligence Bedrock agent
2. Structured response rendering (tables, rankings, sector comparisons)
3. Guided query starters for common market analysis questions
4. Subscription gating with upgrade CTA for non-subscribers

---

## GSD Step 1: Audit Snapshot

### Knowns / Evidence

| What | Where | Details |
|------|-------|---------|
| App mode system | `frontend/src/App.jsx` | `appMode` state switches between `'chat'` and `'value-insights'`. Tab-like navigation in header. |
| Value Insights components | `frontend/src/components/value-insights/` | CategoryPanels, panelMap, mockData with financial data rendering. Uses Tailwind. Charts and data cards. |
| ResearchContext | `frontend/src/contexts/ResearchContext.jsx` | Complex state management for SSE streaming, follow-up chat, section tracking. Uses `useReducer`. |
| Follow-up chat streaming | `ResearchContext.jsx` | Calls Lambda Function URL with fetch + ReadableStream. Parses SSE events: `message_start`, `content_block_delta`, `message_stop`. |
| Company search hook | `frontend/src/hooks/useCompanySearch.js` | Autocomplete for ticker/company search. Calls backend API. |
| Subscription management | `frontend/src/components/SubscriptionCard.jsx` | Shows current tier, upgrade button, calls `/subscription/checkout`. |
| Mobile drawer | `frontend/src/components/MobileDrawer.jsx` | Responsive mobile navigation. |
| Tailwind config | `frontend/tailwind.config.js` | Extended theme with custom colors, fonts. Dark mode support. |
| mockData schema | `frontend/src/components/value-insights/mockData.js` | Normalized DynamoDB metrics → dashboard schema. 9 categories. Format helpers (billions, pct, ratio, etc.). |
| Stripe API client | `frontend/src/api/stripeApi.js` | `createCheckoutSession(plan)`, `getSubscriptionStatus()`. |
| Auth context | `frontend/src/auth.jsx` | Google OAuth, JWT management, user state. Subscription tier accessible. |
| Vite env vars | `frontend/.env.*` | `VITE_ANALYSIS_FOLLOWUP_URL` pattern for Lambda Function URLs. |

### Unknowns / Gaps

1. **Charting library**: Value Insights appears to use custom Tailwind components for data display. Do we need a charting library (Recharts, Chart.js) for market intelligence visualizations, or can we build with Tailwind + CSS?
2. **Response format**: How does the Bedrock agent return structured data vs text? The follow-up agent returns plain text. Market intelligence needs structured data for rendering tables/charts. Options: JSON blocks in markdown, or custom response parsing.
3. **Session management**: Does the market intelligence chat maintain conversation history? The existing chat stores in DynamoDB. Market intelligence may need lighter sessions (just Bedrock session ID).
4. **Mobile responsiveness**: The existing app has mobile support via MobileDrawer. The new tab needs to work on mobile too.

### Constraints

- React 18 + Vite 5 + Tailwind 3. No additional frameworks.
- ESLint with 0 warnings policy (`npm run lint` must pass).
- Frontend env vars prefixed with `VITE_`.
- Auth + subscription check client-side before making API calls.
- Responsive design (mobile + desktop).

### Risks

1. **Structured response parsing**: If the agent returns free-text, we can't render rich visualizations. Need a convention: agent wraps data in ```json blocks, frontend extracts and renders.
2. **Chat + visualization layout complexity**: Two-panel layout (chat + data viz) is significantly more complex than the current single-panel chat.
3. **Bundle size**: Adding a charting library could increase bundle size. Consider dynamic imports.

---

## GSD Step 2: PRD — Acceptance Criteria

```
AC-1: Given the app loads, when the user sees the navigation, then there are 3 tabs/modes:
      "Chat", "Value Insights", and "Market Intelligence".

AC-2: Given a non-authenticated user clicks "Market Intelligence" tab, when the tab loads,
      then they see a login prompt ("Sign in to access Market Intelligence").

AC-3: Given an authenticated user WITHOUT Market Intelligence subscription, when they click
      the tab, then they see an upgrade CTA with pricing ($10/month) and a "Subscribe" button
      that redirects to Stripe Checkout.

AC-4: Given a subscribed user opens Market Intelligence, when the tab loads, then they see:
      - A chat input at the bottom
      - 6-8 suggested query cards/buttons above the input
      - An empty response area ready for results

AC-5: Given a subscribed user types "Top 10 companies by FCF margin" and submits, when the
      response streams in, then the chat shows a text explanation AND a structured table
      with company names, tickers, and FCF margin values.

AC-6: Given a response includes sector comparison data, when rendered, then a visual
      comparison (table or bar chart) is displayed alongside the text explanation.

AC-7: Given the user is on mobile (viewport <768px), when viewing Market Intelligence,
      then the layout adapts to single-column with chat input always visible.

AC-8: Given the frontend is built, when running `npm run lint`, then 0 warnings are reported.

AC-9: Given the chat has history, when the user asks a follow-up question, then the
      Bedrock agent receives the session context and can reference prior answers.
```

---

## GSD Step 3: Implementation Plan

### Objective
Build the "Market Intelligence" tab with a chat interface, structured response rendering, and subscription gating.

### Approach Summary
Add a new `appMode: 'market-intelligence'` alongside the existing modes. Create a `MarketIntelligence` component tree with: a `MarketIntelChat` for the chat interface, `MarketIntelResponse` for structured data rendering, and `MarketIntelSuggestions` for guided query starters. Create a `MarketIntelContext` (following `ResearchContext` pattern) for SSE streaming and state management. Gate access with subscription check in the component.

### Steps

1. **Add environment variable for Market Intelligence API**
   - `VITE_MARKET_INTEL_URL` — Lambda Function URL for market intel agent
   - Add to `.env.development`, `.env.production`, Vite config

2. **Create MarketIntelContext**
   - File: `frontend/src/contexts/MarketIntelContext.jsx`
   - State: messages (array), isStreaming, sessionId, error
   - Actions: sendMessage, clearChat, setSessionId
   - SSE streaming: follow `ResearchContext` pattern — fetch to Lambda Function URL, parse ReadableStream
   - Parse agent responses: extract ```json blocks for structured data, keep text for explanation

3. **Create MarketIntelligence main component**
   - File: `frontend/src/components/market-intelligence/MarketIntelligence.jsx`
   - Subscription gate: check user's subscription tiers
   - If not authenticated → login prompt
   - If no subscription → upgrade CTA with pricing card
   - If subscribed → render chat interface

4. **Create MarketIntelChat component**
   - File: `frontend/src/components/market-intelligence/MarketIntelChat.jsx`
   - Chat input with submit button (same style as main chat)
   - Message list: user messages + agent responses
   - Streaming indicator
   - Auto-scroll to latest message

5. **Create MarketIntelSuggestions component**
   - File: `frontend/src/components/market-intelligence/MarketIntelSuggestions.jsx`
   - Grid of clickable suggestion cards:
     - "Top 10 S&P 500 by FCF margin"
     - "Which sectors have improving margins?"
     - "Compare FAANG profitability"
     - "Companies with declining debt levels"
     - "S&P 500 index health overview"
     - "Best dividend growth stocks"
     - "Tech sector deep dive"
     - "Companies with strongest cash flow"
   - Clicking a card populates the chat input and submits

6. **Create structured response renderers**
   - File: `frontend/src/components/market-intelligence/ResponseRenderers.jsx`
   - `RankingTable` — for getTopCompanies results (rank, ticker, company, metric value)
   - `SectorComparisonTable` — for getSectorOverview (sector name, median metrics, company count)
   - `CompanyProfileCard` — for getCompanyProfile (company info + key metrics + sector rank)
   - `ComparisonGrid` — for compareCompanies (side-by-side metric cards)
   - `IndexSnapshotCard` — for getIndexSnapshot (overall health indicators)
   - Each renderer receives parsed JSON data and uses format helpers from `mockData.js`

7. **Create response parser utility**
   - File: `frontend/src/utils/marketIntelParser.js`
   - Parse agent response text for embedded JSON blocks: ` ```json\n{...}\n``` `
   - Extract `response_type` field from JSON to determine which renderer to use
   - Return `{ text: "...", structuredData: {...}, responseType: "ranking"|"sector"|"comparison"|... }`

8. **Create subscription gate component**
   - File: `frontend/src/components/market-intelligence/MarketIntelGate.jsx`
   - Check subscription status via `stripeApi.getSubscriptionStatus()`
   - Render upgrade CTA: product description, $10/month pricing, subscribe button
   - Subscribe button calls `stripeApi.createCheckoutSession('market_intelligence')`

9. **Update App.jsx**
   - Add `'market-intelligence'` to appMode options
   - Add tab in navigation header
   - Lazy-load MarketIntelligence component
   - Add MarketIntelContext provider

10. **Update navigation for 3 tabs**
    - Desktop: horizontal tab bar with "Chat", "Value Insights", "Market Intelligence"
    - Mobile: update MobileDrawer with new option
    - Active tab styling

11. **Responsive layout**
    - Desktop: full-width chat with structured responses inline
    - Mobile: single column, input pinned to bottom
    - Breakpoints matching existing Tailwind config

### Files to Create/Modify

| File | Change |
|------|--------|
| `frontend/src/components/market-intelligence/MarketIntelligence.jsx` | **NEW** — main component |
| `frontend/src/components/market-intelligence/MarketIntelChat.jsx` | **NEW** — chat interface |
| `frontend/src/components/market-intelligence/MarketIntelSuggestions.jsx` | **NEW** — query starters |
| `frontend/src/components/market-intelligence/ResponseRenderers.jsx` | **NEW** — structured data rendering |
| `frontend/src/components/market-intelligence/MarketIntelGate.jsx` | **NEW** — subscription gate + CTA |
| `frontend/src/contexts/MarketIntelContext.jsx` | **NEW** — state management + SSE streaming |
| `frontend/src/utils/marketIntelParser.js` | **NEW** — response parsing utility |
| `frontend/src/App.jsx` | Add market-intelligence mode, tab navigation, context provider |
| `frontend/src/components/MobileDrawer.jsx` | Add Market Intelligence option |
| `frontend/src/api/stripeApi.js` | Add market_intelligence plan support |
| `frontend/.env.development` | Add `VITE_MARKET_INTEL_URL` |
| `frontend/vite.config.js` | Verify env var handling |

### Verification Commands

```bash
# Lint
cd frontend && npm run lint

# Dev server
cd frontend && npm run dev
# Then manually verify:
# 1. Three tabs visible
# 2. Non-auth shows login prompt
# 3. Auth without subscription shows upgrade CTA
# 4. Mock/test subscription shows chat interface
# 5. Suggested queries are clickable
# 6. Responsive at 375px, 768px, 1280px

# Production build
cd frontend && npm run build
```

---

## GSD Step 4: Task Graph

```
Task 1: Create MarketIntelContext with SSE streaming
  Dependencies: Phase 4 (API endpoint exists — can mock for dev)
  Files: contexts/MarketIntelContext.jsx
  Verify: npm run lint

Task 2: Create response parser utility
  Dependencies: none
  Files: utils/marketIntelParser.js
  Verify: npm run lint

Task 3: Create MarketIntelGate (subscription check + upgrade CTA)
  Dependencies: none
  Files: components/market-intelligence/MarketIntelGate.jsx
  Verify: npm run lint

Task 4: Create MarketIntelSuggestions (query starter cards)
  Dependencies: none
  Files: components/market-intelligence/MarketIntelSuggestions.jsx
  Verify: npm run lint

Task 5: Create ResponseRenderers (tables, cards, comparisons)
  Dependencies: Task 2 (parser)
  Files: components/market-intelligence/ResponseRenderers.jsx
  Verify: npm run lint

Task 6: Create MarketIntelChat (chat interface + message rendering)
  Dependencies: Task 1 (context), Task 2 (parser), Task 5 (renderers)
  Files: components/market-intelligence/MarketIntelChat.jsx
  Verify: npm run lint

Task 7: Create MarketIntelligence main component (orchestrator)
  Dependencies: Task 3, Task 4, Task 6
  Files: components/market-intelligence/MarketIntelligence.jsx
  Verify: npm run lint

Task 8: Update App.jsx with new tab + mode + context provider
  Dependencies: Task 7
  Files: App.jsx, MobileDrawer.jsx
  Verify: npm run lint && npm run build

Task 9: Add environment variables + update stripeApi.js
  Dependencies: none
  Files: .env.development, api/stripeApi.js
  Verify: npm run lint

Task 10: Responsive testing + polish
  Dependencies: Task 8
  Files: various component adjustments
  Verify: npm run lint && manual responsive check

Task 11: End-to-end visual QA
  Dependencies: all above + Phases 1-4 deployed
  Files: none (manual testing)
  Verify: full user flow in browser
```

---

## GSD Step 5: Self-Critique / Red Team

### Fragile assumptions
- **Agent returns parseable structured data**: The biggest risk. If the Bedrock agent doesn't consistently wrap data in ```json blocks with a `response_type` field, the frontend can't render rich visualizations. Mitigation: the agent prompt (Phase 3) must explicitly instruct this format. Fallback: render all responses as plain text (graceful degradation).
- **Format helpers reuse**: Assumes `mockData.js` format helpers (`fmt.billions`, `fmt.pct`, etc.) can be extracted to a shared utility. Currently they're co-located with mock data.

### Failure modes
- **Streaming breaks mid-response**: If the Lambda or Bedrock agent errors mid-stream, the frontend shows partial text. Need error handling in the SSE parser (follow ResearchContext pattern which handles this).
- **Large response rendering**: A screenStocks result with 50 companies could render a very long table. Add virtual scrolling or pagination for large result sets.
- **Subscription status caching**: If subscription check is too aggressive (every render), it's slow. If too lax (once on mount), user might lose access mid-session. Cache for 5 minutes with refetch on focus.

### Simplest 80% version
Start with chat-only (no structured renderers). Just render agent responses as markdown text. This works immediately with no parsing logic. Then add ResponseRenderers as a fast follow once the agent response format is stabilized. The suggested query cards + chat input + streaming response covers 80% of the value.

### Key Design Decision: Layout
Two viable approaches:
- **Option A**: Full-page chat (like existing chat mode) — simpler, familiar, mobile-friendly
- **Option B**: Split-panel (chat left, visualization right) — richer but complex, needs desktop-only layout

Recommend **Option A** for MVP with structured responses rendered inline in the chat flow (like how ChatGPT renders tables inline). Option B can be a future enhancement.
