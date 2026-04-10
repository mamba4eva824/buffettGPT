# Design System Document

## 1. Overview & Creative North Star
The financial sector is often defined by cold, utilitarian grids. This design system rejects that tradition, moving toward a **"Digital Curator"** North Star. We treat financial data not as raw information, but as a premium editorial experience—think *The Financial Times* meets a high-end private banking gallery.

The system breaks the "template" look through a signature use of high-contrast typography and intentional depth. We leverage a rich, midnight foundation to allow gold accents to "glow" with conviction. The layout philosophy prioritizes breathing room and asymmetrical balance over dense, boxed-in charts, ensuring that every data point feels intentional and authoritative.

---

## 2. Colors
Our palette is rooted in a deep, nocturnal base that provides the stage for "warm-light" accents.

### Color Tokens
- **Background (`surface`):** `#111125` — A deep navy that provides the infinite canvas.
- **Primary (`primary`):** `#f2c35b` — A warm gold for high-conviction signals and primary actions.
- **Secondary (`secondary`):** `#cac6be` — A muted cream for subtle UI elements.
- **Tertiary/Semantic:**
    - **Strong/Positive (`tertiary`):** `#a0d6ad` (Sage)
    - **Moderate/Neutral (`on_secondary_container`):** `#b9b5ad` (Amber/Stone)
    - **Weak/Negative (`error`):** `#ffb4ab` (Dusty Rose)

### The "No-Line" Rule
To maintain a premium, seamless feel, **prohibit 1px solid borders for sectioning.** Boundaries must be defined through background shifts. A card should be a `surface-container-low` object sitting on a `surface` background. If you need to separate content, use white space (from the 16px/24px scale) or a subtle tonal shift.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical layers:
1.  **Level 0 (Base):** `surface` (#111125)
2.  **Level 1 (Sections):** `surface-container-low` (#1a1a2e)
3.  **Level 2 (Cards/Active Elements):** `surface-container` (#1e1e32)
4.  **Level 3 (Pop-overs/Modals):** `surface-container-highest` (#333348)

### Glass & Gradient Rule
For floating elements (like analysis tooltips), use a semi-transparent `surface-variant` with a `backdrop-blur` of 12px. For main CTAs, use a subtle linear gradient from `primary` (#f2c35b) to `primary_container` (#d4a843) to provide a "metallic" soul that flat colors lack.

---

## 3. Typography
We employ a high-contrast pairing: an authoritative Serif for headlines and a high-legibility Sans-Serif for the mathematical precision of financial data.

- **Display & Headlines (Noto Serif):** These are the "Editor's Voice." Use `display-md` or `headline-lg` for portfolio totals and market sentiments. The serif nature conveys institutional trust.
- **Body & Data (Inter):** The "Analyst's Voice." All data tables, ticker symbols, and fine print use Inter. It is clean, legible at small sizes, and feels technologically advanced.

**Hierarchy Note:** Always lead with a Serif headline to ground the page, followed by Sans-Serif data. This reinforces the "Value Insights" editorial narrative.

---

## 4. Elevation & Depth
In this system, depth is organic, not structural.

- **The Layering Principle:** Avoid shadows for static layout components. Instead, place a `surface-container-lowest` card inside a `surface-container-low` wrapper to create a soft, "recessed" look.
- **Ambient Shadows:** For interactive "raised" elements, use a 32px blur shadow with 6% opacity, tinted with the `surface_tint` (#eec058) color. This mimics the way light catches gold leaf.
- **The "Ghost Border" Fallback:** If a border is required for high-density data tables, use `outline-variant` (#4e4636) at 20% opacity. It should be felt, not seen.
- **Glassmorphism:** Use for navigation overlays and floating action buttons. This allows the midnight background to bleed through, softening the interface and making it feel integrated.

---

## 5. Components

### Buttons
- **Primary:** Gold gradient background (`primary` to `primary_container`), `on_primary` text. 8px rounded corners.
- **Secondary:** `surface-container-high` background with a `primary` ghost border (20% opacity).
- **Tertiary:** Text-only in `secondary_fixed_dim`, no background. Use for "Cancel" or "View Less" actions.

### Cards & Data Tables
- **Cards:** No borders. Use `surface-container-low` and `md` (12px) roundedness. 
- **Data Tables:** Forbid divider lines. Use `spacing-4` (16px) vertical padding to separate rows. Highlight the "Conviction Row" using a subtle `surface-bright` background shift.

### Tickers & Chips
- Use `tertiary_container` for positive trends and `error_container` for negative. The text color should always be the high-contrast `on_tertiary` or `on_error` variant to ensure accessibility against the dark backgrounds.

### Input Fields
- Dark backgrounds (`surface_container_lowest`) with an `outline` that glows `primary` only when focused. Labels must always be visible in `body-sm`.

---

## 6. Do's and Don'ts

### Do
*   **Do** use asymmetrical spacing. A 64px left margin versus a 32px right margin creates an editorial "magazine" feel.
*   **Do** use the Gold (`primary`) sparingly. It is a "High Conviction" signal, not a decoration.
*   **Do** rely on `notoSerif` for large, bold statements about value and wealth.

### Don't
*   **Don't** use pure white (#FFFFFF). Use the Cream (`secondary_fixed`) or Blue-Grey (`on_surface_variant`) to maintain the midnight atmosphere.
*   **Don't** use 1px solid white/grey borders. It breaks the premium "curated" immersion.
*   **Don't** use standard "Success Green." Use the Sage (`tertiary`) token for a more sophisticated, calm financial outlook.