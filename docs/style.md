# Lintel style guide: the drawing-sheet design system

The app looks like an architect's drawing sheet: paper, ink, hairlines, mono annotations, and one accent colour for things that need attention. It takes its look from the lintel-arc page; every component below is designed for a working app.

Screens and flows: [appdesign.md](appdesign.md).

---

## 1. Principles

1. **Ink on paper.** Black-ish ink on warm paper. One accent, used only for "needs attention" and primary actions.
2. **Hairlines, not boxes and shadows.** Structure comes from 1 px rules and cells. No drop shadows (except floating panels), no rounded corners.
3. **Annotate like a drawing.** Labels, measurements and metadata use mono uppercase, as on a title block.
4. **Big, tight headings; quiet body.** Grotesk display type, uppercase, tight tracking; body text in normal case.
5. **Calm motion.** Short, purposeful transitions; nothing that slows down work.

---

## 2. Tokens

```css
:root {
  /* colour */
  --paper:        #f2f1eb;   /* app background */
  --paper-raised: #f7f6f1;   /* cards on hover, inputs */
  --sheet:        #fbfaf6;   /* floating panels, drawers, chat */
  --ink:          #282828;   /* text, lines, primary fills */
  --ink-2:        rgba(40,40,40,.72);  /* secondary text */
  --ink-3:        rgba(40,40,40,.64);  /* muted text: ≥ 4.5:1 on paper */
  --ghost:        #b4b4b0;   /* disabled, placeholder heading state */
  --line:         rgba(40,40,40,.18);  /* hairline */
  --line-2:       rgba(40,40,40,.32);  /* cell borders */
  --accent:       #fa3600;   /* issues, primary action, focus */
  --accent-ink:   #ffffff;   /* text on accent: use ≥ 14px bold or ≥ 18px */
  --accent-soft:  rgba(250,54,0,.08);  /* selected rows, selection box fill */
  --warn:         #b26a00;   /* warnings (advice-only issues) */
  --ok:           var(--ink); /* success is shown in ink with a check, not green */

  /* type */
  --font-display: "Schibsted Grotesk", Arial, sans-serif;
  --font-body:    "Schibsted Grotesk", Arial, sans-serif;
  --font-mono:    "Geist Mono", ui-monospace, Consolas, monospace;

  /* space (4 px base) */
  --s-1: 4px;  --s-2: 8px;  --s-3: 12px; --s-4: 16px;
  --s-5: 24px; --s-6: 32px; --s-7: 48px; --s-8: 64px;

  /* layout */
  --header-h: 64px;
  --gutter: 6px;             /* outer frame gap */
  --col-left: 300px;  --col-right: 340px;

  /* motion */
  --t-fast: 100ms; --t-base: 200ms; --t-slow: 300ms;
  --ease-out: cubic-bezier(.16, 1, .3, 1);
  --ease-inout: cubic-bezier(.7, 0, .2, 1);

  /* focus */
  --focus: 0 0 0 2px var(--paper), 0 0 0 4px var(--accent);
}
```

Paper grain: an SVG noise layer at 7% opacity on `body` only (never inside the plan canvas).

---

## 3. Typography

| Role | Font | Size / line | Weight | Case / tracking |
|---|---|---|---|---|
| Display (page titles) | Display | 40 / 0.95 (clamp 32–56) | 700 | UPPER, −0.035em |
| H2 (section) | Display | 28 / 1.0 | 700 | UPPER, −0.03em |
| H3 (card title) | Display | 20 / 1.05 | 700 | UPPER, −0.02em |
| Body | Body | 15 / 1.45 | 500 | normal, −0.01em |
| Small body | Body | 13 / 1.4 | 500 | normal |
| Label | Mono | 12 / 1.3 | 400 | UPPER, +0.02em |
| Data / measurement | Mono | 13 / 1.3 | 500 | tabular numbers |
| Micro (meta, plan annotations) | Mono | 11 / 1.3 | 400 | UPPER; minimum size anywhere |

Rules: nothing below 11 px; body text never uppercase; measurements always mono with units (`813 MM`, `10.2 M²`).

---

## 4. Layout

- **Frame:** the app sits inside a 1 px `--line-2` border, inset `--gutter` from the window, like a sheet edge.
- **Header:** a fixed row of cells, `--header-h` tall; each cell has a left border; the logo cell is left, the account cell right.
- **Grid:** 12 columns inside content areas; cards snap to 3 or 4 per row; gutters are borders (cells touch), not gaps.
- **Workspace:** 3 columns (`--col-left` · fluid · `--col-right`), full height below the header, each column scrolls on its own.
- **Ruler frame:** only on the plan canvas and the auth pages: tick marks every 8 px (long ticks every 40 px) on the edges, "+" at the corners.

---

## 5. Components

Every interactive component has these states: default · hover · focus-visible · active · disabled · loading.

### Button
| Variant | Default | Hover | Notes |
|---|---|---|---|
| Primary | accent fill, white mono label, arrow `→` | darker accent (`#d92f00`) | one per view |
| Secondary | 1 px `--line-2` border, ink mono label | ink fill rises from the bottom (`--t-slow`, `--ease-inout`); label turns paper | |
| Ghost | no border, ink-2 label | underline grows left to right | for inline actions |
| Danger | 1 px accent border, accent label | accent fill, white label | delete, revoke |

Height 40 px (32 px compact); padding 0 16 px; label mono 12 px upper; loading = label replaced by a 3-dot mono ellipsis; disabled = ghost colour, no hover.

### Header cell / nav item
Mono 12 px upper, 14 px padding, left border; hover = ink fill + paper text; active page = 2 px accent bar along the bottom; dropdown = panel wipes down (`clip-path`, `--t-slow`).

### Card (cell)
1 px `--line-2` border, paper background, 16 px padding; top row = mono label left + `[01]` index right; hover = `--paper-raised`, no movement; selected = accent left bar 3 px.

### Input / select / textarea
Label above in mono 11 px upper; field: 1 px `--line-2` bottom border only (title-block style), 40 px tall, body 15 px; focus = bottom border accent 2 px; error = accent bottom border + mono 11 px accent message below.

### Table
Header row mono 11 px upper `--ink-3`; rows 44 px, 1 px `--line` dividers; numbers right-aligned mono; hover row `--paper-raised`; selected row `--accent-soft`.

### Issue row
Accent square marker (12 px) with number · rule name (H3 small) · element name · `760 < 813 MM` (mono, accent on the failing value) · reference (mono micro italic) · action (Fix → or "ADVICE ONLY").

### Issue marker (plan)
12 px accent square with a white mono number; hover scale 1.15; selected 1.4 with a 2 px accent outline offset 3 px; blinking only for brand-new issues (3 blinks, then steady).

### Change-set card
Header strip: accent fill, white mono title + meta. Body: diff table, before (`--ink-3`, struck through) → after (ink, bold mono). Footer: Approve (primary), Reject (danger), Comment (ghost). Status chip in the header for non-proposed states.

### Status chip
Mono 11 px upper in a 1 px border box: PROPOSED (accent border), APPROVED (ink border), APPLIED (ink fill, paper text, ✓), FAILED (accent fill), REJECTED / REVERTED (ghost).

### Drawer / floating panel
`--sheet` background, 1 px ink border, shadow `0 18px 40px -20px rgba(0,0,0,.35)`, ink title strip in mono; slides in from the right (`--t-base`).

### Toast
Ink background, paper text 13 px, mono label for the type; 4 s; optional Undo (ghost, paper colour).

### Chat
User messages: ink fill, paper text, right-aligned. Assistant messages: 1 px border, left-aligned. Rule references are chips (mono micro, bordered). Proposed change sets are inline compact change-set cards. Input: bordered field with a mono placeholder ("ASK ABOUT YOUR DRAWING…").

### Plan canvas
- Walls: `#3a3a3a` solid, drawn at true thickness.
- Rooms: no fill (flagged rooms get `--accent-soft`); names in mono micro `--ink-2`.
- Doors: a thin leaf plus a dashed swing arc; flagged doors are drawn in accent.
- Dimensions: 0.8 px `--ink-3` with ticks and mono micro labels.
- Selection box: dashed accent border with `--accent-soft` fill.
- Crosshair: 1 px lines, `mix-blend-mode: difference`, live `X … MM / Y … MM` readout in mono micro beside the cursor. Inside the canvas only.

### Empty state
Mono label, one sentence, one primary button, and optionally a small line drawing (outline only, `--ink-3`).

### Skeleton
Cells with a 1 px border and an animated hairline sweep (no grey blocks); static when reduced motion is on.

---

## 6. Iconography

- 1.4 px stroke line icons, square caps, 20 px grid, ink colour; accent only on the "issue" icon.
- Prefer words plus the arrow `→` over icons for actions.
- Status symbols: ✓ (applied), × (rejected/close), ↺ (revert), ▣ (issue).

---

## 7. Motion

| Use | Duration | Easing |
|---|---|---|
| Hover colour/fill | 100–200 ms | ease-out |
| Button fill rise, dropdown wipe | 300 ms | ease-inout |
| Drawer / panel in | 200 ms | ease-out |
| List items appearing (new issues, toasts) | 200 ms, 40 ms stagger, max 6 items | ease-out |
| Plan zoom to issue | 300 ms | ease-inout |

No preloaders, parallax, scroll pinning or scroll-scrubbed animation in the app. The marketing site may use them. `prefers-reduced-motion: reduce` → instant changes, no stagger, no blinking markers.

---

## 8. Accessibility checklist

- Body text contrast ≥ 4.5:1 (`--ink-3` on paper passes); white on accent only for text ≥ 14 px bold.
- Focus ring `--focus` on every focusable element; never removed.
- Hit targets ≥ 32 × 32 px (40 px for primary actions).
- Colour never carries meaning alone: markers have numbers, statuses have words, failing values are also marked by `<`/`>`.
- All plan information is also available in the issue list and the Model tables.

---

## 9. Do and don't

| Do | Don't |
|---|---|
| Use hairline cells to group content | Add drop shadows or rounded cards |
| Keep accent for issues and the one primary action | Colour headers, icons or backgrounds accent |
| Write measurements in mono with units | Mix fonts inside a number |
| Show the rule reference next to every issue | Quote building-code text |
| Use the crosshair only on the plan | Replace the cursor across the whole app |
