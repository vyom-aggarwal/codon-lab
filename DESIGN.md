# CatalystAI — design system

This file is the source of truth for every colour, type size, space, radius, shadow and
easing in the product. `apps/web/app/tokens.css` is a literal transcription of §1 below.
Nothing in the codebase may introduce a colour or a font size that is not defined here.

**If you deviate, update this file in the same commit.**

---

## 1. Tokens

Raw tokens live on `:root` under the exact names used in the product spec. Tailwind's
`@theme inline` block maps them into utility namespaces, so a token redefined for dark
mode propagates to every utility automatically without a second set of classes.

### 1.1 Colour — light (default)

```css
:root {
  /* surfaces */
  --canvas: #fbfbfa; /* page background */
  --surface: #ffffff; /* panels, tables */
  --surface-sunk: #f5f5f4; /* inset areas, code blocks, table headers */

  /* structure */
  --border: #e7e5e4; /* 1px hairlines — the primary structural device */
  --border-strong: #d6d3d1; /* focused / active edges */

  /* text */
  --text: #1c1917;
  --text-muted: #57534e;
  --text-faint: #a8a29e;

  /* interaction — the only accent in the product */
  --accent: #1d4ed8; /* interactive affordances + selection ONLY */
  --accent-sunk: #eff4ff; /* selected row background */

  /* semantics — reserved for meaning, never decoration */
  --positive: #15803d; /* stabilizing / passed */
  --negative: #b91c1c; /* destabilizing / failed */
  --warn: #b45309; /* flags, epistasis warnings, demo-mode */
}
```

### 1.2 Colour — dark

Real values, not inverted lightness. Surfaces sit _above_ the canvas (warmer and
lighter); sunk surfaces sit below it. Borders are white at low alpha so they read as
hairlines rather than as lines of paint.

Defined now, **toggle intentionally not shipped** — per the spec, dark mode ships only
if Phase 6 lands early. Until then these values exist so no second pass is needed.

```css
[data-theme='dark'] {
  --canvas: #131110;
  --surface: #1c1917;
  --surface-sunk: #0e0c0b;

  --border: rgb(255 255 255 / 12%);
  --border-strong: rgb(255 255 255 / 20%);

  --text: #f5f5f4;
  --text-muted: #a8a29e;
  --text-faint: #78716c;

  --accent: #3b82f6; /* #1d4ed8 fails contrast on a dark canvas */
  --accent-sunk: #17233f;

  --positive: #22c55e;
  --negative: #f87171;
  --warn: #f59e0b;
}
```

### 1.3 Contrast budget

Audited against the surface each token is actually used on. Phase 9 re-runs this.

| Pair                          | Ratio  | Verdict                              |
| ----------------------------- | ------ | ------------------------------------ |
| `--text` on `--surface`       | 16.9:1 | AAA                                  |
| `--text-muted` on `--surface` | 7.5:1  | AAA                                  |
| `--text-faint` on `--surface` | 2.6:1  | **fails AA — restricted, see below** |
| `--accent` on `--surface`     | 8.6:1  | AAA                                  |
| `--surface` on `--accent`     | 8.6:1  | AAA (white text on accent fill)      |
| `--positive` on `--surface`   | 5.3:1  | AA                                   |
| `--negative` on `--surface`   | 6.2:1  | AA                                   |
| `--warn` on `--surface`       | 4.9:1  | AA                                   |

`--text-faint` is for placeholder text, disabled controls, and non-essential ornament
**only**. It must never carry information the user has to read. In particular it is
never used to encode low confidence — per the spec, low confidence is encoded by
desaturation plus an explicit ± interval, never by making text transparent.

### 1.4 Data colour

Data colour is a **separate system** from UI colour and does not use the tokens above.

- **Signed quantities (ΔΔG and anything else with a sign):** diverging RdBu, zero pinned
  to neutral. A colourbar is always shown, always labelled with units and the sign
  convention.
- **Unsigned quantities (conservation, likelihood, RSA):** single-hue sequential Blues,
  or viridis for heatmaps.
- **Never rainbow.**

Gradients are permitted **only** inside data visualisations. Nowhere else.

### 1.5 Type

Two faces, no more.

```css
:root {
  --font-sans: 'Inter', ui-sans-serif, system-ui, sans-serif; /* UI */
  --font-mono: 'JetBrains Mono', ui-monospace, monospace; /* data / sequence */
}
```

| Size   | Use                                                        |
| ------ | ---------------------------------------------------------- |
| `11px` | micro labels, table headers — uppercase, `0.04em` tracking |
| `12px` | secondary text, captions                                   |
| `13px` | **base UI size — the default for everything**              |
| `15px` | panel titles                                               |
| `18px` | page title                                                 |
| `24px` | rare; project title only                                   |

Line height `1.45` body, `1.25` headings. Weights `400`, `500`, `560` — **never 700+**.
Uppercase is permitted at 11px and nowhere else.

**Mono face is mandatory** for: sequences, mutation codes (`A123V`), accessions, hashes.

**`font-variant-numeric: tabular-nums` is mandatory** for every numeral in a table, chart
axis, or metric readout. Use Tailwind's `tabular-nums`.

### 1.6 Space

4px grid, which is Tailwind's default `--spacing`, so `p-4` is 16px.

| Token                   | Value   | Use                                        |
| ----------------------- | ------- | ------------------------------------------ |
| `--spacing-row`         | `30px`  | table row                                  |
| `--spacing-row-compact` | `26px`  | table row, compact toggle                  |
| `--spacing-control`     | `30px`  | form control height                        |
| `--spacing-rail`        | `240px` | left rail (collapsible)                    |
| `--spacing-inspector`   | `380px` | right inspector                            |
| `--spacing-track-min`   | `640px` | minimum legible width for a sequence track |

Panel padding 16px. Section gaps 24px.

### 1.7 Radius

```css
--radius-control: 4px; /* buttons, inputs, selects */
--radius-panel: 6px; /* panels, tables, cards */
--radius-dialog: 8px; /* dialogs, popovers */
```

`rounded-full` is permitted on status dots and nowhere else. `rounded-3xl` is banned.

### 1.8 Elevation

**Two shadows exist in the entire application.** No others may be added.

```css
--shadow-popover: 0 4px 12px -2px rgb(28 25 23 / 8%), 0 2px 4px -2px rgb(28 25 23 / 6%);
--shadow-dialog:
  0 16px 48px -12px rgb(28 25 23 / 18%), 0 4px 12px -4px rgb(28 25 23 / 8%);
```

No glows, no coloured shadows, no shadows on cards or buttons. Hierarchy is carried by
borders and background steps — the 1px hairline is the primary structural device.

### 1.9 Motion

```css
--ease-out-quint: cubic-bezier(0.16, 1, 0.3, 1);
--duration-fast: 120ms;
--duration-base: 160ms;
```

Only **opacity** and **transform** animate. Popovers and dialogs fade in with a 2px rise.
Nothing else in the product animates — no page transitions, no stagger, no springs.

`prefers-reduced-motion: reduce` cuts every duration to `0ms`. This is implemented once,
globally, in `tokens.css`; individual components do not re-check it.

### 1.10 The synthetic mark

The specification requires a fabricating provider to badge **every individual number** it
produced, not only the screen. A full badge on every cell would make a dense table
unreadable, so the mark is a single `--warn` asterisk immediately after the value,
carrying its explanation as a tooltip, with the footnote spelled out once beneath the
table:

> `*` Synthetic value from a provider that fabricates numbers. Not model output, and not
> a prediction.

It is the only typographic mark in the product that carries meaning on its own, and it is
reserved for this. Whether to draw it comes from `is_mock` on the model version that
produced the number — never from recognising a model by name.

The persistent amber bar stays as it is: not dismissible, on every screen, whenever any
active provider fabricates. The mark is per-number; the bar is per-screen; both are
required and neither substitutes for the other.

### 1.11 The cofactor mark

A second typographic mark, and the last one: a `--warn` dagger `†` after a burial class,
meaning *this residue is exposed in the protein alone and buried once cofactors are
present*. The number beside it is the apo value, which is the honest one to report and
also the misleading one to read alone, so the mark carries the holo value in its tooltip.

Two marks now exist in the product and both mean "this number needs a caveat you cannot
see". No third one may be added without a reason of the same weight.

### 1.12 Third-party rendering surfaces

Mol\* draws to its own WebGL canvas inside the inspector. It is embedded headless — its
toolbars, panels and skin are **not** used, because every visual decision in this product
is ours. The canvas is the one rectangle on screen this design system does not govern,
and it is bounded by a standard panel border like any other figure.

---

## 2. Layout

Three-pane workbench, resizable by drag handle, sizes persisted per user.
Left rail 240px, collapsible. Inspector 380px.

**No modal for anything the user needs to reference while working** — that is what the
inspector is for. Dialogs are for interruptions that genuinely block, and nothing else.

## 3. Tables

Tables, not cards, for anything list-shaped. Every table has:

- sticky header, sortable columns, right-aligned numbers
- a column visibility menu
- row selection with shift-range, and a persistent selection count in a bottom bar
- a keyboard path: `j`/`k` move, `x` selects, `Enter` opens the inspector

## 4. Global interaction

`Esc` closes the topmost layer. Every table carries the keyboard path in §3.

`⌘K` and `?` are **deferred — see §9.** They are specified, not built, and this section
describes what exists.

Focus rings are visible on **every** interactive element: 2px accent at 2px offset.

## 5. State coverage

The empty, loading, and error state of every panel is designed **before** its happy path.

- **Loading** — skeletons matching the final layout's geometry. Never a centred spinner
  over the page.
- **Error** — states what failed, what it means, and the one action that fixes it.
- **Empty** — names the next action.

## 6. Copy

Sentence case. Terse. Units always shown; sign conventions always stated.

- No emoji, anywhere, ever.
- No exclamation marks.
- No first person from the application. "12 variants", never "I found 12 variants".
- No "AI ✨" language, no "powered by".
- Buttons name their effect and **keep that name through the flow**:
  `Start design run` → toast reads `Design run started`.

## 7. Banned

Decorative gradients (data visualisations excepted) · glassmorphism and `backdrop-blur`
cards · emoji · `rounded-3xl` · shadows on cards and buttons · a marketing hero inside the
app · 3-column feature-card grids · animated gradient borders · confetti · fake progress
bars · sparkle icons · page-transition animation · lorem ipsum · centred full-page
spinners · toast spam · "Oops! Something went wrong" · pill-shaped buttons · icon-only
buttons without tooltips · more than one accent colour.

Icons are lucide-react, 16px, 1.5 stroke, never mixed with another set.

> If a screen would look at home on a Product Hunt launch, it is wrong.

---

## 8. Enforcement

The Phase 1 exit gate is: **these tokens are the only source of colour and type in the
codebase.** That is checked mechanically, not by eye —
`apps/web/test/tokens.test.ts` fails the build on any hex literal, `rgb()`/`hsl()` call,
or `text-[…px]` arbitrary value found in `app/` or `components/`, with an allowlist
covering only `tokens.css` itself and data-visualisation scales.

---

## 9. Deferred

Specified in `BRIEF.md`, not yet built. Listed here because a design document that
describes what does not exist is worse than one that admits the gap: it stops being
checkable, and the next reader cannot tell which parts are the contract and which are
the wish.

Nothing may be added to this section without a phase named beside it.

| Device                          | Specified in   | Lands in | Why not yet                                                                                                                              |
| ------------------------------- | -------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `⌘K` command palette            | `BRIEF.md` §4  | Phase 9  | Needs a search surface over projects, targets, constraints and variants — most of which arrived only in Phases 4 and 5. Built with the a11y pass, where keyboard traversal is the phase's subject. |
| `?` shortcut sheet              | `BRIEF.md` §4  | Phase 9  | It documents the shortcuts, so it follows them. The workbench path (`j`/`k`/`x`/`Enter`/`Esc`) exists and is tested; the sheet listing it does not.                                                |
| Wild-type / mutant rotamer toggle | `BRIEF.md` §5.6 | Unscheduled | Needs a side-chain packer. Redrawing the wild-type residue under a "mutant" label would fabricate structural data. See `ARCHITECTURE.md` §12 for the decision and the Dunbrack path forward.       |
| Dark mode toggle                | `BRIEF.md` §4  | Unscheduled | Tokens are defined in §1.2 and ship; the toggle does not. Per the brief, it lands only if a phase comes in early.                          |

**Row-height compaction (`26px`) is not deferred** — it is built, in the workbench
filter rail.
