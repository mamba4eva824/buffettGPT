# Stitch Prompt: Buffett Market Intelligence Chat

## What I'm Building

An AI-powered **"Market Intelligence"** chat interface for an existing Warren Buffett-themed financial advisor app called Buffett. This is the third tab in the app (alongside "Chat" and "Value Insights"). It provides a conversational interface where users ask natural-language questions about S&P 500 companies, and the AI agent responds with both text explanations and **rich structured data** rendered inline — tables, company profiles, metric trends, and sector comparisons.

The agent has **9 specialized tools** that query a database containing 5 years (20 quarters) of financial data for all ~500 S&P 500 companies. The UI must do more than show plain text — it should **guide users** with suggestion cards that teach what the agent can do, and **render structured financial data** beautifully alongside conversational explanations.

**Design ethos**: Like having a Bloomberg terminal that speaks plain English — data-dense yet approachable, professional yet warm.

---

## The 9 Agent Tools (What the AI Can Do)

These tools determine what kinds of responses the UI must render:

| # | Tool | What it does | Example query | Response type |
|---|------|-------------|---------------|---------------|
| 1 | `getTopCompanies` | Rank companies by any metric | "Top 10 by FCF margin" | Rankings table |
| 2 | `screenStocks` | Filter companies by metric thresholds | "Companies with >30% operating margin in tech" | Filtered results table |
| 3 | `getSectorOverview` | Sector-level medians and top companies | "How is the tech sector doing?" | Sector summary card |
| 4 | `getIndexSnapshot` | Overall S&P 500 health indicators | "How is the S&P 500 doing?" | Index health dashboard |
| 5 | `getCompanyProfile` | Deep dive on a single company | "Tell me about NVDA" | Company profile card |
| 6 | `compareCompanies` | Side-by-side comparison of 2-10 companies | "Compare AAPL vs MSFT vs GOOGL" | Comparison grid |
| 7 | `getMetricTrend` | 20-quarter trend of one metric for one company | "How has AAPL's margin changed over 5 years?" | Trend line chart |
| 8 | `getEarningsSurprises` | Biggest earnings beats or misses | "Who had the biggest earnings beats?" | Earnings table |
| 9 | `compareSectors` | Side-by-side sector medians | "Compare tech vs healthcare profitability" | Sector comparison table |

---

## Design System

### Color Palette

**Dark mode (primary)**:
- Canvas/background: `#1a1815` (deep warm charcoal)
- Card surfaces: `#211f1c` (slightly elevated)
- Elevated surfaces: `#2c2925`
- Borders: `#363330`
- Primary text: `#e8e6e3` (warm off-white)
- Secondary text: `#b5b0a8`
- Muted/placeholder text: `#9a9590`
- **Accent gold**: `#f2c35b` (primary accent — icons, highlights, active states)
- Positive/success: `#a0d6ad` (sage green)
- Negative/warning: `#ffb4ab` (soft rose)
- CTA/upgrade buttons: `#4f46e5` (indigo-600)

**Light mode**:
- Canvas: `#faf8f5` (warm white)
- Card surfaces: `#f5f2ed`
- Borders: `#e8e4de`
- Primary text: `#2d2923`
- Secondary text: `#5c5750`
- Same accent colors

### Typography
- **Headings & hero values**: Serif font (Playfair Display or Georgia) — classic, authoritative
- **Body, labels, data**: Sans-serif (Inter or system-ui) — clean, modern
- **Financial figures**: Tabular/monospace numbers for alignment in tables
- **Category labels**: 10px uppercase bold with wide letter-spacing

### Component Style
- Rounded corners: 12px on cards (rounded-xl), 8px on buttons/inputs (rounded-lg)
- Subtle borders, no heavy drop shadows
- Generous whitespace inside cards (32px padding)
- Data tables: alternating subtle row shading, right-aligned numeric columns
- Rating badges: pill-shaped — Strong (sage green), Moderate (gold), Weak (rose)
- Hover states: subtle background lift + gold accent border

### Overall Feel
- Warm, professional, premium — like a private wealth management report
- Data-rich but never cluttered
- Not startup-flashy, not corporate-sterile
- Sophisticated color hierarchy that guides the eye to important data

---

## Screens to Design

---

### Screen 1: Welcome / Empty State (Subscribed User)

What a subscribed user sees when they first open the Market Intelligence tab, before sending any messages.

**Layout**: Full-width single column. Content vertically centered with breathing room.

**Top section**:
- Analytics/chart icon in gold accent
- Title: **"Market Intelligence"** (serif, large)
- Subtitle: "Query 5 years of financial data across 500 S&P 500 companies. Just ask a question." (secondary text color, sans-serif)

**Suggestion cards** (center of screen, primary discovery mechanism):

A 2×4 grid of clickable cards on desktop. Each card has:
- A small icon (left-aligned or top) in gold accent color
- Query text in primary text color (the actual question the user would ask)
- Cards have a subtle border (warm-700 in dark mode), slight background elevation
- **Hover**: gold border, slight background lift, pointer cursor

The 8 suggestions, each mapping to a different tool capability:

| Icon | Card text |
|------|-----------|
| Trending up (bar chart) | "Top 10 S&P 500 companies by free cash flow margin" |
| Pie chart / sectors | "Which sectors have the best profitability?" |
| Filter / funnel | "Companies with >30% operating margin in tech" |
| Building / profile | "Deep dive on NVIDIA (NVDA)" |
| Columns / compare | "Compare AAPL, MSFT, and GOOGL side by side" |
| Activity / pulse | "How healthy is the S&P 500 right now?" |
| Timeline / line chart | "How has Apple's margin changed over 5 years?" |
| Zap / lightning | "Biggest earnings surprises this quarter" |

**Chat input** (fixed to bottom of viewport):
- Full-width input bar with rounded-xl corners
- Placeholder text: "Ask about any S&P 500 company..."
- Send button on right side (gold accent icon)
- Subtle border, elevated slightly from canvas background

---

### Screen 2: Chat with Rankings Table Response

User asked: **"Top 10 companies by free cash flow margin"**

The AI responded with text + a structured rankings table.

**Chat layout**: Messages flow top-to-bottom. User messages right-aligned, AI messages left-aligned and wider.

**User message** (right side):
- Text in a compact bubble with warm-800 background (dark mode)
- Rounded corners, slight padding
- Timestamp below in muted text (optional)

**AI message** (left side, nearly full width):
- **Text block first** (2-3 sentences): "Here are the top 10 S&P 500 companies ranked by free cash flow margin. These companies generate the highest proportion of free cash flow relative to revenue, indicating exceptional cash conversion efficiency."
- **Rankings table** (below the text, inline):

| Rank | Ticker | Company | FCF Margin |
|------|--------|---------|------------|
| 1 | NVDA | NVIDIA Corp | 48.2% |
| 2 | V | Visa Inc | 42.1% |
| 3 | MSFT | Microsoft Corp | 35.7% |
| 4 | MA | Mastercard Inc | 34.8% |
| 5 | AAPL | Apple Inc | 28.5% |
| 6 | ADBE | Adobe Inc | 27.3% |
| 7 | INTU | Intuit Inc | 26.1% |
| 8 | META | Meta Platforms | 25.4% |
| 9 | AVGO | Broadcom Inc | 24.8% |
| 10 | ORCL | Oracle Corp | 23.9% |

Table styling:
- Rank numbers in gold accent color
- Ticker in bold
- FCF Margin right-aligned
- Alternating row backgrounds (very subtle)
- Row hover: highlight background
- Header row: uppercase tiny labels, muted color, heavier border below

**Follow-up suggestion chips** (below the AI response):
Small pill-shaped buttons with gold/muted border:
- "Compare the top 3 by all metrics"
- "Which sectors do these belong to?"
- "Deep dive on NVDA"

**Chat input** (still fixed at bottom)

---

### Screen 3: Chat with Company Profile Response

User asked: **"Tell me about NVDA"**

**AI message** contains a rich company profile card:

**Company header section**:
- Large ticker badge: "NVDA" — gold background, dark text, rounded pill
- Company name: "NVIDIA Corporation" — serif, large
- Sector/Industry path: "Technology > Semiconductors" — muted text
- Quick stats row (horizontal): Market Cap · Revenue · FCF — in small labeled chips

**Key metrics grid** (2×3 bento tiles):
Each tile is a small card showing:
- Label: uppercase tiny bold muted text (e.g., "OPERATING MARGIN")
- Value: large serif number (e.g., "48.2%")
- Delta indicator: small green up-arrow or red down-arrow showing QoQ change
- Optional mini sparkline in the corner (subtle, decorative)

Six tiles for: Operating Margin, FCF Margin, Revenue Growth, ROE, Debt-to-Equity, EPS Surprise

**Sector ranking context** (below the grid):
- "Ranked **#1** in Technology sector for FCF margin"
- "Above sector median (12.3%) by 35.9 percentage points"
- A visual horizontal bar showing company's position vs sector median — company value as a gold dot, sector median as a line

---

### Screen 4: Chat with Sector Comparison Response

User asked: **"Compare tech vs healthcare vs energy profitability"**

**AI text**: Brief 2-3 sentence analysis of how the sectors compare.

**Sector comparison** — could be rendered as either:

**Option A — Comparison table** (cleaner for data):

| Metric | Technology | Healthcare | Energy |
|--------|-----------|------------|--------|
| Operating Margin | 23.4% | 18.7% | 14.2% |
| FCF Margin | 19.8% | 15.2% | 11.4% |
| Revenue Growth | 12.1% | 8.4% | 5.7% |
| ROE | 28.5% | 22.1% | 16.8% |
| Debt-to-Equity | 1.2 | 1.8 | 0.9 |

- Best value in each row highlighted with gold/green accent
- Header row uses sector names as column headers

**Option B — Three side-by-side cards** (more visual):
Each card:
- Sector name as header (serif font)
- Performance badge: "Strong" / "Moderate" / "Weak" (pill-shaped, color coded)
- Key metrics listed vertically with values
- Top 3 companies in that sector listed below
- Company count: "72 companies"

**Follow-up chips**: "Which tech companies lead?", "Show healthcare sector details", "Compare margins over time"

---

### Screen 5: Chat with Metric Trend Response

User asked: **"How has Apple's operating margin changed over 5 years?"**

**AI text**: "Apple's operating margin has remained remarkably stable over the past 5 years, trending slightly upward from 29.8% to 31.2%. The margin expanded meaningfully in 2022-2023 as services revenue grew."

**Trend chart** (inline):
- An area/line chart showing 20 quarterly data points
- X-axis: fiscal quarters (labeled by year)
- Y-axis: operating margin percentage
- Solid gold line for actual values
- Dashed line for 4-quarter rolling average
- Subtle shaded area under the line
- Current value called out: "Current: 31.2%"
- CAGR or trend direction indicator

Chart styling:
- Subtle grid lines
- Clean axis labels in muted text
- Data points as small dots on the line
- Legend below: "Quarterly" (solid line) and "4Q Average" (dashed)

---

### Screen 6: Chat with Earnings Surprises Response

User asked: **"Who had the biggest earnings beats this quarter?"**

**AI text**: "Here are the companies that exceeded analyst EPS estimates by the widest margins."

**Earnings table**:

| Rank | Ticker | Company | Actual EPS | Est. EPS | Surprise |
|------|--------|---------|-----------|---------|----------|
| 1 | NVDA | NVIDIA Corp | $5.16 | $4.64 | +11.2% |
| 2 | META | Meta Platforms | $6.03 | $5.25 | +14.9% |
| 3 | AMZN | Amazon.com | $1.43 | $1.14 | +25.4% |

- Surprise column: green for beats, red for misses
- Positive surprises prefixed with "+"
- Beat/miss icon (checkmark/x) next to the surprise value

---

### Screen 7: Subscription Gate (Non-Subscriber)

An authenticated user who doesn't have a Market Intelligence subscription.

**Layout**: The suggestion cards and chat input are visible but dimmed/blurred behind an overlay.

**Upgrade card** (centered, overlaying the blurred background):
- Crown or unlock icon in indigo
- Title: **"Unlock Market Intelligence"** (serif)
- Subtitle: "AI-powered analysis of every S&P 500 company with 5 years of financial data."
- Feature list with checkmark icons:
  - "Rank and screen 500 companies by any metric"
  - "Compare companies and sectors side-by-side"
  - "Track metric trends over 20 quarters"
  - "Earnings surprise analysis"
  - "Natural language — just ask a question"
- Price: **"$10/month"** — large, prominent
- CTA button: **"Subscribe Now"** — full width, indigo background, white text, rounded-lg
- Fine print: "Cancel anytime. 7-day free trial." — muted small text

---

### Screen 8: Mobile Layout (375px viewport)

Same chat experience as Screens 2-6, adapted for mobile:

**Adaptations**:
- Suggestion cards: horizontal scrollable row (1 card height, swipeable left/right) instead of 2×4 grid
- Chat input: pinned to bottom with safe-area padding for iOS
- Tables: horizontally scrollable with a subtle scroll shadow/indicator on the right edge
- Company profile bento tiles: 2×2 grid then 1-column stacking
- Follow-up chips: wrap to multiple lines
- Reduced padding throughout (16px instead of 32px)
- Charts: full width, slightly shorter height

---

### Screen 9: Streaming / Loading State

User has submitted a query. The AI is generating a response.

**Elements**:
- User message appears immediately (right-aligned)
- AI response area shows:
  - A subtle typing/thinking indicator (3 animated dots or a gentle pulse animation)
  - Text streams in progressively (word by word or chunk by chunk)
  - Structured data (table, chart, card) fades in after text is complete
- Send button in input bar: disabled state with a small spinner
- Below the streaming response: a "Stop generating" text button (muted, small)

---

### Screen 10: Index Snapshot Response

User asked: **"How healthy is the S&P 500 right now?"**

**AI text**: Overview of the index's current state.

**Index snapshot card** — a dashboard-style summary:
- Header: "S&P 500 Index Health" with a pulse/heartbeat icon
- Grid of health indicators (3×2 bento tiles):
  - "Median Operating Margin" — 14.2%
  - "Median Revenue Growth" — 6.8%
  - "Median FCF Margin" — 11.4%
  - "Median D/E Ratio" — 1.3
  - "Companies Profitable" — 467/500
  - "Earnings Beat Rate" — 72%
- Each tile with a directional indicator (improving/declining vs prior quarter)
- Overall health rating badge: "Moderate" (gold pill badge)

---

## Component Reference

These are the reusable components the design should demonstrate:

1. **SuggestionCard** — Icon + query text, clickable, grid/scroll layout
2. **ChatInput** — Text input + send button, fixed to bottom
3. **UserBubble** — Right-aligned message bubble
4. **AIMessage** — Left-aligned, wider, contains text + structured data slots
5. **RankingsTable** — Ranked list with position, ticker, company, metric value
6. **CompanyProfileCard** — Header + bento metric tiles + sector ranking bar
7. **SectorComparisonGrid** — Multi-column table or side-by-side cards
8. **MetricTrendChart** — Area/line chart with 20 data points + rolling average
9. **EarningsTable** — Ranked list with beat/miss color coding
10. **IndexSnapshotCard** — Dashboard grid of health indicators
11. **FollowUpChips** — Row of contextual suggestion pills
12. **SubscriptionGate** — Blurred background + centered upgrade card
13. **StreamingIndicator** — Animated loading dots for AI typing state
14. **BentoTile** — Small metric card: label + value + delta + optional sparkline

---

## Interactions

- Clicking a suggestion card populates the chat input AND auto-submits the query (the card itself acts as the trigger)
- After each AI response, contextual follow-up chips appear based on the response content
- Clicking a follow-up chip auto-submits that query
- Tables have hover states on rows
- On mobile, suggestion cards are swipeable/scrollable horizontally
- Chat auto-scrolls to latest message as streaming content appears
- Transition from empty state → first message: suggestion cards slide up and away, chat message flow begins
- The chat should preserve scroll position when the user scrolls up to read history

---

## What NOT to Design

- Login/authentication screens (already exist in the app)
- The top-level tab navigation bar (already exists — we're just adding a third tab)
- Settings, profile, or account management pages
- The other two app modes (Chat and Value Insights)
- Backend API design or database schema
