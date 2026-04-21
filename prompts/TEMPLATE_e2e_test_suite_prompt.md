# [Feature Name] E2E test suite — agent instructions

Use this document when you need to **verify**, **debug**, and **iteratively fix** the [feature name] flows in the [app name] frontend. The suite is **Playwright** end-to-end tests that exercise [brief description of what's tested] against the real local app and live database.

---

## Goal

Validate the [user role] journey end to end:

- [ ] [Step 1 — e.g., log in as user]
- [ ] [Step 2 — e.g., navigate to feature page]
- [ ] [Step 3 — e.g., create a resource]
- [ ] [Step 4 — e.g., update resource state]
- [ ] [Step 5 — e.g., verify real-time sync across users]
- [ ] [Step 6 — e.g., verify access controls]

---

## What exists

| Item | Location | Status |
|------|----------|--------|
| Playwright config | `apps/frontend/playwright.config.ts` | Built / Not built |
| Custom fixture + diagnostics | `apps/frontend/e2e/fixtures.ts` | Built / Not built |
| Feature helpers | `apps/frontend/e2e/helpers/[feature].ts` | Built / Not built |
| Auth helpers | `apps/frontend/e2e/helpers/auth.ts` | Built / Not built |
| Feature spec | `apps/frontend/e2e/[feature]-flow.spec.ts` | Built / Not built |

Tests assume the app is served at **`http://localhost:3000`** (override with `PLAYWRIGHT_BASE_URL`).

---

## API endpoints required

These are the endpoints the tests expect. If an endpoint doesn't exist yet, the test will fail — build the endpoint to make it pass.

### Read endpoints (GET)

| Route | Auth | Response shape | Purpose |
|-------|------|----------------|---------|
| `GET /api/v1/[resource]` | Public or Bearer JWT | `{ items: [...], total: number }` | List resources |
| `GET /api/v1/[resource]/[id]` | Public or Bearer JWT | `{ item: {...} }` | Get single resource |

### Write endpoints (POST/PATCH/DELETE)

| Route | Auth | Request body | Response | Purpose |
|-------|------|-------------|----------|---------|
| `POST /api/v1/[resource]` | Bearer JWT | `{ field1, field2 }` | `201 { item }` | Create resource |
| `PATCH /api/v1/[resource]/[id]` | Bearer JWT (owner) | `{ field1? }` | `200 { item }` | Update resource |
| `POST /api/v1/[resource]/[id]/[action]` | Bearer JWT (owner) | `{}` | `200 { item }` | Trigger state change |
| `DELETE /api/v1/[resource]/[id]` | Bearer JWT (owner) | — | `204` | Delete resource |

### Error responses expected

| Scenario | Status | Body |
|----------|--------|------|
| Missing auth token | 401 | `{ error: "Unauthorized" }` |
| Wrong owner | 403 | `{ error: "Forbidden" }` |
| Resource not found | 404 | `{ error: "Not found" }` |
| Invalid input | 400 | `{ error: "description" }` |
| Wrong state transition | 400 | `{ error: "description" }` |

---

## Seeded data required

| Item | Value | Notes |
|------|-------|-------|
| User 1 | `user1@app.com` / `password123` | Role: [ROLE], used for [purpose] |
| User 2 | `user2@app.com` / `password123` | Role: [ROLE], used for [purpose] |
| Resource 1 | ID: `sample-1` / Title: "[name]" | Must be in [STATE] status |
| Resource 2 | ID: `sample-2` / Title: "[name]" | Must be in [STATE] status |

Most tests should **create their own data** via API helpers so they don't mutate shared seeded data.

---

## How to run the suite

From the **repository root**:

```bash
# Install browsers (first time only)
npx playwright install chromium

# Run all feature tests
npx playwright test --config=apps/frontend/playwright.config.ts [feature]-flow

# Run a specific spec
npx playwright test --config=apps/frontend/playwright.config.ts e2e/[feature]-flow.spec.ts

# Interactive debugging
npx playwright test --config=apps/frontend/playwright.config.ts --ui
```

---

## Integration tests (API-level)

For testing the API contract directly (faster feedback, no browser):

```bash
# Run integration tests
npx tsx apps/frontend/src/test/integration/[feature]-api.test.ts
```

Integration tests verify:
- Correct status codes (200, 201, 400, 401, 403, 404)
- Response shapes match expected schema
- Auth enforcement (missing token, wrong user)
- State transitions (valid and invalid)
- Data persistence (read back what was written)

---

## How to read failures (agent workflow)

Work in a tight loop:

1. **Run tests** → note which specs fail
2. **Inspect artifacts** → check `test-results/` for screenshots, videos, `browser-diagnostics.txt`
3. **Identify the gap** → missing endpoint? wrong response shape? UI not wired?
4. **Fix the smallest relevant code** → one endpoint or one component at a time
5. **Re-run the failing spec only** → `npx playwright test [spec-file] -g "[test name]"`
6. **Repeat** until green, then run full suite

---

## Stitching workflow (GSD + RALF)

When building endpoints that don't exist yet:

### GSD (plan)
1. **Audit** — read the test spec to understand what the endpoint must do
2. **PRD** — the test assertions ARE the acceptance criteria
3. **Plan** — design the route, lib function, and DB query
4. **Approve** — confirm approach before writing code

### RALF (implement per endpoint)
1. **Implement** — create the API route + lib function
2. **Verify** — run the integration test for that endpoint
3. **Review** — check auth, error cases, response shape
4. **Learn** — note any issues
5. **Complete** — move to next endpoint

---

## Realtime sync (if applicable)

If the feature requires real-time updates across users:

| Mechanism | Table | Event | What it does |
|-----------|-------|-------|-------------|
| Postgres Changes | `[table]` | INSERT | Push new items to all viewers |
| Postgres Changes | `[table]` | UPDATE | Sync counts/status changes |
| Broadcast | `[channel]` | `[event]` | Push ephemeral events |
| Presence | `[channel]` | sync | Track active users |

**Requirements for Realtime:**
- Table must be in `supabase_realtime` publication
- RLS must be enabled with SELECT policy for `anon` role
- Frontend must subscribe to channel on mount and unsubscribe on unmount

---

## Principles

1. **Tests define the bar** — if the test expects it, build it. If the test doesn't check it, don't gold-plate it.
2. **One failure at a time** — fix the first failing test, re-run, repeat.
3. **Minimal changes** — don't refactor unrelated code while fixing tests.
4. **Integration first, E2E second** — prove the API works before testing through the browser.
5. **Create, don't mutate** — tests should create their own data, not depend on shared state.

---

## Logging

Write test results and debug notes to:

```
DOCUMENTATION/Logs/[feature]_flow/YYYY-MM-DD_[description].md
```

Include:
- Which tests passed/failed
- Root cause of failures
- What was fixed
- Any remaining issues

---

## Checklist

- [ ] All API endpoints exist and return expected shapes
- [ ] Auth enforcement tested (401, 403)
- [ ] Error cases tested (400, 404)
- [ ] State transitions tested (valid + invalid)
- [ ] Integration tests pass (API-level)
- [ ] Playwright E2E tests pass (browser-level)
- [ ] Realtime sync verified (if applicable)
- [ ] Results logged to `DOCUMENTATION/Logs/`
