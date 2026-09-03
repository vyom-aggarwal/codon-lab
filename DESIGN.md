# Codon Lab — design system

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

No document-level toggle ships — per the spec, dark mode ships only if Phase 6 lands
early, and it did not. The values are reachable in one place: the landing page scopes
`data-theme="dark"` to its hero, refusals and footer, which re-points every token
underneath and leaves the application on the light palette. See §13.

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

**Recomputed and enforced on every build**, not audited by hand once a phase.
`apps/web/test/contrast.test.ts` derives every ratio below from `tokens.css`
with the WCAG 2.1 relative-luminance formula and fails if this table disagrees.
Changing a token without updating the table breaks the build; so does updating
the table without changing the token.

That gate exists because the hand-maintained version drifted. Until Phase 9 this
section claimed `--accent` on `--surface` was **8.6:1, AAA**. It is **6.70:1,
AA** — and had been since Phase 1. The error was in the direction that
overstates compliance, which is the direction that matters.

Ratios are for normal-size text: AAA at 7:1, AA at 4.5:1.

#### Light

| Pair                              | Ratio   | Verdict                              |
| --------------------------------- | ------- | ------------------------------------ |
| `--text` on `--surface`           | 17.49:1 | AAA                                  |
| `--text-muted` on `--surface`     | 7.63:1  | AAA                                  |
| `--text-faint` on `--surface`     | 2.52:1  | **fails AA — restricted, see below** |
| `--accent` on `--surface`         | 6.70:1  | AA                                   |
| `--surface` on `--accent`         | 6.70:1  | AA (white text on an accent fill)    |
| `--positive` on `--surface`       | 5.02:1  | AA                                   |
| `--negative` on `--surface`       | 6.47:1  | AA                                   |
| `--warn` on `--surface`           | 5.02:1  | AA                                   |
| `--text` on `--canvas`            | 16.89:1 | AAA                                  |
| `--text-muted` on `--canvas`      | 7.37:1  | AAA                                  |
| `--accent` on `--canvas`          | 6.47:1  | AA                                   |
| `--text` on `--surface-sunk`      | 16.03:1 | AAA                                  |
| `--text-muted` on `--surface-sunk`| 6.99:1  | AA                                   |
| `--text` on `--accent-sunk`       | 15.87:1 | AAA                                  |
| `--accent` on `--accent-sunk`     | 6.08:1  | AA                                   |

#### Dark

Dark is reachable in exactly one place — the landing page scopes it to three
sections (§13). It is audited anyway, because the tokens exist and a toggle
would make all of it live at once.

| Pair                              | Ratio   | Verdict                              |
| --------------------------------- | ------- | ------------------------------------ |
| `--text` on `--surface`           | 16.03:1 | AAA                                  |
| `--text-muted` on `--surface`     | 6.93:1  | AA                                   |
| `--text-faint` on `--surface`     | 3.65:1  | **fails AA — restricted, see below** |
| `--accent` on `--surface`         | 4.75:1  | AA                                   |
| `--surface` on `--accent`         | 4.75:1  | AA                                   |
| `--positive` on `--surface`       | 7.68:1  | AAA                                  |
| `--negative` on `--surface`       | 6.32:1  | AA                                   |
| `--warn` on `--surface`           | 8.14:1  | AAA                                  |
| `--text` on `--canvas`            | 17.26:1 | AAA                                  |
| `--text-muted` on `--canvas`      | 7.47:1  | AAA                                  |
| `--accent` on `--canvas`          | 5.12:1  | AA                                   |
| `--text` on `--surface-sunk`      | 17.89:1 | AAA                                  |
| `--text-muted` on `--surface-sunk`| 7.74:1  | AAA                                  |
| `--text` on `--accent-sunk`       | 14.27:1 | AAA                                  |
| `--accent` on `--accent-sunk`     | 4.23:1  | **fails AA — latent, see below**     |

**`--accent` on `--accent-sunk` fails AA on dark.** `--accent-sunk` is the
selected-row background, so this pairing would occur wherever accent-coloured
text sits on a selected row. It is **latent rather than live**: the only dark
surfaces in the product are three landing-page sections, and none of them
contains a table. It is recorded here, and asserted in `contrast.test.ts`, so
that shipping a dark-mode toggle cannot make it live without someone being made
to look at it first.

`--text-faint` is for placeholder text, disabled controls, and non-essential
ornament **only**, in either theme. It must never carry information the user has
to read. In particular it is never used to encode low confidence — per the spec,
low confidence is encoded by desaturation plus an explicit ± interval, never by
making text transparent.

### 1.4 Data colour

Data colour is a **separate system** from UI colour and does not use the tokens above.

- **Signed quantities (ΔΔG and anything else with a sign):** diverging RdBu, zero pinned
  to neutral. A colourbar is always shown, always labelled with units and the sign
  convention.
- **Unsigned quantities (conservation, likelihood, RSA):** single-hue sequential Blues,
  or viridis for heatmaps.
- **Never rainbow.**

Gradients are permitted **only** inside data visualisations. Nowhere else.

**A chart that encodes nothing in colour uses no data palette.** The Phase 8
scorecard charts — the predicted-vs-measured scatter and the calibration curve —
encode both of their variables in *position*. Colour there is not carrying a
value, so introducing a diverging or sequential ramp would be decoration
pretending to be an encoding, and would put a second meaning on a screen where
`--accent` already means "this is the data". Both therefore draw marks in
`--accent`, gridlines in `--border`, axes and the identity reference in
`--border-strong`. The rules above apply the moment a chart encodes a value in
colour; none currently does.

Consequently `tokens.test.ts` still forbids every colour literal in
`components/scorecard/`, and that is correct rather than an oversight — the
exemption for data colour begins where a palette is actually needed.

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

**Three display sizes exist for the landing page and nowhere else.**

| Size   | Line height | Tracking   | Use                                              |
| ------ | ----------- | ---------- | ------------------------------------------------ |
| `32px` | 1.2         | `-0.01em`  | landing section headings, hero stats, hero on narrow viewports |
| `44px` | 1.1         | `-0.015em` | the landing hero from `sm`                       |
| `56px` | 1.05        | `-0.02em`  | the landing hero from `md`                       |

`BRIEF.md` §4 fixes the scale at 11/12/13/15/18/24, and **that scale still governs
every application screen** — the workbench, the run view, the scorecard, all of
it. The brief's §5 lists nine screens and a landing page is not among them, so
this is a surface the in-app scale was never written for rather than a
relaxation of it. Negative tracking at these sizes is ordinary typesetting: Inter
at 44px with default tracking reads loose.

The containment is a test, not a convention. `tokens.test.ts` fails the build if
`text-32`, `text-44` or `text-56` appears anywhere outside `components/landing/`.

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

`⌘K` opens the command palette and `?` opens the shortcut sheet. Both ship in Phase 9
and both are mounted in `AppFrame`, so they exist on every application screen and on none
of the landing page. `?` is ignored while a text field has focus — it is an ordinary
character, and a user typing a question mark into the goal composer is not asking for
help.

**The shortcut sheet lists only bindings that exist.** `apps/web/test/keyboard.test.tsx`
checks it in both directions: every key the workbench implements appears in the sheet, and
every key the sheet lists is in the implemented set. A sheet that names a key nothing
answers to is the product telling the user something untrue about itself.

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
| Wild-type / mutant rotamer toggle | `BRIEF.md` §5.6 | Unscheduled | Needs a side-chain packer. Redrawing the wild-type residue under a "mutant" label would fabricate structural data. See `ARCHITECTURE.md` §12 for the decision and the Dunbrack path forward.       |
| Dark mode toggle                | `BRIEF.md` §4  | Unscheduled | Tokens are defined in §1.2 and ship; the toggle does not. Per the brief, it lands only if a phase comes in early.                          |
| Wet-lab handoff screen          | `BRIEF.md` §5.8 | Phase 7, blocked | The **refusal** ships (`services/exports`): primers are refused while any provider fabricates, and again because no target carries a coding DNA sequence to design against. The screen that would show primers, a plate map and a PDF report does not exist, and cannot until a construct's DNA can be attached. `ARCHITECTURE.md` §16. |
| Codon usage and plate map       | `BRIEF.md` §5.8 | Phase 7, blocked | Same blocker. A gene fragment can legitimately be back-translated; a primer cannot, and the two ship together. |

**Row-height compaction (`26px`) is not deferred** — it is built, in the workbench
filter rail.

**`⌘K` and the `?` sheet are no longer deferred** — both shipped in Phase 9 and are
described in §4. They were the only two rows in this table with a phase that has now
passed; what remains here is unscheduled or blocked, and each says which.

---

## 10. The epistasis warning

Added in Phase 7, and the one place in the product where a panel is allowed to be
loud. `BRIEF.md` §5.7 asks for "an unmissable warning"; this is what that means
concretely, and what it deliberately does not mean.

**It is `--warn`, the token reserved for flags, epistasis warnings and demo mode.**
Not `--negative`: nothing has failed. A stacked design is a legitimate thing to
order, and the warning is a caveat on how to read its number, not an error.

**It is not dismissible**, for the same reason the demo bar is not (§1.10). A
warning a user can close is a warning that is absent from the screenshot which
ends up in a slide deck.

**It renders from data, never from a component's judgement.** The API returns
`warning.stacked_designs`, and zero is what turns the panel off. The assumption
sentence itself comes from `domain/epistasis`, so it lives with the arithmetic
that needs it and a second screen cannot quietly soften the wording.

**No third typographic mark was added.** §1.11 says two marks exist and a third
needs a reason of the same weight. The pair flag did not qualify: it is a badge on
a row, in `--warn`, and an unmeasured pair is the ordinary em dash of §1.10's
neighbour — `EmptyCell` with the reason on hover. The marks stay at two.

### Three states, three renderings

The rule that shapes the whole panel: **`unknown` must not look like `beyond`.**

| State     | Rendering                                                        |
| --------- | ---------------------------------------------------------------- |
| `within`  | separation in `--warn`, tabular, plus a `Within 8 Å` badge        |
| `beyond`  | separation in `--text-muted`, tabular, no badge                   |
| `unknown` | the words "not measured" in `--text-faint`, reason on hover       |

`--text-faint` is permitted here because it is doing exactly the job §1.3 reserves
it for — the value is genuinely absent and the text carries no information the
user must read; the reason does, and that is in the tooltip and again in the panel
summary. The summary counts unknown pairs on its own line whenever there are any,
so the absence is legible without hovering anything.

---

## 11. The scorecard figure row

Phase 8. This is a design rule that exists because of a *scientific* constraint, so
it is stated here and enforced in a test rather than left to layout judgement.

`ARCHITECTURE.md` §13: a rank statistic never stands alone. A predictor that is
perfectly ordered but reads a constant 2 kcal/mol high scores a flawless Spearman
and a flawless precision@k. So the card renders four figures **in one row, in one
`<dl>`, in this order**:

| Position | Figure                | Kind  |
| -------- | --------------------- | ----- |
| 1        | Spearman ρ            | rank  |
| 2        | Precision@k           | rank  |
| 3        | MAE, in the unit      | error |
| 4        | Mean signed error     | bias  |

Rank and bias are two cells apart and **may not be separated** by a tab, a
disclosure, a scroll or a second card. `apps/web/test/scorecard.test.tsx` asserts
from the rendered DOM that the bias figure shares a `<dl>` with the rank figures;
closing that list early fails four tests.

Two renderings follow from it:

- An uncomputable figure reads `—` and its reason is printed **inside the same
  block**, immediately beneath the row — never in a tooltip, never in a footnote.
  A reader must not be able to mistake "the error could not be measured" for "the
  error is small". This is the one place a `—` carries a warn-toned panel rather
  than only a hover.
- The bias figure is the only one set in `font-strong`. It is the figure most
  likely to be skipped and the one §13 exists to protect.

---

## 12. The mark

`components/brand/codon-mark.tsx`. One component, `currentColor` throughout, so
the mark takes whatever token its context sets and never introduces a colour.

**What it is.** A segment of duplex DNA, twisting. Two backbone strands run
straight through the middle and flick away at the top left and bottom right.
**Five rungs**: three at full width across the straight core, and two shorter
ones out on the flares, foreshortened the way a base pair is when the duplex
rotates away from the viewer. The short pair is what makes the form read as
turning rather than as a ladder; `landing.test.tsx` asserts the count, because
dropping one is a different mark.

**Construction.** Stroke 1.5 on a 24-unit grid — the same construction §1.9
fixes for every icon in the product. A brand mark drawn at a different weight to
the interface around it reads as an imported asset. The straight core runs y=8 to
y=16 at x=7 and x=17; the strands leave it on a curve to (4.5, 3) and (19.5, 21);
full-width rungs sit at y=8.5, 12 and 15.5, and the foreshortened pair spans
x=9.5 to 14.5 at y=5 and y=19.

The form has 180-degree rotational symmetry, so it needs no separate variant for
a dark ground.

**Twelve candidates were drawn and compared** at 16, 20, 24, 32 and 48px before
this one. The rejected ones failed by reading as something else at small size — a
bowtie, a euro sign, a text-align icon, a document, a shopping trolley. That list
is the useful part of the record: a mark is chosen against misreadings, not
against a description.

**Colour.** Accent in the application chrome and on the landing page; `--surface`
when it sits on an accent fill. It never carries a second colour.

**Favicons are the one place a literal colour is unavoidable.** `app/icon.svg`
and `app/apple-icon.svg` are standalone documents — a browser tab renders them
with no stylesheet, so they cannot reference a custom property. Both carry
`#1D4ED8`, which is `--accent`, and both are outside the extensions
`tokens.test.ts` scans. If the accent ever moves, these two files move by hand.

---

## 13. The landing page

`components/landing/`, served at `/` with **no application chrome** — `Shell`
renders that one route without the rail or the demo bar.

`BRIEF.md` §4 bans a marketing hero *inside the app*. This is how that stays
true: the marketing surface and the instrument are separate documents that share
a domain, and the ban holds everywhere the rail is. Every other prohibition in
§4 applies here unchanged and is respected — no gradients, no glassmorphism, no
card shadows, no three-column feature-card grid, no pill buttons, no emoji, one
accent colour. Most of it is enforced by `tokens.test.ts`, which scans this
directory like any other.

**Rhythm comes from alternating grounds, not from ornament.** Hero, refusals and
footer are dark; the sequence band and the three content sections are light. That
is the whole visual device — there are no gradients, no glows, no cards floating
on shadows, because none of those are in the system and adding them for one page
would put a second design language in the repository.

The dark sections work by scoping `data-theme="dark"` to a wrapper. Every token
underneath re-points, so those sections are built from the same utilities as the
light ones and cannot drift from the palette. Two consequences worth knowing:

- On dark, the primary button is `bg-text text-canvas` — a near-white fill with
  dark text. `bg-accent` with white text was measured at 3.37:1 against
  `--accent`'s dark value and does not clear AA; this pairing clears it easily
  and is the stronger call to action anyway.
- The 3D viewer resolves `--surface` and `--accent` from **its own container**
  rather than from `:root`, which is what makes the model's ground follow the
  section it sits in.

**The sequence band is real characters.** All 212 residues of P37957, the signal
peptide dimmed and the catalytic triad in `--warn`. It runs off the edge of the
viewport rather than wrapping or shrinking to fit: a sequence is long, and
compressing it to look tidy is the same instinct as rounding a number for the
same reason. `lib/landing/lipase.ts` is a copy of the API's vendored FASTA
because the web container cannot read `apps/api`; `landing.test.tsx` asserts the
two are byte-identical, so the duplication cannot drift.

Two rules are specific to this page.

**Every number on it is one this build measured**, with the conditions it was
measured under. A page whose product claim is "no fabricated numbers" cannot
round, dramatise or invent one — including the unflattering ones, which is why
ρ = 0.30 is on the page rather than a rounder figure, and why the MAE reads as
an em dash with its reason. No customer logos, no testimonials, no metrics that
were not produced by running the thing.

**The 3D viewer shows real coordinates and says what they are.** It is the
AlphaFold model of P37957 — the protein the rest of the build is measured on —
served as a static asset so the page renders with the API, worker and database
all down. It is labelled a prediction rather than an experimental structure, and
the residue buttons carry both numbering schemes, because the coordinate file
numbers the full-length precursor while the project's canonical scheme is the
mature protein, 31 lower. Mol\* is created headless, so none of its own chrome
appears, and its orientation gizmo is switched off: a landing page is not the
place to publish another product's debug widget.

**There is no ambient rotation, and that is a correctness decision rather than a
taste one.** The viewer originally spun. A spin redraws the scene every frame,
and this scene cost ~65 ms a frame even at 358x358 — enough to saturate the main
thread and starve the Next router, so that clicking "Open the workbench" did
nothing at all. It was measured both ways: under `prefers-reduced-motion:
reduce`, where the spin never started, the same click navigated and a frame cost
14 ms. A dead call-to-action is a far worse defect than a still model.

So the model sits still until the reader moves it, which is what §1.9 asks for
anyway: motion on demand, not motion by default. It remains fully interactive —
drag to rotate, and the triad buttons fly the camera to a residue. Temporal
multisampling and screen-space occlusion are off for the same reason; they earn
their cost in a structure viewer a scientist is studying, not on a landing page.

If ambient motion is ever wanted back, the prerequisite is making a frame cheap,
not re-adding the spin. `apps/web/e2e/landing-cta.spec.ts` holds the line at
25 ms a frame and explains where that number came from.
