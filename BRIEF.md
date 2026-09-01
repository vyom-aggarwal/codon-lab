# Codon Lab — the brief

**This is the product specification as written by the project owner, reproduced
verbatim. It is the source of truth for what this is and why.**

Unlike `DESIGN.md` and `ARCHITECTURE.md` — which are living contracts, updated
in the same commit as any deviation — this file is not edited to match the code.
If the code disagrees with this document, the code is wrong or the owner has
changed their mind, and either way it is a conversation to have, not a silent
edit.

---

## 0. How to work on this

Build this in the numbered phases at the end. After each phase: run typecheck,
lint, and tests; fix everything red; commit with a real message. Do not scaffold
all nine screens at once and leave them half-wired — a smaller number of
finished screens beats a full skeleton.

Before writing any UI code, write `DESIGN.md` containing the token table from §4
as actual CSS custom properties, and `ARCHITECTURE.md` containing the module
boundaries from §6. Then build against those files. If you deviate later, update
the file in the same commit.

Ask me before adding any dependency not listed in §3. Ask me before inventing a
scientific default (a threshold, a cutoff, a sign convention) — those are domain
decisions, not implementation details.

Stop and check in with me at the end of each phase. Do not silently keep going.

## 1. What this is

Wet-lab protein engineers have a goal in their head ("make this enzyme survive
65°C without killing activity") and a wall in front of them: the models that
could help — ESM, ProteinMPNN, ThermoMPNN, RFdiffusion, AlphaFold — are Python
repos with CUDA requirements, not tools. So they either don't use them, or they
get a one-off notebook from a computational colleague, run it once, and never
trust the output enough to spend $4,000 of ordering budget on it.

Codon Lab turns a plain-language engineering goal into a ranked, defensible
list of specific mutations, and then closes the loop with what actually happened
at the bench.

The user is a bench biologist with a PhD in biochemistry and zero ML background.
They know more molecular biology than this app ever will. Design for someone who
is skeptical, busy, and correct — not for someone who needs to be impressed.

## 2. The three things that make this worth building

Everything else is table stakes. These three are the product:

1. **Parse, then confirm — never silently interpret.** The user types a goal in
   English. The app parses it into an explicit structured objective and shows
   that parse back as editable chips: objective, constraints, budget, expression
   host, assay. Nothing runs until the user confirms the parse. A tool that
   guesses what "more thermostable" means and quietly proceeds is a tool that
   gets abandoned after the first surprising result.
2. **Every number is traceable.** Any score displayed anywhere can be traced, in
   two clicks, to: which model, which version and weights hash, which inputs,
   which run, at what time. Build a provenance record as a first-class entity,
   not a log file. This is what makes a PI sign off.
3. **The validation loop.** The user uploads measured results from the bench
   (Tm, kcat/KM, expression yield) and the app joins them to the predicted
   variants, shows predicted-vs-measured, computes Spearman/precision-at-k, and
   updates a per-model scorecard for this lab's own targets. Over three projects,
   the lab learns which predictor to trust for their chemistry. No competitor
   does this. It is the entire moat.

## 3. Stack

Do not substitute without asking.

- **Web:** Next.js 15 (App Router), TypeScript in strict mode, React 19
- **Styling:** Tailwind v4 with a custom token layer defined in `@theme` — tokens
  only, no arbitrary values scattered through JSX
- **Components:** build a small in-house primitives layer (`components/ui/`) —
  Button, Input, Select, Table, Popover, Dialog, Tabs, Tooltip, Badge, Toast. Use
  Radix primitives underneath for behavior/a11y. Do not install a component kit
  and use its defaults.
- **State:** TanStack Query for server state, Zustand for workbench UI state
  (selection, filters, panel sizes). No Redux.
- **Tables:** TanStack Table + TanStack Virtual. Result tables must handle 10,000
  rows at 60fps.
- **Structure viewer:** Mol\* (`molstar`) — embedded, controlled, wild-type/mutant
  toggle
- **Charts:** build them with D3 scales + plain SVG. No chart library.
- **Icons:** lucide-react, 16px, 1.5 stroke, never mixed with another set
- **API:** FastAPI (Python 3.12), Pydantic v2, SQLModel
- **DB:** Postgres via Docker Compose, Alembic migrations
- **Jobs:** Redis + RQ. Jobs idempotent, results content-addressed and cached on
  `hash(model_version + inputs)`
- **Tests:** Vitest + Testing Library, Playwright for two smoke flows, pytest for
  the scoring layer
- **Monorepo:** pnpm workspaces — `apps/web`, `apps/api`, `packages/schema`
  (shared Zod + Pydantic-generated types)

Ship a `docker compose up` that gets the whole thing running with seed data on
first try. Write the README last, and make it accurate.

## 4. Design system — read this section twice

The bar: a structural biologist opens this next to Benchling and Geneious and it
does not look like the odd one out. It should read as instrument software —
dense, quiet, precise, built by people who respect the user's time. Reference
feel: Linear's restraint, Benchling's density, Observable's data typography, a
Zeiss microscope control panel. Not a SaaS landing page.

### Tokens

**Type.** UI face: Inter Variable. Data/sequence face: JetBrains Mono. Two faces
total. Scale, in px: `11` (micro labels, table headers, uppercase 0.04em
tracking), `12` (secondary, captions), `13` (base UI size — everything default),
`15` (panel titles), `18` (page title), `24` (rare, project title only).
Line-height 1.45 body, 1.25 headings. Weights: 400, 500, 560. Never 700+, never
uppercase except 11px labels. Every numeral in a table, chart axis, or metric
readout gets `font-variant-numeric: tabular-nums`. Sequences, mutation codes
(`A123V`), accessions, and hashes are mono.

**Color.** Neutral-dominant, one accent, semantics reserved for meaning.

```
--canvas        #FBFBFA   page background
--surface       #FFFFFF   panels, tables
--surface-sunk  #F5F5F4   inset areas, code blocks, table headers
--border        #E7E5E4   1px hairlines — the primary structural device
--border-strong #D6D3D1   focused/active edges
--text          #1C1917
--text-muted    #57534E
--text-faint    #A8A29E
--accent        #1D4ED8   interactive affordances + selection ONLY
--accent-sunk   #EFF4FF   selected row background
--positive      #15803D   stabilizing / passed
--negative      #B91C1C   destabilizing / failed
--warn          #B45309   flags, epistasis warnings, demo-mode
```

Borders and background steps carry the hierarchy. Two shadows exist in the entire
app: popover and dialog. No glows, no colored shadows, no gradients anywhere
except inside data visualizations.

Data color is separate from UI color. ΔΔG and any signed quantity: diverging
RdBu, zero pinned to neutral, colorbar always shown with units and sign
convention. Conservation, likelihood, RSA: single-hue sequential (Blues), or
viridis for heatmaps. Never rainbow. Encode low confidence by desaturation and an
explicit ± interval — never by making text transparent.

**Space.** 4px grid. Table rows 30px (a 26px "compact" toggle in settings). Panel
padding 16px. Section gaps 24px. Form control height 30px. Radius: 4px on
controls, 6px on panels, 8px on dialogs. `rounded-full` only on status dots.

**Motion.** 120–160ms, `cubic-bezier(0.16, 1, 0.3, 1)`, opacity and transform
only. Popovers and dialogs fade+2px rise. Nothing else animates. No page
transitions, no stagger-in, no springs. Honor `prefers-reduced-motion` by cutting
to 0ms.

**Dark mode.** Real token values, not inverted lightness — `--canvas #131110`,
surfaces warmer than the canvas, borders at 12% white. Ship it if Phase 6 lands
early; otherwise leave the tokens defined and the toggle out.

### Layout and interaction

Three-pane workbench, resizable via drag handles, sizes persisted per user. Left
rail 240px collapsible. Inspector 380px. No modal for anything the user needs to
reference while working — use the inspector.

Tables, not cards, for anything list-shaped. Sticky headers, sortable columns,
right-aligned numbers, column visibility menu, row selection with shift-range,
and a persistent selection count in a bottom bar. Every table has a keyboard
path: `j`/`k` move, `x` selects, `Enter` opens the inspector.

`⌘K` command palette that actually works — jump to project, add a constraint,
start a run, open a variant by typing `A123V`. `?` opens the shortcut sheet.
`Esc` closes the topmost layer. Visible focus rings on every interactive element,
2px accent at 2px offset.

Design the empty, loading, and error state of every panel before the happy path.
Loading = skeletons matching the final layout's geometry, never a centered
spinner over the whole page. Errors state what failed, what it means, and the one
action that fixes it. Empty states name the next action.

### Copy

Sentence case everywhere. Terse. No emoji, ever, anywhere in the product. No
exclamation marks. No "AI ✨" language, no "powered by", no first-person from the
app ("I found 12 variants" — no; "12 variants" — yes). Buttons name their effect
and keep that name through the flow: `Start design run` → toast
`Design run started`. Units always shown, sign conventions always stated.

### Explicitly banned

Purple/blue or any decorative gradient · glassmorphism and `backdrop-blur` cards
· emoji · `rounded-3xl` · shadows on cards and buttons · a marketing hero inside
the app · 3-column feature-card grids · animated gradient borders · confetti ·
fake progress bars · sparkle icons · framer-motion page transitions · lorem ipsum
· centered full-page spinners · toast spam · "Oops! Something went wrong" ·
pill-shaped buttons · icon-only buttons without tooltips · more than one accent
color.

If a screen would look at home on a Product Hunt launch, it is wrong.

## 5. Screens

1. **Projects** — table of projects: target, organism, objective, run count, last
   activity, measured-variant count. Not a card grid.
2. **Target setup** — paste FASTA / fetch by UniProt accession / upload PDB / pull
   from AlphaFold DB. Residue numbering reconciliation is a required step with
   its own UI: show sequence numbering vs PDB author numbering vs construct
   numbering side by side, make the user pick the canonical scheme, and display
   that scheme's name next to every mutation code for the rest of the project.
   Off-by-one numbering is the single most expensive error this app can make.
3. **Constraints** — annotate the target before designing: catalytic residues,
   ligand/cofactor contacts, binding interface, disulfides, signal peptide,
   purification tag, do-not-touch regions. Draw on a linear sequence track and
   pick in the 3D view. Constraints are hard filters, and every filtered-out
   variant is retrievable with the reason shown.
4. **Goal composer** — free-text box, parsed into editable chips (§2.1). Show a
   plain-English restatement of the full parsed objective above the run button.
   Include a "what this run will and won't tell you" note — set expectations
   before the run, not after.
5. **Run view** — pipeline stages as a vertical list: retrieve structure → build
   MSA → score with each predictor → aggregate → filter by constraints → rank.
   Each stage shows model name, version, runtime, input hash, and status.
   Streaming logs behind a disclosure. Cancellable. Re-runnable with one
   parameter changed and diffable against the previous run.
6. **Variant workbench** — the main screen. Left: filters and constraint toggles.
   Center: virtualized variant table — rank, mutation, position, region
   (core/surface/interface), predicted ΔΔG ± CI, ESM log-likelihood ratio,
   conservation, RSA, distance to active site, predictor agreement, flags. Right:
   inspector — Mol\* focused on the residue with wild-type and mutant rotamers
   toggleable, local contact list, a plain-language _why this was proposed_
   paragraph derived from the actual feature values (not from an LLM guessing),
   and the provenance trail.
7. **Design set builder** — select variants into a set. Combinatorial builder for
   stacking mutations, with an unmissable warning that stacked effects are
   assumed additive and frequently are not (epistasis), and a flag on any pair
   within 8Å of each other. Running budget and cost estimate.
8. **Wet-lab handoff** — the thing that makes it real. Site-directed mutagenesis
   primers per variant (Tm-matched, with the algorithm and parameters stated),
   codon usage for the chosen host, an orderable gene-fragment CSV, a 96-well
   plate map, and a PDF design report with a full provenance appendix. This
   screen is why a lab uses the tool twice.
9. **Results intake and scorecard** — upload a CSV of measured values or paste
   from a plate reader; column-mapping UI with a preview; fuzzy-join to variants
   by mutation code with manual override. Then: predicted-vs-measured scatter per
   predictor, Spearman ρ, precision@10, calibration curve, and a persistent
   scorecard per predictor per target class that accumulates across the lab's
   projects.

## 6. Model layer

One interface, many providers. The UI must never import a model client directly.

```python
class Predictor(Protocol):
    id: str; name: str; version: str; weights_hash: str
    modality: Literal["stability", "fitness", "structure", "generative"]
    requires: Capabilities   # structure? MSA? max_len? GPU?
    citation: str
    def score(self, variants: list[Variant], ctx: TargetContext) -> list[Score]: ...
```

Implement: `ESMScorer` (masked-marginal log-odds), `StabilityPredictor`
(ThermoMPNN-shaped adapter), `StructureProvider` (AlphaFold DB / uploaded PDB /
ESMFold), `MSAProvider`, `GenerativeProvider` (ProteinMPNN / RFdiffusion — used
for scaffold and binder tasks, not pretended to be a point-mutation oracle). Each
provider declares what it cannot do, and the UI greys out objectives no available
provider supports rather than returning something worthless.

Aggregation must expose disagreement. Show per-model scores alongside the
consensus. When models disagree, that is the most useful signal on the screen —
surface it, don't average it away.

### Honesty requirements — non-negotiable

Ship a `MockProvider` so the full UI is usable without GPUs. It produces
deterministic, plausibly-shaped synthetic output. It must also:

- set a global demo flag that renders a persistent amber bar reading
  `Demo data — not model output` on every screen,
- badge every individual number it produced,
- watermark PDF exports and refuse to generate primers.

Never fabricate a scientific number outside this provider. If a model is
unavailable, the cell reads `—` with a tooltip explaining why. No imputation, no
"estimated" placeholders.

## 7. Domain rules that make biologists trust this

- Mutation codes: `A123V` and `p.Ala123Val` both rendered, always with the
  numbering scheme label.
- ΔΔG: state the sign convention in the column header and never change it —
  destabilizing positive, in kcal/mol, with a confidence interval. A bare point
  estimate is not acceptable output.
- Do not claim a Tm shift in °C from a ΔΔG prediction. Report predicted stability
  change and say what it does and does not imply.
- Classify each position as core / boundary / surface from relative solvent
  accessibility, and use that in the rationale — the strategies differ (core
  packing vs surface charge).
- Surface the classical thermostability heuristics as filterable tags where the
  geometry supports them: proline substitution in flexible loops, glycine→X in
  helices, new salt bridges, engineered disulfides, hydrophobic core repacking,
  consensus/ancestral substitutions from the MSA.
- Never propose mutations at constrained positions without an explicit override,
  and log the override.
- Flag any position with >90% MSA conservation as high-risk regardless of what
  the models say.
- Seed the app with two real targets and, for the validation loop, a
  deep-mutational-scanning dataset with real measured values (ProteinGym is the
  right source) so the scorecard screen is demoable with true numbers on day one.

## 8. Data model

`Project` · `Target` (sequence, numbering schemes, structures) · `Constraint` ·
`Goal` (raw text + parsed spec + confirmed-at) · `Run` (pipeline config, status,
timing) · `ModelVersion` (name, version, weights hash, citation) · `Variant`
(mutations[], derived features) · `Score` (variant, model_version, value,
uncertainty, run) · `DesignSet` · `Experiment` (assay, protocol, date, operator) ·
`Measurement` (variant, metric, value, sd, replicate) · `ProvenanceEvent`
(append-only).

`Score` never exists without a `ModelVersion` and a `Run`. Enforce it at the DB
level.

## 9. Phases

1. Monorepo, Docker, migrations, token layer, `components/ui/` primitives, one
   styled page. **Done when:** `DESIGN.md` tokens are the only source of
   color/type in the codebase.
2. Target setup + numbering reconciliation + sequence track. **Done when:** I can
   load a UniProt accession and a PDB, reconcile numbering, and every downstream
   mutation code is unambiguous.
3. Constraints + goal composer with confirmable parse. **Done when:** no run can
   start from an unconfirmed parse.
4. Job queue, `Predictor` interface, `MockProvider`, run view with live stages.
   **Done when:** a run completes end to end with demo banners correct
   everywhere.
5. Variant workbench — virtualized table, Mol\* inspector, rationale, provenance
   drawer. **Done when:** 10,000 rows scroll at 60fps and any score traces to a
   model version in two clicks.
6. Real `ESMScorer` + `StabilityPredictor`, disagreement surfacing, agreement
   column.
7. Design set builder, epistasis warnings, wet-lab handoff exports.
8. Results intake, join UI, predicted-vs-measured, calibration, persistent
   scorecard.
9. Playwright smoke flows, a11y pass (keyboard-only traversal of the workbench,
   contrast audit), README, accurate screenshots.

## 10. Definition of done

Keyboard-only users can complete the full flow. Every number traces to a model
version. Nothing in the UI is fabricated. A skeptical PI can read the exported
PDF and reproduce the run. And the app looks like it was made by a design team
that has never heard of a landing page.
