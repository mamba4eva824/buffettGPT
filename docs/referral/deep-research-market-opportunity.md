# Deep Research Prompt: Market Opportunity Analysis

Copy everything below the line into Claude Desktop's Deep Research mode.

---

## Research Request

I'm building a fintech app (working title: "Buffett AI") — an AI-powered financial research engine designed to make institutional-quality investment analysis accessible to everyday retail investors, specifically millennials and Gen Z (ages 22-40). I need comprehensive market research to validate the opportunity, understand the competitive landscape, and identify the strongest positioning for go-to-market.

### The Core Problem We Solve

Financial literacy is low, but interest in investing is at an all-time high. Young investors opened brokerage accounts in record numbers post-2020, but most lack the ability to read financial statements, interpret earnings reports, or evaluate whether a stock is fairly priced. They rely on Reddit threads, TikTok tips, and headline-driven trading.

Meanwhile, the tools that DO provide deep financial analysis (Bloomberg Terminal, FactSet, S&P Capital IQ) cost $20,000-$50,000/year and are designed for finance professionals. There's a massive gap between "Robinhood shows you a price chart" and "Bloomberg shows you everything but assumes you have an MBA."

**Buffett AI sits in that gap.** We translate complex financial data into plain English, visualize 5 years of fundamentals in interactive dashboards, and use AI to explain what the numbers mean — all through the lens of Warren Buffett's long-term value investing philosophy.

### Target Audience

**Segment 1 — Emerging Investors (acquisition base):**
- Millennials and Gen Z (22-35), $50-$500/month to invest
- May have student loans, building their first real portfolio
- Knows what stocks are, uses Robinhood/Fidelity/Schwab, but doesn't understand financial statements
- Pain point: "I want to invest smarter than just buying whatever's trending, but I don't know how to evaluate if a company is actually good"

**Segment 2 — Established Self-Directed Investors (higher-value target):**
- Millennials and older Gen Z (28-45), $1,000-$10,000+/month to invest
- Has a meaningful portfolio ($50K-$500K+), actively manages it, may have outgrown basic brokerage tools
- Understands some fundamentals but doesn't have time or expertise for deep financial statement analysis
- May be a high-earning professional (tech, medicine, law, finance-adjacent) who invests seriously but isn't a finance professional
- Pain point: "I have real money at stake and I want institutional-quality research without paying Bloomberg prices or spending hours on spreadsheets"

**Shared characteristics across both segments:**
- Prefers visual/conversational formats over raw spreadsheets
- Values transparency, education, and understanding *why* behind investment decisions
- Researches on phone and desktop, wants information that's both deep and accessible
- Distrusts hype-driven investing (meme stocks, crypto gambling) — wants a fundamentals-first approach

### Product — Four Integrated Modes

The app has four distinct modes that work together to give investors a complete picture:

#### Mode 1: Value Insights Dashboard
An interactive data visualization dashboard showing 5 years (20 quarters) of fundamental financial data across 8 analytical categories for any publicly traded company. Categories include Growth, Profitability, Valuation (with P/E deep dive), Earnings Performance, Cash Flow, Debt, Earnings Quality, and Dilution.

Key features:
- **Executive Summary tab** with a quick health check (report card format), AI-generated business analogy that explains the company in everyday terms, investment fit analysis, and decision triggers — all written in plain English. Note: we intentionally do NOT show BUY/HOLD/SELL ratings. The app empowers users with information and interpretation, not directives. Users make their own decisions.
- **Decision Triggers** — specific financial milestones that would signal a change in the company's trajectory (e.g., "If revenue growth drops below 5% for 2 consecutive quarters, reassess"). These are educational signals, not trading recommendations.
- **Interactive charts** with 1Y/3Y/5Y toggles, hover tooltips with exact values, color-coded trends (green = improving, red = declining)
- **Plain English translations** for every financial metric — "Free Cash Flow" becomes "Money Left Over," "Debt-to-Equity" becomes "How Much They Borrowed," "FCF Margin" becomes "What They Keep"
- **Per-tab AI chatbot** — every tab in the dashboard has an integrated chatbot that helps users analyze the data they're looking at. Users can ask contextual questions like "Why is Target's margins shrinking?" and follow up with "Can they reinvest in their business with the cash they have to spur growth again?" The AI references the actual data visible on the tab to give grounded, educational answers.
- **Rating badges** per category: Strong (sage green), Moderate (gold), Weak (rose)

The executive summary content is generated from AI investment analysis of the company's financials, distilled into an accessible format that gives users the story behind the numbers without overwhelming them with a full-length report.

#### Mode 2: Market Intelligence Chat
A conversational AI agent with access to 5 years of financial data for all companies in the S&P 500. Think of it as a Bloomberg terminal that speaks plain English. The agent has 9 specialized tools:

1. **Rank companies** by any metric (e.g., "Top 10 by free cash flow margin")
2. **Screen stocks** with filters (e.g., "Companies with >30% operating margin in tech")
3. **Sector overview** — median metrics and top performers in any sector
4. **Index snapshot** — overall S&P 500 health indicators
5. **Company deep dive** — comprehensive profile of any single company
6. **Compare companies** — side-by-side comparison of 2-10 companies across all metrics
7. **Metric trends** — 20-quarter trend of any metric for any company
8. **Earnings surprises** — biggest beats and misses across the index
9. **Sector comparison** — compare profitability, growth, or valuation across sectors

The agent renders rich structured data inline — comparison tables, trend charts, sector heatmaps, company profile cards — not just plain text responses. It teaches as it answers, explaining why metrics matter and what the numbers reveal about a company's competitive position.

Coverage will expand beyond S&P 500 to include the Dow Jones, Nasdaq Composite, and Russell 2000 — giving users access to financial intelligence across ~4,000+ publicly traded companies.

#### Mode 3: AI-Powered Analysis Engine (Behind the Scenes)
The app generates comprehensive AI investment analysis for each company, but rather than presenting users with lengthy ~5,000-word reports, we distill the insights into the Executive Summary tab on the Value Insights dashboard. This gives users the high-value takeaways — the business analogy, health check, investment fit, and decision triggers — without requiring them to read a full research report.

The underlying analysis follows a zero-tolerance jargon policy: every financial ratio includes a plain English explanation in the same sentence. "Operating margin of 31%" becomes "keeps 31 cents of every dollar after paying for day-to-day stuff." This philosophy carries through to every surface of the app.

#### Mode 4: Earnings Tracker (Upcoming — Not Yet Built)
A real-time earnings monitoring system that transforms how retail investors follow earnings season:

- **Same-day earnings summaries** — when a company you're tracking reports earnings, get a plain-English summary pushed to your phone within hours: what they earned, whether they beat analyst estimates, and what it means for your investment thesis
- **Earnings transcript summaries** — AI-generated summaries of earnings call transcripts highlighting key management commentary, guidance changes, and red flags
- **Push notifications** — real-time alerts for earnings beats/misses, significant guidance changes, and decision trigger activations
- **"Since You Started Tracking" dashboard** — shows how a company's financials have changed since the user began following it: revenue trajectory, margin shifts, debt changes, stock price performance
- **Quarter-over-quarter change tracking** — visual diffs showing exactly what changed in the financials between this quarter and last
- **Decision trigger monitoring** — when a tracked company hits a threshold defined in its decision triggers (from the investment research report), the user gets an alert: "AAPL's revenue growth dropped below 5% for the second consecutive quarter — this was flagged as a reassessment trigger"
- **Earnings calendar** — upcoming reports for tracked stocks with analyst estimates and historical beat rates

### Design Philosophy & Ethos

- **Warren Buffett's investing philosophy** — long-term, fundamentals-focused, understand-the-business approach. Not day trading, not meme stocks, not momentum chasing
- **"Investing should feel like due diligence, not gambling"** — we help users think like owners, not traders
- **Warm, professional, premium aesthetic** — like a private wealth management report, not a flashy trading app. Dark mode with warm charcoal tones, serif headings (classic/authoritative), gold accents, sage green for positive, soft rose for negative
- **Education woven into every interaction** — users don't just see data, they learn what it means. Every metric has a plain-English translation. Every chart has contextual insight. The AI teaches as it analyzes
- **Zero jargon tolerance** — if a financial term appears, the plain English translation appears in the same sentence. Always.
- **Data-dense but never cluttered** — sophisticated color hierarchy that guides the eye to important data. Professional information density with generous whitespace

### Technology Stack

- **AI:** Amazon Bedrock (Claude) with guardrails, multi-agent architecture with specialized expert agents for different analysis categories
- **Backend:** Serverless on AWS (Lambda, DynamoDB, API Gateway, EventBridge Scheduler)
- **Data:** Financial Modeling Prep API for fundamentals, earnings, prices; 5 years of quarterly data cached and updated automatically via scheduled pipelines
- **Frontend:** React with interactive charting, SSE streaming for real-time AI responses

### What I Need Researched

1. **Market Size & Opportunity**
   - TAM/SAM/SOM for AI-powered retail investment research tools targeting millennials/Gen Z, including both emerging investors AND higher-capital self-directed investors ($50K-$500K+ portfolios)
   - Growth trajectory of the retail investing market (accounts opened, AUM, engagement trends)
   - How much do retail investors currently spend on research tools, education, and premium features? Segment by portfolio size.
   - What's the willingness-to-pay for AI financial analysis among young investors vs. established self-directed investors with larger portfolios?

2. **Competitive Landscape**
   - Direct competitors: AI-powered investment analysis tools (Seeking Alpha Premium, Morningstar, Simply Wall St, Stock Analysis, Koyfin, Finviz, etc.)
   - Adjacent competitors: Robinhood's education features, Fidelity's research tools, Yahoo Finance Premium
   - AI-native entrants: Any startups using LLMs for investment research (there are many emerging)
   - What's the gap? What does NO ONE do well for the 25-35 year old investor who wants to understand fundamentals but isn't a finance professional?

3. **Positioning & Differentiation**
   - How should we position against the "free" tools (Yahoo Finance, Google Finance)?
   - How should we position against the "pro" tools (Bloomberg, FactSet)?
   - How should we position against the "AI summary" tools that are emerging?
   - What's our strongest moat: the plain-English translation layer, the visual dashboard, the Buffett philosophy framing, the multi-modal experience (dashboard + chat + reports + earnings tracker), or something else?

4. **Monetization & Pricing**
   - What pricing models work for fintech research tools targeting this demographic?
   - Freemium tiers: what features are best as free (acquisition) vs. premium (conversion)?
   - Comparable pricing: What do Seeking Alpha ($240/yr), Morningstar ($35/mo), Simply Wall St ($10/mo), Stock Analysis ($10/mo) charge and what do they offer at each tier?
   - Our current plan is **$10/month** with possible higher tiers in the future. Is this the right entry price point? What does the data say? What premium features would justify a higher tier?

5. **User Behavior & Adoption**
   - How do millennials/Gen Z currently research stocks before buying? How does this differ between someone investing $200/mo vs. $5,000/mo?
   - What's the typical "research stack" for a self-directed retail investor with a $100K+ portfolio?
   - Retention patterns: What keeps users coming back to financial research tools vs. churning?
   - What role does earnings season play in engagement spikes?
   - At what portfolio size do investors start paying for research tools? What's the conversion trigger?

6. **Regulatory & Trust Considerations**
   - What disclosures are needed for AI-generated investment analysis? (We are NOT a registered investment advisor and do not provide personalized investment advice)
   - How do competitors handle the "not financial advice" positioning?
   - What builds trust with young investors in AI-powered financial tools?

7. **Go-to-Market Strategy**
   - Best acquisition channels for millennial/Gen Z investors (Reddit, YouTube, TikTok, Twitter/X finance communities, podcasts?)
   - What content marketing strategies work in this space?
   - Partnership opportunities (brokerage integrations, financial education platforms, employer benefits)
   - What's the playbook for fintech apps that successfully grew in this demographic?

8. **Market Timing & Trends**
   - How is the "AI for finance" space evolving in 2025-2026?
   - What tailwinds exist? (AI adoption, financial literacy movements, generational wealth transfer)
   - What headwinds? (Regulatory, AI skepticism, market downturns reducing investing interest)
   - Is there a first-mover or fast-follower advantage in this space?

### Output Format

Please provide a structured research report with:
- Executive summary with key findings and strategic recommendations
- Data-backed analysis for each section above
- Specific competitor profiles with feature comparisons
- Pricing recommendations with supporting evidence
- A clear strategic recommendation for positioning and initial go-to-market
- Sources cited throughout
