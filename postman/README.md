# BuffettGPT Postman Collection

Postman collection and environment files for testing the BuffettGPT AWS dev API.

## Architecture

Tool-based LLM orchestration using Claude Haiku with direct Bedrock model invocation. The follow-up endpoint uses 4 tools for answering research questions:

- `getReportSection` - Fetch specific report sections (debt, cashflow, growth, etc.)
- `getReportRatings` - Get investment ratings and verdict
- `getMetricsHistory` - Historical financial trend data
- `getAvailableReports` - List all covered companies

## Files

- `BuffettGPT-AWS-Dev-API.postman_collection.json` - Full API test collection
- `BuffettGPT-Dev-Environment.postman_environment.json` - Environment variables

## Setup

### 1. Import into Postman

1. Open Postman
2. Click **Import** button
3. Select both JSON files from this folder
4. The collection and environment will be imported

### 2. Configure Environment

1. Select **BuffettGPT Dev Environment** from the environment dropdown (top-right)
2. Click the eye icon to view/edit variables
3. Update `base_url` with your actual API Gateway URL:
   - Find it in AWS Console > API Gateway > Your API > Stages > dev
   - Or from Terraform output: `terraform output api_gateway_url`
   - Format: `https://{api-id}.execute-api.us-east-1.amazonaws.com/dev`

### 3. Authentication

To test authenticated endpoints, you need a JWT token:

#### Option A: Get Google ID Token from Browser

1. Open your BuffettGPT frontend app
2. Open browser DevTools (F12) > Network tab
3. Click "Sign in with Google"
4. Find the `/auth/callback` request in Network tab
5. In the request payload, copy the `credential` value
6. Set it as the `google_id_token` environment variable
7. Run the **Auth Callback - Get JWT Token** request
8. The JWT token will be auto-saved for subsequent requests

#### Option B: Use Existing JWT Token

If you already have a valid JWT token:
1. Set it directly as the `jwt_token` environment variable

## Collection Structure

### 1. Authentication
- **Auth Callback** - Exchange Google token for JWT (auto-saves token)
- **Health Check** - Verify API is running

### 2. Conversations (DynamoDB CRUD)
- **Create Conversation** - Creates new conversation, saves ID
- **List Conversations** - Get all user conversations
- **Get Conversation** - Get single conversation by ID
- **Update Conversation** - Update title/metadata
- **Get Messages** - Retrieve conversation messages
- **Save Message** - Add user/assistant messages
- **Archive Conversation** - Soft delete
- **Delete Conversation** - Hard delete

### 3. Research Follow-up (Tool-based)
- **Ask Follow-up Question** - General research question (SSE stream)
- **Ask About Debt Metrics** - Triggers getMetricsHistory tool
- **Ask About Cashflow** - Triggers getReportSection(10_cashflow)
- **Ask About Growth** - Triggers getReportSection(06_growth)
- **Get Investment Verdict** - Triggers getReportRatings tool

### 4. Token Usage Tracking
- **Get Token Usage** - Via chat endpoint response
- **Check Token Usage in Follow-up** - Monitor in SSE complete event

### 5. Research Reports
- **Check Report Status** - See if report exists
- **Stream Report** - Get full report via SSE
- **Get Section** - Fetch individual report sections (debt, cashflow, growth, bull, bear)

## Testing Flow

Recommended order for testing:

```
1. Health Check (verify API is up)
2. Auth Callback (get JWT token)
3. Create Conversation
4. Save User Message
5. Save Assistant Message
6. Get Conversation Messages
7. List All Conversations
8. Ask Research Follow-up Questions
9. Check Token Usage
10. Archive/Delete Conversation
```

## Notes

### SSE Streaming Endpoints

The following endpoints return Server-Sent Events (SSE):
- `/research/followup`
- `/research/report/{ticker}/stream`

Postman displays raw SSE data. For proper streaming visualization:
- Use curl: `curl -N -H "Authorization: Bearer $TOKEN" $URL`
- Or use the frontend application

### Token Usage

Token usage is tracked monthly per user. The response includes:
```json
{
  "token_usage": {
    "input_tokens": 150,
    "output_tokens": 450,
    "total_tokens": 600,
    "token_limit": 500000,
    "percent_used": 0.12,
    "remaining_tokens": 499400,
    "threshold_reached": null
  }
}
```

Threshold warnings at 80%, 90%, and 100% usage.

### Session IDs

- For conversations: Use `conversation_id` from Create Conversation
- For research follow-up: Use any unique `session_id` for conversation context

## Troubleshooting

### 401 Unauthorized
- JWT token expired (7-day validity)
- Re-run Auth Callback with fresh Google token

### 403 Forbidden
- Trying to access another user's conversation
- Check `user_id` matches conversation owner

### 429 Too Many Requests
- Monthly token limit reached
- Wait for month reset or upgrade subscription tier

## Available Report Sections

| Section ID | Description |
|------------|-------------|
| `01_executive_summary` | Overview and key takeaways |
| `06_growth` | Revenue and earnings growth analysis |
| `07_profit` | Profit margins |
| `08_valuation` | P/E, price targets, valuation metrics |
| `09_earnings` | Earnings quality |
| `10_cashflow` | Free cash flow analysis |
| `11_debt` | Leverage and debt analysis |
| `12_dilution` | Share dilution analysis |
| `13_bull` | Bull case / positive scenario |
| `14_bear` | Bear case / risks |
| `15_warnings` | Red flags and warnings |
| `16_vibe` | Sentiment analysis |
| `17_realtalk` | Bottom line conclusions |
