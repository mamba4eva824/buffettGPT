# Critical Bug Fixes Test Suite

This directory contains automated tests for the three critical bugs fixed in the React frontend.

## Bugs Covered

| Bug # | Issue | Location |
|-------|-------|----------|
| 1 | WebSocket Reconnection Race Condition | `App.jsx:644-661` |
| 2 | Stale Closure in Chunk Streaming | `App.jsx:241-265` |
| 3 | Memory Leak from Untracked Timeouts | `App.jsx:771-791, 864-884` |

## Setup

Install testing dependencies:

```bash
npm install --save-dev \
  jest \
  @testing-library/react \
  @testing-library/react-hooks \
  @testing-library/jest-dom \
  jest-environment-jsdom \
  @babel/preset-env \
  @babel/preset-react
```

Add to `package.json`:

```json
{
  "scripts": {
    "test": "jest",
    "test:watch": "jest --watch",
    "test:coverage": "jest --coverage",
    "test:critical": "jest --testPathPattern=critical-fixes"
  },
  "jest": {
    "testEnvironment": "jsdom",
    "setupFilesAfterEnv": ["<rootDir>/__tests__/setup.js"],
    "moduleNameMapper": {
      "\\.(css|less|scss|sass)$": "identity-obj-proxy"
    },
    "testPathIgnorePatterns": ["/node_modules/", "/setup.js$", "/README.md$"]
  }
}
```

Create `__tests__/setup.js`:

```javascript
import '@testing-library/jest-dom';
```

## Running Tests

```bash
# Run all tests
npm test

# Run only critical fix tests
npm run test:critical

# Run with watch mode
npm run test:watch

# Run with coverage
npm run test:coverage
```

## Test Structure

### `critical-fixes.spec.js`

Contains three main describe blocks:

#### Bug Fix #1: WebSocket Reconnection Race Condition
- Tests timeout cleanup on unmount
- Tests cancellation when dependencies change rapidly
- Verifies no state updates after unmount

#### Bug Fix #2: Stale Closure in Chunk Streaming
- Tests finding streaming message by `meta.streaming` flag
- Verifies no duplicate messages created
- Tests content accumulation across chunks

#### Bug Fix #3: Memory Leak from Untracked Timeouts
- Tests timeout tracking with refs
- Tests cleanup of existing timeouts before new ones
- Verifies no banner flickering with rapid queries
- Tests cleanup on component unmount

## Manual Testing with DevTools

### Bug #1: WebSocket Reconnection
1. Open DevTools Console
2. Log in to the app
3. Immediately close the tab within 500ms
4. **Expected:** No "Can't perform a React state update" warning

### Bug #2: Chunk Streaming
1. Open DevTools Console + React DevTools
2. Send a message to the AI
3. Watch the response stream in
4. Check `messages` state in React DevTools
5. **Expected:** Single assistant message that builds up (not multiple bubbles)

### Bug #3: Banner Timeouts
1. Open DevTools Console
2. As unauthenticated user, send 3 queries rapidly
3. Watch the rate limit banner behavior
4. Close tab immediately after queries
5. **Expected:** Banner appears once, no console warnings, no flickering

## Using DevTools MCP Server

The tests are designed to work with automated testing via DevTools MCP:

```javascript
// Example: Testing Bug #1 with Puppeteer via MCP
await page.goto('http://localhost:3000');
await page.click('[data-testid="login-button"]');

// Close before 500ms reconnection timeout
await new Promise(r => setTimeout(r, 100));
await page.close();

// Check for console errors
const errors = await page.evaluate(() => window.__REACT_ERRORS__);
expect(errors).toHaveLength(0);
```

## Expected Test Results

All tests should pass with the fixes in place:

```
PASS  __tests__/critical-fixes.test.js
  Bug Fix #1: WebSocket Reconnection Race Condition
    Timeout Cleanup on Unmount
      ✓ should cancel pending reconnection timeout when component unmounts
      ✓ should cancel pending reconnection when dependencies change
    Concurrent Connection Prevention
      ✓ should not create multiple WebSocket connections on rapid auth changes
    No State Updates After Unmount
      ✓ should not call connect() after cleanup is called

  Bug Fix #2: Stale Closure in Chunk Streaming
    Streaming Message Detection
      ✓ should find streaming message by meta.streaming flag
      ✓ should not rely on external closure variable
    No Duplicate Messages
      ✓ should not create duplicate messages when chunks arrive rapidly
      ✓ should create exactly one assistant message for a streaming response
    New Streaming Message Creation
      ✓ should create new message when no streaming message exists
      ✓ should create new message when previous message is finalized
    Content Accumulation
      ✓ should correctly accumulate content across multiple chunks
      ✓ should handle empty chunks gracefully

  Bug Fix #3: Memory Leak from Untracked Timeouts
    Timeout Tracking
      ✓ should store timeout IDs in refs
      ✓ should clear existing timeouts before setting new ones
    No Banner Flickering
      ✓ should not flicker when queries are sent rapidly
      ✓ should show banner for full 8 seconds even with rapid queries
    Cleanup on Unmount
      ✓ should cleanup timeouts when component unmounts
      ✓ should not cause React warnings after unmount
    Memory Leak Prevention
      ✓ should not accumulate timeout references

  Critical Fixes Integration
    ✓ should handle auth -> query -> stream -> unmount flow

Test Suites: 1 passed, 1 total
Tests:       20 passed, 20 total
```
