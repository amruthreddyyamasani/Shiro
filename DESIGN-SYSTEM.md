# SHIRO — Design System Specification

## 1. Visual Language & Creative Direction

SHIRO embodies a **technical, restrained, and futuristic** aesthetic tailored for local intelligence. It avoids colorful rainbow gradients, decorative floating shapes, and faux-cyberpunk gimmicks. Instead, it relies on strict typographical rhythm, dark charcoal/graphite surfaces, high contrast technical typography, and deliberate accent signals.

---

## 2. Color Palette & Tokens

### Background & Surface Hierarchy
```css
:root {
  /* Canvas & Foundations */
  --bg-app: #080b10;          /* Deepest obsidian canvas */
  --bg-sidebar: #0b0f15;      /* Navigation boundary */
  --bg-surface: #0f141c;      /* Default card / container surface */
  --bg-surface-raised: #151d28;/* Interactive / hovered card surface */
  --bg-surface-elevated: #1a2431;/* Modal dialogs, dropdown menus */
  --bg-input: #0b0f16;        /* Composer, search and form inputs */

  /* Text & Content */
  --text-primary: #edf2f7;    /* High contrast reading text */
  --text-secondary: #a0acba;  /* Subtitles, labels, descriptions */
  --text-muted: #687789;      /* Timestamps, disabled labels, shortcuts */
  --text-code: #53d9f2;       /* Inline code tokens, identifiers */

  /* Structural Borders */
  --border-subtle: #18202c;   /* Dividers, subtle groupings */
  --border-default: #263242;  /* Standard container borders */
  --border-hover: #3d4f66;    /* Hovered interactive borders */
  --border-focus: #53d9f2;    /* Keyboard focus ring */

  /* Functional Accents */
  --accent-cyan: #53d9f2;     /* Primary brand, active streaming indicator */
  --accent-blue: #648bff;     /* Secondary brand, execution links, buttons */
  --accent-violet: #9681f5;   /* Planner state, memory category tag */

  /* Status Colors */
  --status-success: #10b981;  /* Verified result, succeeded task, online */
  --status-warning: #f59e0b;  /* Approval required, retry pending */
  --status-danger: #ef4444;   /* Error, cancellation, rejection */
  --status-neutral: #64748b;  /* Paused, pending, inactive */
}
```

---

## 3. Typography

- **UI & Display**: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`
  - Clean, legible, neutral sans-serif that respects the host operating system.
- **Technical & Code**: `"JetBrains Mono", "Cascadia Code", "Fira Code", "Consolas", monospace`
  - High legibility for file paths, tool arguments, hashes, JSON diffs, and execution timestamps.

### Type Scale
| Level | Font Size | Line Height | Weight | Usage |
|-------|-----------|-------------|--------|-------|
| `Display` | 24px (1.5rem) | 32px | 600 SemiBold | Page titles (Dashboard, Chat header) |
| `Heading` | 18px (1.125rem) | 26px | 600 SemiBold | Section headers, card titles |
| `Subheading` | 14px (0.875rem) | 20px | 600 SemiBold | Modal titles, trace steps |
| `Body` | 14px (0.875rem) | 22px | 400 Regular | Message content, descriptions |
| `Small` | 12px (0.75rem) | 18px | 500 Medium | Badges, timestamps, secondary labels |
| `Mono/Code`| 13px (0.8125rem) | 20px | 400 Regular | Code blocks, arguments, logs |

---

## 4. Spacing, Radius & Shadows

- **Grid Unit**: 4px base (`4px`, `8px`, `12px`, `16px`, `24px`, `32px`, `48px`).
- **Border Radius**:
  - `sm`: 4px (Buttons, badges, tags).
  - `md`: 8px (Inputs, dropdowns, cards).
  - `lg`: 12px (Modal dialogs, popovers).
  - `full`: 9999px (Pills, avatar circles).
- **Shadows**:
  - `card`: `0 2px 8px rgba(0, 0, 0, 0.4)`
  - `elevated`: `0 8px 24px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.05)`

---

## 5. UI Primitives & Components

### Buttons
- **Primary**: Solid Cyan accent with dark text (`#080b10`), hover brightness +10%.
- **Secondary**: Elevated surface background with default border and `#edf2f7` text.
- **Danger**: Dark red background with bright red border for destructive actions (Delete memory, Deny approval).
- **Ghost**: Transparent with hover background highlight.

### Status Mark & Badges
- Pill-shaped container with an inner 6px solid dot and label.
- Color dynamically mapped to backend enum state:
  - `status: ok` -> Emerald dot + "Ready"
  - `state: running` -> Electric blue pulse + "Running"
  - `requires_approval: true` -> Amber dot + "Approval Needed"

### Trace Line (Agent Step Visualizer)
- Left vertical connection line (`--border-subtle`).
- Status icon (clock, spinner, check, cross, question mark).
- Step title & tool name in Mono font.
- Collapsible argument & result inspector drawer.
