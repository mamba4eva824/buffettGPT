# GSD Plan: Enhanced Settings Page

## Phase 1: Audit Snapshot

### Knowns / Evidence
- **Current settings** is a slide-out panel from the right (~50 lines inline in App.jsx, lines 1748-1799)
- Contains only: User ID field, TokenUsageDisplay, SubscriptionManagement, and a short "About" blurb
- **No routing library** — the app uses state-driven navigation (e.g., `showInvestmentResearch` toggles views)
- Existing subscription/usage components are well-built: `TokenUsageDisplay`, `SubscriptionCard`, `SubscriptionManagement`, `UpgradeModal`
- Design system: Tailwind CSS with custom `warm`/`sand` color palettes, `rust` accent, dark mode via `darkMode: 'class'`
- Icons: Lucide React; Animations: Framer Motion; Font: Inter
- Auth: Google OAuth with JWT, `useAuth` hook provides `user`, `token`, `isAuthenticated`
- Dark mode toggle currently lives **only** in the AccountDropdown, not in settings
- App.jsx is already **2,220 lines** — a monolithic component that needs reduction

### Unknowns / Gaps
- Whether users want notification preferences, email preferences, or data export
- Whether keyboard shortcuts or accessibility preferences are desired
- Privacy/data deletion requirements (GDPR, etc.)

### Constraints
- No router — settings must use the existing state-toggle pattern or remain a panel
- Must support both authenticated and unauthenticated states
- Dark/light mode must work across all sections
- Mobile-responsive (Tailwind breakpoints)
- **Must reduce** App.jsx complexity, not add to it

### Risks
1. **App.jsx complexity** — Adding more inline settings content worsens an already-large file
2. **Feature creep** — Settings pages tend to grow unchecked; need clear boundaries
3. **Prop drilling** — SettingsPanel needs many props from App.jsx (manageable for now)

---

## Phase 2: PRD (Product Requirements)

### Goal
Transform the minimal settings slide-out into a professional, well-organized Settings panel that feels complete and trustworthy, while keeping the warm, approachable BuffettGPT personality.

### Acceptance Criteria

**AC-1: Component Extraction**
Given the settings panel code is currently inline in App.jsx (~50 lines), when the enhancement is complete, then all settings UI lives in a dedicated `SettingsPanel.jsx` component file with a clean prop interface.

**AC-2: Section Organization**
Given a user opens settings, when the panel renders, then content is organized into four clearly labeled sections with visual separators and icons:
- **Profile** — User identity and account info
- **Subscription & Usage** — Plan details, token usage, upgrade
- **Appearance** — Dark mode toggle
- **About** — App info, version, links

**AC-3: Profile Section**
Given an authenticated user, when they view the Profile section, then they see:
- Profile picture (from Google via Avatar component), name, and email displayed clearly
- Google ID shown in subtle secondary text
- For unauthenticated: username input + "Sign in" CTA

**AC-4: Appearance Section**
Given a user views the Appearance section, when they toggle dark mode, then the toggle works immediately and persists. The dark mode toggle is available in Settings (the quick-toggle in AccountDropdown also remains as a convenience).

**AC-5: Subscription & Usage Section**
Given the existing `TokenUsageDisplay` and `SubscriptionManagement` components, when they render in the settings panel, then they maintain all current functionality, grouped under a "Subscription & Usage" heading.

**AC-6: About Section**
Given a user views the About section, then they see:
- App description (BuffettGPT tagline)
- Version display
- Placeholder links: Privacy Policy, Terms of Service
- "Powered by" credit line

**AC-7: Mobile Responsive**
Given a mobile user, when they open settings, then the panel is full-width with comfortable touch targets and proper scrolling.

**AC-8: Visual Polish**
- Section headers use Lucide icons for scannability
- Smooth Framer Motion slide-in/out animation
- Consistent spacing and visual hierarchy
- Matches the warm, professional tone of the app

**AC-9: Close Behavior**
Given the settings panel is open, when user clicks backdrop, presses Escape, or clicks Close, then the panel closes.

---

## Phase 3: Implementation Plan

### Objective
Extract and enhance the settings panel into a standalone, well-organized component with clear sections, improved profile display, dark mode toggle, and a polished About section.

### Approach Summary
Create a new `SettingsPanel.jsx` component that replaces the inline settings panel in App.jsx. Use a vertically scrollable layout with clearly delineated sections (no tabs — vertical scroll with section headers is cleaner and more mobile-friendly for 4 sections). Add Framer Motion `AnimatePresence` for slide-in/out, Escape key handling, and an improved profile display.

### Steps

| # | Task | Dependencies | Files | Verification |
|---|------|-------------|-------|-------------|
| 1 | Create `SettingsPanel.jsx` with panel shell, backdrop, Escape key, Framer Motion animation | None | `components/SettingsPanel.jsx` | Renders, opens/closes |
| 2 | Build Profile section — avatar, name, email (auth); username input (unauth) | 1 | `SettingsPanel.jsx` | Correct display for both auth states |
| 3 | Build Subscription & Usage section — embed `TokenUsageDisplay` + `SubscriptionManagement` | 1 | `SettingsPanel.jsx` | All existing subscription features work |
| 4 | Build Appearance section — dark mode toggle with switch UI | 1 | `SettingsPanel.jsx` | Toggle works and persists |
| 5 | Build About section — tagline, version, placeholder links | 1 | `SettingsPanel.jsx` | Renders correctly |
| 6 | Integrate into App.jsx — replace inline panel, pass props | 1-5 | `App.jsx` | Settings opens/closes, all features preserved |
| 7 | Run lint + build verification gates | 6 | — | `npm run lint` + `npm run build` pass |

### Files Changed
| File | Change |
|------|--------|
| `frontend/src/components/SettingsPanel.jsx` | **NEW** — Full settings panel component |
| `frontend/src/App.jsx` | Replace ~50 lines of inline panel with `<SettingsPanel />` import |

### Files Reused As-Is (no changes)
- `TokenUsageDisplay.jsx`, `SubscriptionManagement.jsx`, `SubscriptionCard.jsx`, `UpgradeModal.jsx`, `Avatar.jsx`

---

## Phase 4: Self-Critique (Red Team)

### Fragile Assumptions

1. **"Four sections is enough"** — Users may expect notification preferences, data export, or connected accounts. Starting lean is correct — these can be added as new sections later without restructuring.

2. **"No routing needed"** — If settings grows to need sub-pages (billing history, detailed preferences), we'd eventually want React Router. For now, a single scrollable panel is the right call.

3. **"Prop drilling is manageable"** — SettingsPanel needs ~10 props. If it grows beyond 12-15, a SettingsContext would help, but that's premature now.

### Failure Modes

1. **Animation jank** — Framer Motion slide-in with backdrop blur is standard usage, low risk.
2. **Mobile scroll lock** — Current `fixed inset-0` pattern already prevents background scroll. Maintained.
3. **Dark mode state source of truth** — Both AccountDropdown and SettingsPanel reference the same `darkMode` state from App.jsx. No conflict since both receive it as props.

### What's the simplest version that delivers 80% of value?

The **biggest wins** are:
1. **Extracting to a component** — Reduces App.jsx by ~50 lines, improves maintainability
2. **Section headers with icons** — Makes settings scannable and professional
3. **Better profile display** — Avatar + name instead of raw ID string
4. **Dark mode in settings** — Logical placement users expect to find

The About section polish and Framer Motion are low effort with high perceived-quality impact. Include them.

### What's NOT in scope (intentionally)
- Notification preferences (no notification system exists)
- Data export / account deletion (needs backend API work)
- Keyboard shortcut preferences (no shortcut system exists)
- Theme color customization (over-engineering)
- Settings persistence to backend (localStorage is fine for now)
