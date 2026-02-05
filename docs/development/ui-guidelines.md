# UI Guidelines

This document covers frontend UI patterns and best practices for BuffettGPT.

## Overview

BuffettGPT's frontend uses React 18 with Tailwind CSS for styling.

## Component Structure

```
frontend/src/
├── components/
│   ├── Chat/              # Chat interface components
│   ├── Research/          # Investment research UI
│   ├── Common/            # Shared components
│   └── Layout/            # Page layouts
├── contexts/
│   └── ResearchContext.jsx  # Research state management
├── hooks/
│   └── useResearch.js     # Custom hooks
└── api/
    └── conversationsApi.js  # API client
```

## Design Principles

### 1. Progressive Disclosure

Show essential information first, details on demand:

- Executive summary visible immediately
- Detailed sections load on click
- Follow-up questions expand inline

### 2. Typewriter Effect

Reports stream with character-by-character animation:

```css
.streaming-text {
  animation: typewriter 0.05s steps(1);
}
```

### 3. Loading States

Use skeleton loaders for async content:

```jsx
{isLoading ? (
  <Skeleton className="h-4 w-full" />
) : (
  <ReportSection content={content} />
)}
```

## Key Components

### Table of Contents

Sticky navigation showing report sections:

```jsx
<TableOfContents
  toc={reportMeta.toc}
  activeSection={activeSectionId}
  onSectionClick={handleSectionClick}
/>
```

### Report Sections

Each section renders markdown content:

```jsx
<ReportSection
  title={section.title}
  content={section.content}
  isStreaming={isStreaming}
  icon={section.icon}
/>
```

### Ratings Display

Star ratings with confidence indicators:

```jsx
<RatingCard
  category="Growth"
  rating={ratings.growth.rating}
  confidence={ratings.growth.confidence}
/>
```

## State Management

### ResearchContext

Global state for research experience:

```javascript
const initialState = {
  selectedTicker: null,
  activeSectionId: null,
  isStreaming: false,
  reportMeta: null,
  streamedContent: {},
  followUpMessages: []
};
```

### Actions

| Action | Purpose |
|--------|---------|
| SET_TICKER | Select company |
| SET_REPORT_META | Store ToC + ratings |
| APPEND_CHUNK | Add streaming text |
| SET_ACTIVE_SECTION | Highlight ToC item |

## Styling

### Tailwind Classes

Use utility classes consistently:

```jsx
// Good
<div className="flex items-center gap-4 p-4">

// Avoid custom CSS unless necessary
```

### Color Scheme

| Element | Light | Dark |
|---------|-------|------|
| Background | `bg-white` | `bg-slate-900` |
| Text | `text-gray-900` | `text-gray-100` |
| Accent | `text-indigo-600` | `text-indigo-400` |

## Accessibility

1. **Keyboard Navigation** - All interactive elements focusable
2. **Screen Readers** - Proper ARIA labels
3. **Color Contrast** - WCAG AA compliant

## Related

- [Testing](testing.md)
- [API Reference](../api/index.md)
