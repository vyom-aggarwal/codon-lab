# CatalystAI — architecture

Module boundaries. **If you deviate, update this file in the same commit.**

---

## 1. Workspace layout

```
catalyst-ai/
├── apps/
│   ├── web/         Next.js 15 App Router, React 19, TypeScript strict
│   └── api/         FastAPI, Python 3.12, Pydantic v2, SQLModel
├── packages/
│   └── schema/      Zod schemas + types generated from the API's OpenAPI document
└── docker-compose.yml
```

`packages/schema` is the **only** module both apps depend on. `apps/web` never imports
from `apps/api` and vice versa; they meet at the HTTP boundary and at the shared schema.

---

## 2. The rule that matters most

> **The UI must never import a model client directly.**

There is exactly one seam between "what the product asks for" and "what a model can do",
and it is the `Predictor` protocol (§4). The web app knows about _scores_ and _model
versions_; it does not know that ESM exists. Concretely:

- `apps/web` may not import anything from a provider module, may not name a model in a
  conditional, and may not encode a model's quirks in a component.
- Anything the UI needs to vary by model arrives as **data** — through
  `Capabilities` and `ModelVersion` records — never as a branch in a component.

The test for whether this holds: adding a fourth stability predictor must touch zero
files under `apps/web/components`.

---

## 3. Layers in `apps/api`

Dependencies point downward only. A module never imports from a layer above it.

```
  routes/        HTTP surface. Pydantic request/response models. No business logic.
     │
  services/      Orchestration: build a run, aggregate scores, apply constraints.
     │           This is where domain rules from spec §7 live.
     │
  providers/     Predictor implementations. The ONLY place a model client may be
     │           imported. Each provider is self-contained and declares its own
     │           Capabilities. MockProvider lives here too.
     │
  features/      Derived structural features: solvent accessibility, burial
     │           class, distance to the annotated active site. Beside providers/
     │           rather than inside it, because these are neither model output
     │           nor a download — they are a deterministic calculation over
     │           coordinates the user loaded. See §11.
     │
  sources/       External retrieval and parsing: UniProt, RCSB, AlphaFold DB,
     │           PDB and FASTA. No model runs here — these are downloads — which
     │           is why they sit beside providers/ rather than inside it.
     │
  parsers/       Free-text goal → structured objective. A language model reads
     │           the sentence; a deterministic rule parser runs whenever it
     │           cannot. Not providers/: a parser produces no scientific number
     │           and has no weights hash to cite. See §10.
     │
  domain/        Pure logic with no I/O and no database: amino acid nomenclature,
     │           mutation codes, numbering reconciliation. Everything here is a
     │           function of its arguments, and is where the numbering rules in
     │           §9 are actually enforced.
     │
  models/        SQLModel tables (spec §8). No behaviour beyond validators.
     │
  db.py          Engine + session. Sync psycopg 3 — the same session code path is
                 used by routes, RQ workers, and Alembic.
```

`workers/` sits beside `routes/` as a second entry point at the same level: it consumes
`services/` exactly as routes do. A job must be runnable from either without changes.

### Why sync

The workload is queue-bound, not connection-bound — real work happens in RQ workers, not
in request handlers. Sync SQLModel means routes, workers, Alembic, and pytest share one
engine and one session idiom, instead of needing a parallel sync engine for the three
contexts that cannot be async.

---

## 4. The model layer

One interface, many providers.

```python
class Predictor(Protocol):
    id: str
    name: str
    version: str
    weights_hash: str
    modality: Literal["stability", "fitness", "structure", "generative"]
    requires: Capabilities        # structure? MSA? max_len? GPU?
    citation: str
    is_mock: bool                 # added — see below
    objectives: frozenset[Objective]
    metrics: tuple[MetricSpec, ...]

    def score(self, variants: list[VariantInput], ctx: TargetContext) -> list[ScoreValue]: ...
```

Three deviations from the protocol as sketched in the specification, all made for the
same reason — a provider must be unable to reach past its own seam:

- **`score` returns `ScoreValue`, not `Score`.** A `Score` cannot exist without a run and
  a model version (§5), and a provider knows about neither. `services/runs` is the only
  thing that turns one into the other, and it cannot do so without both. This is the
  integrity rule showing up in the type system: **a provider is structurally incapable of
  writing an untraceable number.**
- **`score` takes `VariantInput`, not the `Variant` table row.** A provider that took an
  ORM row would need a database session. `VariantInput` is a pure dataclass, which is
  also why every provider is testable with no database at all.
- **`is_mock`, `objectives` and `metrics` are added.** They are what lets the interface
  vary by model without ever naming one: `is_mock` drives the demo bar and the per-number
  mark, `objectives` greys out what nothing supports, and `metrics` carries each column's
  unit and sign convention so the convention lives with the provider rather than in a
  component a second screen could contradict.

Every attribute is declared read-only on the protocol. A predictor's identity is what the
provenance trail is built on, and nothing may reassign it after the fact — which also
lets implementations be frozen dataclasses.

Implementations: `ESMScorer` (masked-marginal log-odds), `StabilityPredictor`
(ThermoMPNN-shaped adapter), `StructureProvider` (AlphaFold DB / uploaded PDB / ESMFold),
`MSAProvider`, `GenerativeProvider` (ProteinMPNN / RFdiffusion — for scaffold and binder
tasks, **not** presented as a point-mutation oracle). As of Phase 6 the registry holds
`ESMScorer` (ESM-2 650M, masked marginals), `ThermoMPNN` (vendored, §14.3) and
`MockProvider` as two synthetic predictors. `CATALYST_PROVIDERS` selects between them;
`mock` and `real` are the two shorthands.

**Every provider declares what it cannot do, twice over.** `available()` asks whether the
predictor exists here at all — runtime installed, weights on disk, readable. `requires.unmet(ctx)`
asks whether it suits *this target*. A predictor failing the first is *active* but not
*runnable*: `services/providers.runnable()` excludes it, so no run plans a stage for it and
the objectives it covered grey out with its reason. It never falls back to another provider,
and it never reports a placeholder `weights_hash` — a made-up hash is indistinguishable from a
real one in the provenance trail, which is worse than an absent column.

`Capabilities.unmet(ctx)` returns the
reason a predictor cannot run here, or `None`. The pipeline skips it with that reason,
which travels to the cell and is shown on hover. The UI greys out objectives that no
available provider supports, rather than running them and returning something worthless.

**Which predictors are active is derived, not configured twice.** `CATALYST_PROVIDERS`
names ids; `services/providers` resolves them and answers *demo mode* from
`Predictor.is_mock`, not from the string `mock` appearing in an environment variable.
Those two answers agree today and would drift the first time a provider was renamed —
and the drift would be a screen with no amber bar over fabricated numbers. An id that
matches no predictor is reported by `/meta` and refuses to start a run, because a typo
that silently disables a predictor produces a run that looks complete and is missing a
column.

### Aggregation exposes disagreement

Per-model scores are shown alongside the consensus. When models disagree that is the most
useful signal on the screen — it is surfaced, not averaged away.

Concretely, in `domain/aggregate`:

- **Scores are never averaged.** A ΔΔG in kcal/mol and a log-likelihood ratio are not on
  the same scale. Each predictor's values are converted to ranks within its own series
  first, and only ranks are combined. Averaging the raw values would produce a number
  with no meaning that nevertheless sorts, which is the worst available failure.
- **Disagreement is the spread between those normalised ranks**, reported beside the
  consensus and never folded into it. There is no threshold separating "agreement" from
  "disagreement" — the number is shown and the reader judges it.
- **One opinion is not unanimity.** A variant scored by a single predictor gets a null
  disagreement, not zero, and carries the count of predictors that scored it.

### Aggregation, filtering and ranking are derived, not stored

They are deterministic arithmetic over scores that are already persisted, so a stored
copy could only ever be a second answer capable of disagreeing with the first. The
consensus is also not a model output and could not be written as a `Score` without
inventing a `ModelVersion` for the arithmetic.

The one exception is the **constraint filter**, which is written to an append-only
`ProvenanceEvent` at run time: constraints change, and a run is a record of what
happened. Recomputing the filter from today's constraints would silently rewrite what a
run did last week.

### Honesty boundary — non-negotiable

`MockProvider` produces deterministic, plausibly-shaped synthetic output so the full UI
is usable without GPUs. It must:

- set a global demo flag rendering a persistent amber `Demo data — not model output` bar
  on every screen,
- badge every individual number it produced,
- watermark PDF exports and **refuse to generate primers**.

**No scientific number is ever fabricated outside this provider.** If a model is
unavailable the cell reads `—` with a tooltip explaining why. No imputation, no
"estimated" placeholders.

---

## 5. Provenance

`ProvenanceEvent` is append-only and is a **first-class entity, not a log file**.

Every score rendered anywhere traces in two clicks to: which model, which version and
weights hash, which inputs, which run, at what time.

Enforced at the database level, not by convention:

- `Score.model_version_id` — `NOT NULL`, FK to `modelversion`
- `Score.run_id` — `NOT NULL`, FK to `run`

A `Score` cannot exist without both. This constraint is the reason a PI can sign off, and
it is not negotiable in any later migration.

---

## 6. Jobs

Redis + RQ. Jobs are **idempotent**. Results are content-addressed and cached on
`hash(model_version + inputs)`, so a re-run with one parameter changed re-executes only
what that parameter affects, and the run diff in the run view is exact rather than
inferred.

- `catalyst/queue.py` holds the client, beside `db.py` rather than inside `workers/`.
  Both the API (which enqueues) and the worker (which consumes) need it, and a route
  importing an entry point is the one direction §3 does not allow. The job is referenced
  by dotted path, so the API process never imports the worker module and cannot acquire
  the ability to execute a run inside a request handler.
- **The service does not know about the queue.** `runs.create` takes a `dispatch`
  callable; routes pass `queue.enqueue_run`, tests pass a recording fake. A dispatch that
  fails marks the run failed with the reason, rather than leaving it queued forever
  looking like it is about to start.
- **Content addressing is pinned** in `domain/hashing`: sorted keys, no whitespace, no
  ASCII escaping, floats as `repr`, non-finite numbers refused. A cache key that varies
  with dictionary order misses every time; one that collides serves one model's numbers
  as another's.
- **Cache reuse is visible.** A scoring stage whose input hash matches an earlier
  succeeded stage copies that run's scores into this run — new rows, this run's id, the
  same model version — and says so in its log. `RunStage.input_hash` is what the run diff
  reads to decide whether a stage re-executed.
- **Idempotency** is enforced twice: `execute` returns immediately unless the run is
  still `pending`, and score inserts are `ON CONFLICT DO NOTHING` against `uq_score`, so
  a worker killed mid-stage can be replayed without producing a second set of numbers for
  the same cell.
- **Cancellation** sets the run's status and appends a `ProvenanceEvent`; the executor
  re-reads the run between stages and stops there. A stage already executing is allowed
  to finish and record what it did — it happened, and a provenance trail that omits it is
  a lie of omission.

---

## 7. State in `apps/web`

| Kind                                              | Owner                                      |
| ------------------------------------------------- | ------------------------------------------ |
| Initial page data (projects, targets, schemes)    | **Server components**, fetched per request |
| Mutations (create, attach, reconcile, confirm)    | **Server actions** in `app/actions.ts`     |
| Live/polled state (run progress, workbench table) | **TanStack Query** — arrived in Phase 4    |
| Workbench UI state (selection, filters, panels)   | **Zustand** — arrived in Phase 5           |
| URL-addressable state (project, run, variant)     | **The route** — deep links must work       |

No Redux. Server data is never copied into Zustand; the store holds selection and view
state that references server data by id.

**Why the split.** Phases 2 and 3 have no polling and no optimistic updates, so a
client-side cache would be a second copy of state with nothing to justify it — server
components fetch, server actions mutate, `revalidatePath` refreshes. TanStack Query
entered in Phase 4, where run progress genuinely streams and a cache earns its place.
Adding it earlier would have meant a provider wrapping the tree that nothing reads.

The run view server-renders the run and then polls the same endpoint, so a reloaded page
and a polled one cannot disagree. **Polling stops when the API says the run is terminal**
— `Run.is_terminal` is computed server-side rather than the client keeping its own list
of which statuses are final. `QueryClient` is created inside component state, never at
module scope, because a module-level client is shared between requests on the server and
would leak one user's data into another's render.

Server actions return `{ok, message, remedy}` rather than throwing, so an API failure
reaches the screen with its remedy intact instead of collapsing into an error boundary.

Tables are TanStack Table + TanStack Virtual from Phase 5. The bar is **10,000 rows at
60fps**, which means row components are memoised and cell renderers stay pure. The
small tables before then are the plain `components/ui/table` primitives.

---

## 8. Component boundaries in `apps/web`

```
components/ui/          Primitives. Radix underneath for behaviour and a11y; every
                        visual decision is ours. Knows nothing about proteins.
components/<domain>/    Domain components. Compose primitives. Know about proteins,
                        know nothing about HTTP.
app/                    Routes. Data fetching and composition.
lib/                    Pure helpers. No React, no network.
```

A primitive that grows a protein-specific prop has been put in the wrong directory.

---

## 9. Numbering — the expensive error

Off-by-one residue numbering is the single most costly mistake this application can make,
so numbering is modelled explicitly rather than assumed:

- A `Target` carries **multiple** numbering schemes (sequence, PDB author, construct).
- Reconciliation is a required setup step with its own UI, not a silent inference.
- The chosen canonical scheme's **name is rendered next to every mutation code** for the
  remainder of the project.
- Canonicality lives on `NumberingScheme.is_canonical`, guarded by a partial unique
  index (`uq_numbering_canonical`), so a target cannot have two canonical schemes.
  A pointer on `Target` would have closed a foreign-key cycle with
  `NumberingScheme.target_id` and left the two tables unorderable for creation.
- Mutation codes render in both forms — `A123V` and `p.Ala123Val` — always with the
  scheme label.

No layer is permitted to convert between schemes implicitly. Conversion is an explicit,
audited operation in `services/`.

### Sequence index and canonical label are different things

They are kept apart deliberately, because conflating them *is* the off-by-one:

- **`Variant.code` is written in the canonical scheme.** `services/runs` reads the
  confirmed scheme's labels and hands them to `domain/variants`, which composes the code
  from the label. On the seeded lipase, sequence index 108 is `S77A` — a variant named
  `S108A` would point a bench scientist 31 residues away from the residue it means.
- **`Variant.position` is the 1-based sequence index**, and is what constraints,
  structures and features join on. It is exposed to the interface as
  `sequence_position` and is never displayed as a residue number.
- **A position the canonical scheme cannot name produces no candidate at all.** Three
  cases: the scheme does not cover it, the residue is not one of the standard twenty, or
  the label cannot be written as a mutation code — which is what happens to a signal
  peptide under mature-protein numbering, where labels run zero and below. Each is
  counted and stated in the scoring stage's log rather than approximated.

Writability is decided by `domain/mutation.parse_mutation`, so there is one definition of
what a mutation code is rather than a second rule invented at the enumeration site.

---

## 10. Goal parsing — the confirmation gate

> **No run may start from a parse the user has not confirmed.**

Enforced in `services/goals.require_confirmed`, not in the UI. A check that exists only
on a screen is a check the API does not have, and Phase 4's worker is a second caller
that would bypass it.

- **The parser has no scientific authority.** It extracts what the sentence says and
  never supplies what it does not. Every field is optional; an absent field means "not
  stated", never a default. The JSON schema admits `null` for every field precisely so
  that "not stated" is never harder to express than a guess.
- **Two implementations, one interface.** Claude reads the sentence. A deterministic
  rule parser runs when there is no API key, on any API failure, on malformed output,
  and on a safety refusal — which returns HTTP 200 with `stop_reason: "refusal"`, so the
  stop reason is checked before content is ever read. A rule-based parse is always
  badged, because it matches phrases rather than reading sentences.
- **Editing a chip clears the confirmation.** What the user agreed to was that
  objective, not that database row.
- **The restatement is built from the parsed fields, never from the input.** Echoing the
  goal back would look correct no matter what the parser actually understood.
- **Expectations are shown before the run**, including that a stability prediction does
  not convert to a Tm shift and that stacked mutations are assumed additive.

### Constraints

Hard filters, so nothing is applied without acceptance. UniProt annotations are imported
as _suggestions_ carrying their source, and every position is translated out of UniProt
numbering into the target's canonical scheme first. On the seeded lipase, UniProt
annotates the catalytic nucleophile at 108 and the confirmed mature-protein scheme calls
it Ser77 — importing the raw number would misplace the most important residue on the
protein by 31 positions.

### How reconciliation actually works

1. **Exact correspondence first.** The chain is split into runs of consecutive author
   numbering; every run must be placeable at one shared offset. The offset relates
   author numbering to sequence index — _not_ position within the resolved residues,
   because author numbering stays continuous across an unresolved loop while the
   resolved list does not. Indexing the resolved list would slide every residue after
   a gap by the length of that gap.
2. **More than one placement is a question, not a coin flip.** Repeats produce an
   `AMBIGUOUS` outcome listing the candidates. The user picks.
3. **Alignment is never reached automatically.** `reconcile()` returns
   `NEEDS_ALIGNMENT` and stops. `align()` runs only on an explicit user action, and
   reports every difference before anything is applied.
4. **Insertion codes go straight to alignment.** 100/100A/100B occupy three sequence
   positions but advance the author number once, so the constant-offset assumption
   does not hold and is not approximated.

Alignment is semi-global Needleman-Wunsch with affine gaps and **identity scoring, not
BLOSUM62** — this maps a structure onto its own sequence, where the question is "which
residue is which", not "are these homologous". A substitution matrix would let a
chemically conservative difference slide into a match, which is the silent off-by-one
being guarded against. End gaps are free so a partial construct is not penalised for
the region it does not cover. The parameters are stored on every scheme produced this
way and shown in the UI; an alignment whose parameters are not stated is not
reproducible.

### Stored schemes are label lists, not offsets

`NumberingScheme.offsets` holds one label per sequence position, null where the scheme
does not cover it. A single integer offset would be a lie for all three of the cases
that actually occur: Ambler numbering skips residues by convention, crystal structures
leave gaps, and insertion codes are not integers.

### Confirming is separate from computing

Saving a reconciled mapping creates a scheme. It does **not** make it canonical.
`confirm_canonical` is a distinct call, writes a `ProvenanceEvent`, and is the only
thing that makes a target designable. Until then the API refuses to render a mutation
code at all, with a 409 — a code rendered against an unconfirmed scheme is precisely
the ambiguity this phase removes.

---

## 11. Derived features

Solvent accessibility, burial class and distance to the active site are computed, not
predicted. They live in `features/` — a layer of their own, beside `providers/` — and
specification §2.2 applies to them exactly as it applies to a model score: every number
traces to the parameters that produced it.

### The calculation is not ours

`biotite.structure.sasa` (Shrake-Rupley, ProtOr radii of Tsai et al. 1999) rather than an
implementation of our own. The hidden parameter in a solvent-accessibility calculation is
not the probe radius, it is the van der Waals radii set, and an unvalidated radii table
moves residues across the core/surface boundary without changing a coordinate.

That claim is measured, not asserted. On TEM-1 (PDB 1BTL, 263 residues):

| Change                             | Residues that change region | Correlation with published DSSP |
| ---------------------------------- | --------------------------- | ------------------------------- |
| ProtOr → uniform radius            | 8 (3.0%)                    | **rises** to 0.998              |
| Tien 2013 theoretical → Miller 1987 | 27 (10.3%)                  | unchanged (same ASA)            |

The first row is why `tests/test_sasa.py` carries **two** tests rather than one.
Agreement with published DSSP output validates the absolute numbers and catches gross
errors — wrong probe radius, hydrogens included, ligands in the reported value. It
provably cannot catch a radii swap, so a golden per-residue table pins the radii set and
the normalisation table as well. Both fixtures are committed and the suite stays
hermetic; the DSSP files are real output from the PDB-REDO DSSP databank, and a test
asserts they were computed on the same coordinates this repository feeds to biotite.

#### Adding a reference fixture — required steps

Fixtures are **pinned in the repository and never re-fetched at test time.** A test that
downloads its own reference can fail because a server changed, and — worse — can silently
start validating against different coordinates.

Any new reference fixture must:

1. commit both files, the coordinates and the reference output, side by side;
2. record provenance in `tests/fixtures/README.md`: the URL, the date, and the tool
   version that produced the reference;
3. **assert the reference was computed on the committed coordinates.** DSSP prints CA
   positions, so the check is a coordinate comparison; another tool needs whatever
   equivalent it offers. `test_the_dssp_fixture_was_computed_on_the_vendored_coordinates`
   is the existing example.

Step 3 is not optional and is not satisfied by "they came from the same PDB id". The
current fixtures agree to 0.0 and 0.1 Å because the DSSP databank computed them from the
deposited entries — but a re-refined structure (PDB-REDO's own output, a newer deposition)
would not, and the difference would show up as an unexplained tolerance failure long after
whoever added the fixture had moved on.

### Every parameter is stated

- **Normalisation**: `domain/constants/max_asa` — Tien et al. 2013, theoretical column,
  with the DOI. One copy, because a second copy is a second answer to which residues are
  buried. Miller 1987 and Rose 1985 understate the maxima and produce residues at RSA
  1.00, where the theoretical set tops out at 0.84 on the same coordinates.
- **SASA**: probe 1.4 Å, 1000 points, Fibonacci distribution, ProtOr radii, heavy atoms
  only, waters and monoatomic ions stripped. No library defaults.
- **Cutoffs**: core RSA < 0.25, boundary 0.25–0.40, surface > 0.40. A **project setting**
  (`Project.settings`) rather than a constant, because it is a scientific decision.
- **Coordinates**: whatever the user loaded, described as it actually is. A dimer-interface
  residue is buried in the assembly and exposed in the monomer, and that difference decides
  the mutation, so the manifest states what was measured rather than claiming an assembly.
- **Ligands**: excluded from the reported ASA — a cofactor is not the protein — but a
  second pass includes them and flags any residue whose RSA drops by more than 0.10.
  Without that flag the apo calculation makes active-site residues look solvent-exposed,
  which is the most misleading thing the column can say.

All of it goes into a `FEATURES_COMPUTED` provenance event, per run, alongside the code
version. The event is what `GET /runs/{id}/ranking` reads: features are **not** recomputed
on read, so changing a project's cutoffs tomorrow cannot restate what a run said today.

### The active site is annotated, never inferred

It is exactly the residue set the user marked catalytic or ligand-contacting on the
constraints screen. No pocket detection, no database lookup, no heuristic. With none
annotated the column reads `—` with a tooltip pointing at the constraints screen.

Distance is the minimum separation between any non-hydrogen atom of the residue and any
non-hydrogen atom of that set — not Cα–Cα. An arginine side chain reaches roughly 7 Å past
its own Cα, so a Cα measurement would report a residue as clear of the pocket while its
side chain sits inside it.

### Numbering, once more

Features are computed only when a **reconciled PDB-author scheme** exists for the
structure, and they are keyed by sequence index on the way out. Each carries the
structure's own `author_label` as well, because the viewer addresses residues in author
numbering while the table shows the canonical scheme — on the seeded lipase those are 108
and Ser77 for the same residue. Nothing converts between them by arithmetic (§9).

---

## 12. The workbench

Screen §5.6. Three panes, resizable, sizes persisted; the whole ranking in the middle.

**Virtualisation.** TanStack Table for the column model and sorting, TanStack Virtual for
rendering. The work per frame is constant rather than proportional to the row count: only
the visible window plus overscan is mounted, rows are memoised, and each row subscribes to
its own selection flag so clicking one row re-renders one row. Measured on a 10,450-row
ranking: 32 `<tr>` in the DOM and 772 DOM nodes for the whole page.

Semantic table markup is kept — spacer rows above and below the window give the scroll its
height, rather than absolutely positioning rows out of the table.

**Row height is duplicated into JavaScript**, because virtualisation needs it as a number.
`test/workbench.test.ts` asserts the constant still matches `DESIGN.md`.

**The rationale is a pure function** of the row (`lib/rationale.ts`), never a language
model. Each clause names the field it rests on, so it can be checked against a column, and
a feature that was not measured produces no sentence rather than a hedge. A test asserts
that every numeral in the composed text appears in the row's own data.

**Conservation is not rendered.** It is in the column menu, disabled, labelled "Requires
MSA (Phase 6)". A column where every cell is an em dash trains the reader to stop reading
em dashes, and the dash means something specific: unavailable, here is why.

**Mol\*** is created headless (`PluginContext` with a bare canvas), not through
`createPluginUI`, which would bring another product's toolbars into the inspector. It is
dynamically imported and browser-only. Coordinates are served by our own API
(`GET /targets/{id}/structure`) so the content hash recorded at attach time is verified on
the way through and the viewer cannot render a file that changed underneath the target.

### Decision: mutant side chains are not modelled

Specification §5.6 asks for a wild-type/mutant rotamer toggle. There is no toggle, and
this is a decision rather than an omission.

Placing a mutant side chain requires a side-chain packer, which is not in this stack. A
toggle that redrew the wild-type residue under a "mutant" label would be fabricating
structural data — the one thing this product must not do — and it would be the most
convincing fabrication in the build, because a rendered side chain looks like a
measurement. The inspector states the limitation instead.

**The path forward, when a packer enters the stack:** place the most probable rotamer
from a backbone-dependent rotamer library (Dunbrack), label it as the most probable
rotamer rather than as a prediction, and **do not energy-minimise it**. Minimising would
produce a pose that looks like a computed structure and is not one; the library
probability is a citable statement about backbone-conditioned side-chain preference, and
that is exactly as much as should be claimed. Not Phase 6 scope. It is the first thing to
revisit when a packer lands.

---

## 13. No validation claim rests on a rank statistic alone

A standing rule, and the most general thing this build has learned.

It came out of the solvent-accessibility work. Agreement with published DSSP output
was supposed to validate the van der Waals radii set; it cannot, because **a
correlation statistic is invariant to the transform that produces the error it is
meant to catch**. Swapping ProtOr for a uniform radius on TEM-1 moved 8 residues
across a region boundary and *raised* correlation with DSSP to r = 0.998. The test
passed more convincingly while the answer got worse.

Correlation and rank statistics are invariant to monotonic transforms. A systematic
offset, a scale error and a miscalibration are all monotonic. So a rank statistic is
structurally incapable of detecting the errors most likely to be present.

**The rule.** Any claim that a number is *right* — not merely ordered — must be
supported by a statistic sensitive to absolute value. In practice: a rank or
correlation measure may appear beside an error measure and a bias measure, never
alone, and never as the headline.

This has three consequences already written into the build, and it applies to
anything added later.

### Solvent accessibility (Phase 5, shipped)

Two tests, because one could not do the job: agreement with published DSSP for the
absolute values, plus a golden per-residue table pinning the radii set and the
normalisation table. §11 has the numbers.

### Predictor agreement (Phase 6)

The column is labelled **agreement** and never *confidence*, and its tooltip says
why in as many words: two models agreeing is not evidence that either is right.
Predictors trained on overlapping data share their biases, so agreement measures
how alike two models are, not how close either is to the truth. Where they disagree
is informative; where they agree, nothing has been established.

`MetricSpec` carries the sign convention for exactly this reason — the label lives
with the provider, so a second screen cannot quietly rename it.

### The scorecard (Phase 8)

The serious case, because the scorecard is the moat and its whole job is telling a
lab which predictor to trust.

Spearman ρ and precision@k are both rank statistics. **A predictor offset by a
constant +2 kcal/mol scores ρ = 1.00 and precision@10 = 1.0 while being useless for
the decision the user is actually making**, which is absolute: will this variant
hold at 65 °C.

Every predictor scorecard therefore reports, together and in one view:

| Kind      | Statistic                        | Answers                                |
| --------- | -------------------------------- | -------------------------------------- |
| Rank      | Spearman ρ, precision@k          | Does it put the right variants on top? |
| **Error** | **MAE, kcal/mol**                | **How far off is it?**                 |
| **Bias**  | **Mean signed error, kcal/mol**  | **Is it off in one direction?**        |

The bias term is rendered **visually adjacent to the rank term**, not in a detail
panel or behind a tab. A predictor that ranks perfectly and sits 2 kcal/mol high
must show both facts in one glance, or the scorecard has failed at the only job it
has. A headline that is a rank statistic alone is a defect, not a simplification.

---

## 14. Real predictors — delegated decisions

Phase 6 replaces the synthetic set with real models. Every decision below was
delegated to the assistant by the project owner with its reasoning, and each
records **what would change it**, because a delegated decision with no stated
trigger becomes folklore.

### 14.1 Checkpoint: `esm2_t33_650M_UR50D`

The 650M checkpoint, not 150M, despite costing 31 minutes on a 550-residue target
against 4.9 for 150M (measured on this machine: CPU only, no CUDA, no XPU).

The cost does not recur. `_reuse_scores` keys on the model version, the target,
`TargetContext.cache_key()` and the candidate set — and the context key excludes
the objective, so a scored target is reused across goals and across projects. The
expensive pass is paid once per (target, checkpoint, candidate set); 31 minutes
paid once is not a reason to take a weaker model. 650M is the standard checkpoint
for zero-shot variant effect.

`JOB_TIMEOUT_SECONDS` is 3600 rather than 900 for the same reason: the first pass
on a large target genuinely takes half an hour, and a timeout that kills it would
make the cache impossible to fill.

**Measured afterwards, and the number is tighter than it looks.** A full run on
the 212-residue lipase completed in 3363s — 93% of the 3600s budget. The ESM-2
stage alone took 3293s, or 15.5s per position, against 3.4s per position measured
with the machine otherwise idle. The 4.6x gap is CPU contention: a shared machine
is the realistic case, and eight threads are already saturated by one forward
pass, so anything else running competes directly.

At the observed rate a 550-residue target needs ~142 minutes and would blow
through the timeout. **The cap is adequate for the seeded lipase and not for the
luciferase target already in the database.** Raising it further is one option;
so is making the scoring stage resumable, so a killed pass does not discard the
positions it already scored. That is a decision for the owner, not a constant to
edit quietly.

**150M is deliberately not registered as a second `ModelVersion`.** Adding one is
a one-line provider registration, and Phase 8 — where a scorecard makes comparing
checkpoints meaningful — is when it earns its place. Registering it now would ship
a selector nobody uses.

*What would change it:* a GPU, which makes the argument moot; or Phase 8 showing a
per-lab reason to compare checkpoints, which is when 150M gets registered beside
650M rather than instead of it.

### 14.2 Scoring: masked-marginal, as `BRIEF.md` §6 specifies

One forward pass per position, each with that position masked. The alternative —
wt-marginal, a single pass over the wild-type sequence — is roughly 200x cheaper
on a 212-residue target and is a published scheme, but it is a *different* scheme
and generally weaker.

It only wins on per-run speed, and per-run speed is not the constraint: the cache
makes the cost per-target, not per-run. Deviating from a scientific method the
brief names, to save a one-time cost that is already acceptable, is a bad trade.
wt-marginal is **not** registered as an alternative either, for the same reason
150M is not.

*What would change it:* the brief changing. Not a performance argument.

### 14.3 ThermoMPNN is vendored at a pinned commit

Not on PyPI, so it is vendored rather than depended on. Pinned to an exact commit
SHA — recorded in `providers/thermompnn.py` beside the licence — because a moving
`main` would silently change what a stored `weights_hash` refers to, and the whole
point of that field is that it does not move.

*What would change it:* an upstream release on PyPI, or a deliberate upgrade, which
is a new SHA and a new `ModelVersion` rather than an edit to an existing one.

### 14.4 Which objectives each predictor may be offered for

`Predictor.objectives` decides what the goal composer greys out. These are stated
per real predictor and are **not** inherited from `mock_fitness`, whose seven
objectives were chosen so the interface was exercisable and were never a claim
about any real model.

| Predictor  | Offered for                                                                   | Not offered for                        |
| ---------- | ----------------------------------------------------------------------------- | -------------------------------------- |
| ESM-2      | thermostability, activity, expression, solubility, binding affinity           | **specificity, solvent tolerance**     |
| ThermoMPNN | thermostability                                                               | everything else, incl. solvent tolerance |

**Why ESM-2 is refused specificity and solvent tolerance.** Its log-likelihood
ratio is an evolutionary-plausibility signal. It cannot distinguish substrate
selectivity — a variant that switches specificity while remaining perfectly
plausible evolutionarily is exactly the case it is blind to — and there is no
evolutionary signal for tolerance of a non-natural solvent, because nothing in the
training distribution was selected for it.

**Why ThermoMPNN is refused solvent tolerance.** It predicts the free energy change
of folding. That is a different physical property, and offering it would invite the
reading that a stable protein is a solvent-tolerant one.

**Both are offered for thermostability on purpose.** A sequence-based evolutionary
prior and a structure-based ΔΔG predictor disagreeing on the same variant is
precisely the signal `BRIEF.md` §6 says to surface rather than average away — and
per §13, their agreeing is not evidence that either is right.

ESM-2's column is labelled an **evolutionary-plausibility prior**, not evidence for
the objective in question. That label lives on `MetricSpec` and therefore travels
with the provider, so a second screen cannot quietly restate it.

*What would change it:* evidence, per objective. A specificity benchmark showing the
LLR carries selectivity signal would be a reason to add it; an intuition would not.
