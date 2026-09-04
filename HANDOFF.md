# Start here

You are picking up a multi-session build. This file orients you; it is the first
thing to read and the last thing to update.

**Status current as of 2026-09-03.** All nine phases are built and committed on
`main`, and the API has since been made deployable: identity, per-project
ownership and a ceiling on queued work. **The build is still not finished**, and
the difference is the point. §12 walks `BRIEF.md` §10 clause by clause with the
evidence for each verdict; read it before claiming anything about completeness.

**The single thing standing between this and a real deployment** is that the web
app does not send access tokens (§9.2). The API verifies them and enforces
ownership; the front end has no sign-in flow. With `CODONLAB_AUTH=jwt` every
application screen returns 401. `DEPLOYMENT.md` is the operator's guide and §6
of it is the honest list of what a deployment still cannot do.

> **The product is called Codon Lab.** It was renamed from CatalystAI on
> 2026-09-01 — the code, the packages, the environment variables, the Postgres
> role and database, the GitHub repository, and the working directory. Exactly
> one string inside the code still reads `catalyst`, deliberately: the hash salt
> in `providers/mock.py`. §8 says why, and why finishing the rename there would
> change every synthetic number the product has produced.

Read these first, in this order. This file is the entry point and deliberately
does **not** duplicate them.

| #   | File              | What it gives you                                                                        | Authority                                                               |
| --- | ----------------- | ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| 1   | `BRIEF.md`        | What the product is, why, all nine screens, the phase plan with exit gates, domain rules | **The owner's specification.** Verbatim. Never edited to match the code. |
| 2   | `DESIGN.md`       | Every colour, type size, space, radius, shadow, easing — and what is banned              | Contract. Update in the same commit as any deviation.                   |
| 3   | `ARCHITECTURE.md` | Module boundaries, the numbering subsystem, the confirmation gate, delegated decisions   | Contract. Same rule.                                                    |
| 4   | `README.md`       | The public face: invariants, the engineering worth reading, measured performance         | Audited claim by claim (`90e6f40`). Keep it that way.                   |
| 5   | This file         | Status, what is unverified, decisions taken in conversation, machine quirks              | Status. Rots. Trust code and tests over it.                             |

If this file contradicts `BRIEF.md`, the brief wins. If it contradicts the code,
the code wins and this file needs fixing.

---

## 1. Orientation

**Codon Lab** is a protein-engineering copilot. A wet-lab scientist types a goal
in plain English — "make this lipase survive 65 °C in 30% DMSO" — and the app
returns a ranked, defensible list of specific point mutations, each traceable to
the model, version and weights hash that produced it. The audience is a bench
protein engineer who is skeptical, busy, and correct: the models that could help
them (ESM, ProteinMPNN, ThermoMPNN, AlphaFold) are Python repos with CUDA
requirements rather than tools, so they either go unused or get run once from a
colleague's notebook and never trusted enough to spend $4,000 of ordering budget
on. The gap being closed is **trust**, not capability.

It is a solo build by the repo owner (`vyom-aggarwal`), executed across multiple
assistant sessions against a fixed nine-phase plan in `BRIEF.md` §9. **All nine
phases are built.** Two things are not: Phase 7's wet-lab handoff exports, which
are blocked on something the data model does not have (§3), and the PDF export
`BRIEF.md` §10 names, which belongs to the same blocked screen. Nothing is
deployed; everything runs locally under Docker on the owner's Windows 11
machine.

**The single most important open item is not a code task.** Nobody has looked at
a screen with a design eye. `BRIEF.md` §4 sets the bar — a structural biologist
opens this next to Benchling and it does not look like the odd one out — and no
gate can judge that. §12 records it as unverifiable rather than met.

---

## 2. Mission & scope

### The goal in the owner's words

From `BRIEF.md` §2, unchanged since the first commit — three things make this
worth building, and everything else is table stakes:

1. **Parse, then confirm — never silently interpret.** Nothing runs from an
   objective the user has not explicitly confirmed.
2. **Every number is traceable** — in two clicks, to model, version, weights
   hash, inputs, run, timestamp. A provenance record as a first-class entity, not
   a log file.
3. **The validation loop** (Phase 8) — measured bench results joined to
   predictions, a persistent per-predictor scorecard. The brief calls it "the
   entire moat."

Cutting across all three: **never fabricate a scientific number.** Unavailable
means `—` with a tooltip, never an imputed value. An unstated field means "not
stated", never a plausible default.

### How scope moved during this session

The mission did not change. Four scope decisions were made by the owner mid-flight:

- **The Phase 5 performance gate was rewritten** from "10,000 rows scroll at
  60fps" to **constant work per scroll update**. Frame rate cannot be measured
  from an agent session, so the owner replaced an unmeasurable gate with the
  structural property it rests on. See §8.
- **The rank-statistic finding was generalised into a standing rule.** The
  assistant reported that a DSSP-correlation test could not discriminate a radii
  set; the owner accepted it and directed that it be applied forward everywhere
  the brief made the same assumption. Now `ARCHITECTURE.md` §13, and it binds
  Phase 8's scorecard design.
- **Four Phase 6 decisions were explicitly delegated** to the assistant with the
  requirement that each be recorded in `ARCHITECTURE.md` §14 with "what would
  change it." Done.
- **The README was pulled forward** from Phase 9. It is written and audited; the
  rest of Phase 9 is untouched.

### Explicitly out of scope

- **Mutant rotamers in the 3D viewer.** `BRIEF.md` §5.6 asks for a wild-type /
  mutant toggle. Dropped — placing a mutant side chain needs a packer this build
  does not have, and redrawing the wild-type residue under a "mutant" label would
  fabricate structural data. Path forward named in `ARCHITECTURE.md` §12.
- **Registering ESM-2 150M or wt-marginal scoring as alternatives.** Both are
  deliberate non-features until Phase 8 makes comparing them meaningful
  (`ARCHITECTURE.md` §14.1, §14.2).
- **Any pre-filter on the design space.** A run scores every substitution at
  every nameable position, then ranks, then applies the budget the user stated.
- **GPU support.** Everything measured here is CPU-only. Not refused, just absent.
- **Deployment, auth, multi-user.** Nothing in the brief asks for them.

---

## 3. Current state

Blunt version: **the backend is genuinely strong and the frontend has never been
looked at by a human being.** That asymmetry is the single most important thing
to know.

### Works end to end, verified

- **Phases 1–8 complete**, each with an exit gate asserted in
  `scripts/verify_gates.py` (**263 checks**, over HTTP, against a live stack).
  Phase 7's wet-lab handoff is the one gap — §9.1.
- **The Phase 7 design set builder works end to end.** Select variants into a set,
  stack them combinatorially, and every stacked design carries its 8 Å pair flags
  and its assumed-additive totals. Verified against the live stack: 6 combinations
  from a 4-variant selection, 12 additive totals recomputed independently by the
  gate, and one pair correctly flagged at 7.5 Å.
- **The 8 Å pair flag is measured, and the convention is the discriminating part.**
  Minimum non-hydrogen atom separation, not Cα–Cα, per `ARCHITECTURE.md` §11. On
  crambin, residues 1 and 46 are 7.9 Å apart by heavy atoms and 11.8 Å by alpha
  carbons — the two conventions **disagree about whether that pair is flagged**.
  Mutating the implementation to Cα–Cα fails three tests; that was run, not assumed.
- **"Unmeasured" survives as its own state.** `Proximity` is a three-valued enum,
  so a target with no structure reports every pair as `unknown` with the reason
  rather than as `beyond`. Asserted in the gate on the structureless target.
- **Primers are refused, and the refusal shipped before the exporter.** Two reasons,
  both stated with a remedy: the run's providers fabricate, and no target carries a
  coding DNA sequence. `GET .../exports/primers.csv` answers 409.
- **A full six-stage run completes with a real predictor.** The 212-residue
  lipase, `succeeded` in 3363s, `is_demo` false, every number `is_mock=false`.
- **ESM-2 650M runs and is correct.** Every score checked against an independent
  masked-marginal recomputation from the same checkpoint, exact to 4 decimal
  places, at three positions including the last residue.
- **ThermoMPNN runs.** 874 of 874 crambin substitutions scored, −1.06 to 3.40
  kcal/mol, sign convention established two independent ways.
- **"Unavailable means unavailable" is proven end to end**, not just unit-tested:
  on that real run the target had no structure, so ThermoMPNN **skipped with its
  stated reason and produced nothing** rather than falling back.
- **Phase 8 ships: results intake, the join, and the scorecard.** Verified on the
  live stack against **real measured data** — 2,172 T50 values for the seeded
  lipase from ProteinGym's `ESTA_BACSU_Nutschel_2020` (Nutschel et al. 2020).
  Real ESM-2 650M scores against those measurements give **Spearman ρ = 0.30**,
  where the synthetic predictor gives −0.06. That is the moat working.
- **The join refuses to guess, and the refusal was measured, not asserted.** The
  ProteinGym file is written in full-length numbering; the seeded project's
  canonical scheme is the mature protein. Uploaded as-is, **100 of 2,172 rows
  join and 1,745 report a wild-type mismatch**. The offset proposal finds −31,
  unanimously across all 2,072 unplaced rows, proposes it without applying it,
  and on acceptance joins 2,172 of 2,172. See §6 for why unanimity, not a
  fraction.
- **`ARCHITECTURE.md` §13 is now demonstrated end to end rather than argued.**
  A predictor offset by a constant 2 kcal/mol scores **ρ = 1.0000 and
  precision@10 = 1.00** and is caught only by the bias term at **−2.00
  kcal/mol** — asserted over HTTP in the gate, and visible on the screen with
  the calibration bins running parallel to the identity line.
- **A landing page and a brand mark ship, at the owner's request** (2026-09-02).
  `/` is now a marketing surface with no application chrome; `Shell` is what
  keeps `BRIEF.md` §4's "no marketing hero **inside** the app" true. It carries a
  live Mol\* viewer of the seeded lipase, served as a static asset so the page
  renders with the whole stack down. Every figure on it is one this build
  measured. `DESIGN.md` §12 and §13 hold the rules; three deviations from the
  brief are named in §6.
- **The web app signs in, and still runs with no identity provider at all.**
  Clerk is wired: `<ClerkProvider>`, middleware, an account control in the rail,
  and a bearer token on **every** API call in both runtimes. Clerk was chosen on
  one criterion the owner set — least work for them: sign up, paste two keys into
  Vercel, three into Render. Nothing in the API is Clerk-specific.

  **The unconfigured path is a supported mode, not an oversight.** With no
  publishable key the app behaves exactly as it did before authentication
  existed, and that is what keeps the gate suite, the Playwright flows and local
  development runnable on a machine with no provider. Every conditional —
  provider, middleware, account control — branches on that one env var, and
  `test/auth.test.ts` covers both sides in both runtimes.

  The awkward part is worth knowing about before touching it: `lib/api.ts` is
  imported by server *and* client components, so the token has to come from two
  different places. The obvious `await import('@clerk/nextjs/server')` inside a
  `typeof window` branch **does not work** — bundlers resolve `import()`
  statically, so the `server-only` SDK lands in the client bundle and Next
  refuses to compile. `lib/auth-server.ts` therefore registers a getter on
  `globalThis` and the root layout imports it for that side effect; nothing a
  client component imports ever names the server SDK.
- **A target can carry the DNA of the construct on the bench, and the wet-lab
  blocker is half cleared.** `Target.coding_sequence` exists (migration
  `0007_coding_sequence`), pasted by the user and never derived. It is stored
  only if `domain/translation` translates it and finds it encodes **exactly**
  the protein already held.

  The refusals are the value, and each names a way a real paste goes wrong: out
  of frame, an internal stop, an ambiguity code, a truncation, the wrong
  construct — reported with the residue number where it first disagrees. The one
  worth knowing about is the **precursor**: a translation that merely *contains*
  the stored protein is refused with its offset rather than trimmed, because
  trimming would shift every primer position by the length of the signal peptide
  and a primer at the wrong position anneals to nothing. Mutation testing
  confirmed a containment check passes every other test in the file.

  `services/exports._coding_sequence` was written years-of-commits ago against
  an attribute that did not exist, "the single place that changes when a coding
  sequence becomes attachable". It needed no change: attaching one removes the
  missing-DNA refusal automatically, and the fabrication refusal survives, which
  the gate now asserts as a transition rather than a state.

  **Primers and the PDF are still not built.** The blocker is gone and the
  chemistry is already decided (`ARCHITECTURE.md` §16.1); what remains is the
  designer itself.
- **Scoring is chunked and resumable, so a large target can finish.**
  `predictor.score()` used to be called once over the whole candidate set with
  nothing written until it returned, so a run killed at the hour-long timeout
  had computed hours of numbers and persisted none — which is why the seeded
  550-residue luciferase could not be run at all. Scoring now runs in chunks of
  whole sequence positions, each committed, and `_recover_partial_scores` lets a
  later run under the same input hash adopt what an earlier attempt finished.
  Verified in the gate by killing a run with half its scores written and
  re-running it.
- **The API is deployable: identity, ownership and admission control.**
  Authentication is delegated to an OIDC provider and verified against its JWKS
  — **no credential is stored by this service**, which is deliberate for a
  product holding unpublished sequence data. A `User` row is created on first
  valid token, keyed on the `sub` claim.

  Ownership hangs off a single `Project.owner_id`; every target, run, score and
  measurement reaches its owner through `project_id`, so there is exactly one
  place it is enforced. It is a **router-level dependency**, not a per-handler
  argument, so a route added in a year cannot forget to opt in —
  `tests/test_ownership.py` walks the live route table and fails if one does.
  Somebody else's resource answers **404, never 403**: the difference confirms
  the row exists and lets an enumerator map the database an id at a time.

  Runs are rationed by a **ceiling on work in flight** (default 3) rather than a
  rate per window, because the scarce resource is the single worker and what
  consumes it is unfinished runs, not request frequency.

  **The API refuses to start** with `CODONLAB_AUTH=disabled` once `CORS_ORIGINS`
  names a non-local origin. That is the accident being prevented — deploy, point
  the web app at it, never set the variable, and serve every project in the
  database to anyone who finds the URL, with no symptom until it matters.
- **Phase 9 ships: keyboard access, `⌘K`, the `?` sheet, an enforced contrast
  audit, three Playwright flows and regenerable screenshots.** `DESIGN.md` §9's
  two deferred devices are built and §9 now says so. The a11y pass audited the
  landing page and eight application screens as served: **every focusable element has an accessible name,
  every screen has exactly one visible `<h1>`, no positive `tabindex`, no
  unlabelled input, no heading-level skip.** 38 decorative icons across 27 files
  gained `aria-hidden`.
- **The contrast audit is now a gate rather than a paragraph, and it caught a
  documented lie.** `DESIGN.md` §1.3 had claimed `--accent` on `--surface` was
  **8.6:1, AAA** since Phase 1. It is **6.70:1, AA**. Every ratio in both themes
  is now recomputed from `tokens.css` on each build by
  `apps/web/test/contrast.test.ts` (35 tests over 30 pairs), which fails if the
  table disagrees. Dark is
  audited too, and one pair — `--accent` on `--accent-sunk`, 4.23:1 — is
  recorded as failing AA but **latent**, since no dark surface in the product
  contains a table.
- **The landing page's primary call to action was dead, and only a real
  browser could see it.** Found during the Phase 9 screenshot run. The hero's
  Mol* viewer ran a perpetual `trackball.animate` spin, redrawing a scene that
  cost **~65 ms a frame** even at 358x358. That saturated the main thread badly
  enough to starve the Next router: clicking **"Open the workbench" did nothing
  at all** — no error, no console message, the URL simply never changed — and
  even assigning `window.location` could not complete. Measured, not inferred:
  under `prefers-reduced-motion: reduce`, where the code already declines to
  start the spin, the same click navigated and a frame cost 14 ms. Fixed by
  dropping the ambient spin and turning off temporal multisampling and
  screen-space occlusion; a frame is now vsync (~16.6 ms) and the model is still
  fully interactive. Guarded by `e2e/landing-cta.spec.ts`. **Nothing else in the
  suite could have caught this** — the gate reads served HTML, which was
  correct, and jsdom has neither WebGL nor a frame budget.
- **Playwright catches a mutation jsdom passes.** §8 has long recorded that
  hiding the Trace control behind a closed `<details>` — a genuine third click —
  passes the jsdom two-clicks test, because jsdom keeps closed `<details>`
  contents in the tree. That mutation was re-run against the Playwright flow and
  **failed**, which is the whole reason the flow exists.
- **A Phase 8 defect was found and fixed during the Phase 9 audit.** The
  scorecard used the mutation code as a pair's identity. On a card pooled across
  targets, codes collide: the live lab-wide card reported **n = 192 while
  carrying 24 distinct codes**, so React dropped the duplicates and the scatter
  drew 24 marks under a caption claiming 192 — and `precision@k` credited one
  variant's rank with another's measurement. `Paired` now carries a `key`
  separate from its display `code`, `PointView` carries `variant_id`, and the
  corrected precision for one seeded card moved from **0.4 to 0.2**. It was
  visible in the browser console as a duplicate-key warning and nowhere else.
- **Gates re-run 2026-09-02 after the landing page landed:** **225 gate checks,
  0 failures** against the live stack; **162 vitest across 10 files**; ruff and
  mypy clean on 69 files; `pnpm typecheck` and `pnpm lint` clean. The host
  pytest suite is **blocked by a machine policy, not by the code** — see §8;
  340 pass with the biotite-dependent modules excluded. Earlier on the same day: **396
  pytest** passing (6 skipped, 1 expected failure — see §8), **162 vitest across
  10 files**, ruff clean, mypy strict clean on **69 source files**,
  `pnpm typecheck` and `pnpm lint` clean, and **225 gate checks with 0 failures**
  against the live stack.

### Half-built

- **The MSA stage is a real stage that always skips.** `_stage_build_msa` in
  `services/runs.py:812` emits a stated reason and no alignment. Consequently the
  conservation column is disabled and the >90%-conservation high-risk flag from
  `BRIEF.md` §7 is unimplemented.
- **`Variant.region` is declared and never populated** (`models/run.py:107`,
  nullable, default `None`). Burial lives in the run's `FEATURES_COMPUTED`
  provenance event instead, because a variant is shared across runs and the
  cutoffs are not. The column needs to be deliberately populated or dropped.
- **The wet-lab handoff is blocked on template DNA, and this is the important
  one.** `BRIEF.md` §5.8 wants site-directed mutagenesis primers per variant.
  A primer anneals to the construct actually on the bench, and `Target` carries
  a one-letter **amino acid** sequence and nothing else — there is no DNA in the
  data model, and neither seeded target has any. Back-translating the protein
  would produce a plausible sequence that is *not* the user's plasmid, so the
  primers would not anneal: a fabrication costing a synthesis order and a week.
  Refused with a stated reason instead (`services/exports`). Clearing it needs a
  `Target.coding_sequence`, a way to attach one, and a check that it translates
  to the protein already stored. **This is a specification gap, not laziness** —
  see §9.1 and `ARCHITECTURE.md` §16.
- **Primer chemistry is decided but unimplemented.** The owner delegated the Tm
  algorithm, conditions, layout and duplex choice on 2026-08-25; all four are
  recorded with their triggers in `ARCHITECTURE.md` §16.1. Nothing is coded, and
  nothing should be until the blocker above clears.
- **Cost estimates read `—` until the project states its prices.** Deliberate
  (`ARCHITECTURE.md` §15): no vendor price is invented. There is no UI yet for
  entering them, so today the budget panel always shows the reason rather than a
  total. The setting is read from `Project.settings.cost_basis`.
- **The real-provider path has never run inside Docker.** The API and worker
  images do not carry the `[models]` extra. Both predictors were exercised on the
  host venv against the same Postgres.

### Broken / known-bad

- **A run abandoned mid-flight stays `RUNNING` forever.** `execute()` only claims
  `PENDING` runs; RQ fails its own job without writing back. Nothing reaps it,
  and `uq_run_active_input` then blocks an identical re-run. Manual recovery in §8.
- **`JOB_TIMEOUT_SECONDS = 3600` is marginal.** The lipase run used 93% of it. A
  550-residue target needs ~142 min at the observed rate and **would be killed** —
  and such a target (luciferase P08659) is already seeded in the database.
- **A stale UI string.** `apps/web/app/runs/[id]/workbench/workbench.tsx:51`
  labels the conservation column `'Requires MSA (Phase 6)'`. Phase 6 shipped
  without an MSA provider, so the label now names the wrong phase.

- **Targets carry variant rows written in numbering schemes they have since
  abandoned, and nothing marks them stale.** Found during Phase 8 by running the
  join against this machine's real database, not by reasoning. Changing a
  target's canonical scheme does not touch the `Variant` rows an earlier scheme
  produced — correctly, since they carry `Score` rows — so one seeded lipase
  target holds **4,446** such rows and another **3,274**. Under the current
  scheme they name different residues: `S108A` is a real row whose substitution
  is called `S77A` today.

  **Phase 8's join is immune to this** — it admits only variants whose
  `(wild, label)` agrees with the current canonical scheme, and reports the
  count it excluded (`ARCHITECTURE.md` §17.2, asserted in the gate). But the
  rows are still there, and **any other surface that resolves a mutation code
  against stored variants has the same exposure**. Open thread 11.

---

## 4. Architecture map

### Stack (verified from manifests)

| Layer     | Choice                                                                                                                 |
| --------- | ---------------------------------------------------------------------------------------------------------------------- |
| Monorepo  | pnpm workspaces — `apps/web`, `apps/api`, `packages/schema`                                                            |
| Web       | Next.js `^15.1.4` App Router, React `^19.0.0`, TypeScript `^5.7.3` strict, Tailwind `^4.0.0`                            |
| Web state | TanStack Query `^5.101.4`, Table `^8.21.3` (**pinned to v8**), Virtual `^3.14.9`, Zustand `^5.0.15`, Mol\* `^5.11.0`   |
| API       | FastAPI `>=0.115.6`, Python 3.12, Pydantic `>=2.10.4`, SQLModel `>=0.0.22`, Alembic `>=1.14.0`, psycopg 3               |
| Queue     | RQ `>=2.1.0` on Redis `>=5.2.1`                                                                                        |
| Science   | biotite `>=1.0`; optional `[models]` extra: torch `>=2.2`, transformers `>=4.40`                                        |
| Contract  | `packages/schema` — Zod `^3.24.1`, 555 lines, the only module both apps depend on                                      |

### Layering rule (`apps/api`)

Dependencies point downward only; a module never imports from a layer above it.

```
routes/      HTTP surface. Request/response models. No business logic.
services/    Orchestration: build a run, aggregate scores, apply constraints.
providers/   Predictor implementations. The ONLY place a model client may be imported.
features/    Derived structural features — geometry, not model output.
sources/     External retrieval: UniProt, RCSB, AlphaFold DB, PDB, FASTA.
parsers/     Free-text goal → structured objective. Claude, with a deterministic fallback.
domain/      Pure logic. No I/O, no database. Numbering, mutation codes, aggregation.
models/      SQLModel tables. No behaviour beyond validators.
```

`workers/` sits beside `routes/` as a **second entry point at the same level** —
which is exactly why the confirmation gate lives in `services/`, not in a route
and never in the UI.

**The one rule that shapes everything: the UI must never import a model client.**
Verified 2026-08-25 — grep for `esm`, `thermompnn`, `proteinmpnn` across
`apps/web` returns nothing. The test for whether it still holds: adding a fourth
stability predictor must touch zero files under `apps/web/components`.

### Data flow

```
Goal text → parsers/ (Claude or rule fallback) → Goal (unconfirmed)
  → user confirms in the composer → services/goals.require_confirmed
  → POST /runs → services/runs.create (idempotent on content address)
  → RQ enqueue → workers/ → services/runs.execute
      stage 1 retrieve structure
      stage 2 build MSA          (always skips today)
      stage 3 score × N predictors  → ScoreValue → Score (+ ModelVersion, + Run)
      stage 4 aggregate          (ranks only, never raw scores)
      stage 5 filter by constraints
      stage 6 rank
  → GET /runs/{id}/ranking → workbench
```

### Files that matter most

| Path                                              | Role                                     | Why it matters                                                                                     |
| ------------------------------------------------- | ---------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `apps/api/codonlab/providers/base.py`             | The `Predictor` Protocol                 | The single seam. `ScoreValue` carries no run/model — structurally incapable of an untraceable number |
| `apps/api/codonlab/services/runs.py`              | The six-stage pipeline (~1500 lines)     | Every run flows through it; the only place a `Score` is created                                      |
| `apps/api/codonlab/services/goals.py:162`         | `require_confirmed`                      | Invariant 1. In the service layer because workers are a second caller                                |
| `apps/api/codonlab/models/run.py:118`             | `Score` table                            | Invariant 2. `model_version_id` and `run_id` both `nullable=False`; no migration may relax it        |
| `apps/api/codonlab/providers/mock.py`             | The two synthetic predictors             | The **only** module permitted to invent a number. `is_mock` drives the whole demo apparatus          |
| `apps/api/codonlab/providers/esm.py`              | ESM-2 650M, masked marginals             | Holds `_residue_token_start` — the off-by-one that shipped and was caught. Touch with care           |
| `apps/api/codonlab/providers/thermompnn.py`       | ThermoMPNN ΔΔG                           | Vendored at a pinned SHA; hashes both its own and ProteinMPNN's weights                              |
| `apps/api/codonlab/domain/numbering.py`           | Scheme reconciliation                    | `reconcile()` returns `NEEDS_ALIGNMENT` and stops. Never infers silently                             |
| `apps/api/codonlab/domain/schemes.py`             | sequence index ↔ author numbering        | Pure functions so numbering is testable headlessly. `positions_by_label` refuses duplicate labels    |
| `apps/api/codonlab/domain/aggregate.py`           | Rank-based consensus                     | Never averages raw scores. Null (not zero) disagreement for a single opinion                         |
| `apps/api/codonlab/domain/hashing.py`             | `content_hash`                           | Content addressing and run idempotency both rest on it                                               |
| `apps/api/codonlab/features/structure.py`         | SASA / RSA / burial via biotite          | Every pinned parameter and its citation live here                                                    |
| `apps/api/codonlab/domain/constants/max_asa.py`   | Tien et al. 2013 theoretical MaxASA      | The reference table, with DOI. Swapping it moves 27 of 1BTL's 263 residues                           |
| `apps/web/app/runs/[id]/workbench/workbench.tsx`  | The main screen                          | Assembles filter rail, table, inspector. Holds the stale conservation label at line 51               |
| `apps/web/components/workbench/variant-table.tsx` | Virtualised table                        | `ROW_HEIGHT = 30` duplicated into JS out of necessity; `workbench.test.ts` guards the duplication    |
| `apps/web/lib/rationale.ts`                       | "Why this was proposed"                  | A **pure function** of the row. Never a language model. Each clause names the field it rests on      |
| `apps/web/test/tokens.test.ts`                    | Design-system enforcement                | Fails the build on any off-system colour, size, radius, shadow, gradient, emoji                      |
| `scripts/verify_gates.py`                         | 263 checks over HTTP                     | The real gate. Self-seeding and idempotent. **Add a section per phase you complete**                 |
| `apps/api/codonlab/domain/epistasis.py`           | Stacking, the 8 A pair flag, additivity  | `Proximity` is three-valued so "not measured" cannot render as "far apart". Totals carry their assumption |
| `apps/api/codonlab/services/exports.py`           | The primer refusal                       | Built before the exporter it constrains. The only entry point, so nothing routes around it           |
| `apps/api/codonlab/domain/joining.py`             | Matching bench rows to variants          | No similarity threshold anywhere. The offset proposal is unanimous-and-unique, so there is no fraction to set wrong |
| `apps/api/codonlab/domain/scorecard.py`           | Spearman, precision@k, MAE, bias         | `build()` is the only entry point and always carries the error terms or the reason they are absent. `accumulate()` refuses the averaging shortcut by name |
| `apps/api/codonlab/services/measurements.py`      | Intake, the join, the scorecard          | Holds `_known_variants`, which excludes variants written in a superseded numbering scheme. That check is load-bearing — §3 |
| `apps/api/codonlab/data/proteingym/`              | 2,172 real measured T50 values           | Vendored with its SHA-256, its citation, and what it can and cannot demonstrate. Read by `seed.py`, never fetched at boot |
| `apps/web/components/scorecard/scorecard-card.tsx`| Rank, error and bias in one row          | The shape is a contract, not a layout preference. `scorecard.test.tsx` asserts the adjacency from the DOM |
| `apps/web/components/brand/codon-mark.tsx`        | The mark                                 | Five rungs, stroke 1.5, `currentColor` only. `landing.test.tsx` asserts the count — twelve candidates were compared, `DESIGN.md` §12 lists what the rejects were misread as |
| `apps/web/components/landing/landing.tsx`         | The landing page                         | Outside the app chrome. Every figure on it is one this build measured, including the unflattering ones |
| `apps/web/components/landing/hero-structure.tsx`  | The live 3D structure                    | Holds two Mol\* traps that cost real time: `handleResize` is on the plugin, not `canvas3d`, and `Color.fromHexString` is not the one that reads `#rrggbb` |
| `apps/web/components/shell.tsx`                   | Chrome on, chrome off                    | The single reason `BRIEF.md` §4's "no marketing hero inside the app" is still true |

---

## 5. Environment & runbook

Machine is **Windows 11 Home, PowerShell 5.1**. Git Bash is also available and is
usually the better shell for anything with heredocs or POSIX quoting.

### From a clean clone

```powershell
# 1. Node toolchain
corepack enable --install-directory "$env:APPDATA\npm"
pnpm install

# 2. Environment
Copy-Item .env.example .env      # then fill in values

# 3. Bring the stack up (runs migrations and seeds automatically)
docker compose up -d
```

`docker compose up` runs, in the `api` container:
`alembic upgrade head && python -m codonlab.seed && uvicorn codonlab.main:app --host 0.0.0.0 --port 8000 --reload`

Then open <http://localhost:3000>.

### Services and ports

| Service  | Image / command                    | Host port                | Notes                                    |
| -------- | ---------------------------------- | ------------------------ | ---------------------------------------- |
| postgres | `postgres:17-alpine`               | **5434** (`POSTGRES_PORT`) | 5432 *and* 5433 are taken by other projects on this machine — see §8 |
| redis    | `redis:7-alpine`                   | 6379 (`REDIS_PORT`)      |                                          |
| api      | FastAPI / uvicorn                  | 8000                     | Migrates + seeds on boot                 |
| worker   | `python -m codonlab.workers.worker`| —                        | Without it, runs stay queued forever     |
| web      | `pnpm --filter @codonlab/web dev`  | 3000                     |                                          |

### Environment variable **names** (values never recorded here)

From `.env.example`: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`,
`POSTGRES_PORT`, `DATABASE_URL`, `REDIS_URL`, `CORS_ORIGINS`,
`CODONLAB_PROVIDERS`, `ANTHROPIC_API_KEY`, `CODONLAB_PARSER_MODEL`,
`NEXT_PUBLIC_API_URL`.

Set in `docker-compose.yml` but **absent from `.env.example`** — worth knowing:
`API_INTERNAL_URL` (`http://api:8000`, required by web server components) and
`REDIS_PORT`. Opt-in flags used only by tests and gates: `CODONLAB_TEST_REAL_MODELS=1`,
`CODONLAB_GATE_REAL_MODELS=1`.

`CODONLAB_PROVIDERS` defaults to `mock`. `real` switches on ESM-2 650M and
ThermoMPNN and requires the optional extra.

### Running the real models

```powershell
cd apps\api
pip install -e ".[models]"       # torch + transformers, several GB
# then set CODONLAB_PROVIDERS=real
```

### Tests and gates

```powershell
pnpm typecheck; pnpm lint; pnpm test                   # 221 vitest across 13 files
cd apps\api; .venv\Scripts\python -m pytest -q        # BLOCKED on this host, see below
cd apps\api; .venv\Scripts\python -m ruff check .     # clean
cd apps\api; .venv\Scripts\python -m mypy codonlab    # strict, clean, 69 files
python scripts\verify_gates.py                        # 263 checks, needs the live stack
pnpm --filter @codonlab/web e2e                       # 6 Playwright flows, needs the stack
```

**Deploying.** `render.yaml` provisions the API, worker, Postgres and Redis;
Vercel hosts `apps/web`. `DEPLOYMENT.md` is the operator's guide — read §6
before showing a deployment to anybody, because it is the honest list of what
one still cannot do. The two checks worth memorising:

```bash
curl -i https://<api>/projects   # 401 when CODONLAB_AUTH=jwt. A 200 means auth is OFF.
curl https://<api>/health        # 200
```

**Run pytest inside the api container.** The host suite cannot collect four
modules — a machine policy blocks biotite's compiled extensions (§8). The
container carries its own biotite and is unaffected:

```powershell
docker compose exec -T api sh -c "pip install -q pytest && cd /app && python -m pytest -q"
```

That returns **399 passed, 6 skipped, 1 known failure** (the ESM/torch one, open
thread 12). The image does not ship `[dev]`, so pytest is installed into the
running container; it is lost on rebuild, which is fine for a verification step.

**Run pytest inside the api container.** The host `.venv` cannot collect four
test modules: a machine policy blocks biotite's compiled extensions (section 8).
The container carries its own biotite and is unaffected.

```powershell
docker compose exec -T api sh -c "pip install -q pytest && cd /app && python -m pytest -q"
```

That returns **399 passed, 6 skipped, 1 known failure** (the ESM/torch one,
open thread 12). The image does not install the `[dev]` extra, so pytest is
installed into the running container and is lost on rebuild. That is fine for a
verification step, and it is the only way the suite runs on this machine today.

**Invoke the Python tools as `python -m <tool>`, not through
`.venv\Scripts\<tool>.exe`.** A Windows Application Control policy on this
machine blocks the pip-generated launcher executables — `pytest.exe`, `mypy.exe`
and `alembic.exe` all fail with *"An Application Control policy has blocked this
file"*. The venv's own `python.exe` runs fine, so `python -m` is the working
path. This is a machine-level setting and not a broken install: the launchers
carry the correct absolute path (checked 2026-09-01), and it is the same policy
that blocked torch's DLLs in §8.

Python tests are **hermetic** — no database, no network, no Redis. Anything that
genuinely crosses Postgres is asserted in `verify_gates.py` instead, because that
is the boundary a future caller actually crosses. **Keep it that way.**

A full `verify_gates.py` pass fetches from UniProt, RCSB and AlphaFold DB and
executes real design runs, so it takes several minutes. It seeds its own projects
and targets and is safe to re-run.

### Windows-specific gotchas

- **PowerShell 5.1 corrupts here-strings containing double quotes** when passing
  them to native commands. Write long commit messages to a file and use
  `git commit -F <file>`, or use the Bash tool's heredoc.
- **The Windows console is cp1252** and cannot encode `→` or `°`.
  `verify_gates.py` reconfigures its own streams to UTF-8; anything else printing
  those characters needs `PYTHONIOENCODING=utf-8`.
- **`pnpm` is a corepack shim** in `%APPDATA%\npm`. Reinstall command above.
- **Docker Desktop** lives under `%LOCALAPPDATA%\Programs\DockerDesktop`. An
  earlier session recorded that it will **not** start from a non-interactive
  process; that is wrong, or no longer true. On 2026-08-25 launching
  `Docker Desktop.exe` with `Start-Process` from an agent session brought the
  daemon up (29.6.2) in about 90 seconds. Poll `docker info` rather than
  assuming it is ready.
- **Adding a web dependency needs the image rebuilt, not just restarted.**
  `node_modules` lives in anonymous volumes that shadow the bind mount, so
  installing on the host is invisible to the container:
  `docker compose up -d --build --renew-anon-volumes web`
- **`docker compose rm -f web` does not drop those anonymous volumes.** Use
  `docker compose rm -fsv web` (note the `v`), then `up -d`.
- **The agent's browser pane runs hidden, so the page never composites.**
  `requestAnimationFrame` does not fire — anything driven by animation frames
  (virtualised scrolling, transitions, screenshots) cannot be observed from an
  agent session. Plain DOM reads, `fetch`, timers and MutationObserver work.

---

## 6. Decisions & rationale

The hardest thing to recover once the conversation is gone. Decisions that live
in a document are cross-referenced rather than restated.

### Delegated to the assistant by the owner, recorded in `ARCHITECTURE.md` §14

Each carries "what would change it", because a delegated decision with no stated
trigger becomes folklore.

| Decision                                        | Rationale in one line                                                                                | What would change it                              |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| **ESM-2 650M**, not 150M (§14.1)                | The cost does not recur — the cache is keyed per (target, checkpoint, candidate set), not per run    | A GPU, or Phase 8 giving a reason to compare       |
| **`JOB_TIMEOUT_SECONDS` 3600**, not 900 (§14.1) | The first pass on a large target genuinely takes half an hour                                        | Making the scoring stage resumable instead         |
| **Masked-marginal scoring** (§14.2)             | `BRIEF.md` §6 names it. wt-marginal is ~200× cheaper but a *different*, weaker scheme                | The brief changing. Not a performance argument     |
| **ThermoMPNN vendored at a pinned SHA** (§14.3) | Not on PyPI; a moving `main` would silently change what a stored `weights_hash` refers to           | An upstream PyPI release — a new SHA, new ModelVersion |
| **Objectives stated per predictor** (§14.4)     | Inheriting `mock_fitness`'s seven would have a stability model answering a specificity question      | Evidence about a specific model's coverage         |
| **Primer chemistry, four decisions** (§16.1)    | Delegated 2026-08-25. NN Tm (SantaLucia & Hicks 2004) via Biopython, Owczarzy salt corrections, Liu & Naismith layout, both duplexes reported | A lab whose kit calibrates its acceptance rule on the empirical scale |
| **The 8 A pair distance convention** (§15)      | The brief fixes 8 A but not how it is measured; reused §11's already-settled minimum heavy-atom rule rather than inventing a second one | Owner preferring CA-CA, which flips real pairs |
| **The join is exact, never fuzzy** (§17.1)      | `A123V` and `A123L` are edit-distance 1 and are different experiments, so any similarity cutoff eventually misattributes a real measurement | An owner instruction naming a similarity function and its cutoffs. No amount of usage evidence, since a permissive join fails silently |
| **An offset is unanimous and unique, or absent** (§17.1) | A numbering shift is a systematic transform, so "explains most rows" is evidence it is *not* one. This is what removed the threshold the owner was asked about — unanimity is not a tuneable number | Owner stating a fraction, which would then be implemented as stated |
| **Absolute error needs matching units *and* matching sign conventions** (§17.3) | A ddG in kcal/mol minus a T50 in °C is meaningless; opposed conventions make the error an artefact of notation. Neither is silently converted or negated | Nothing. Both are refusals to fabricate, not tunings |
| **Replicates are averaged per variant before pairing** (§17.1) | A variant measured eight times would otherwise outvote the plate in the MAE and appear eight times in a top-k | An owner preferring the median, which is a one-line change and a stated choice either way |
| **A scorecard is keyed on a model version** (§17.4) | Two weight hashes are two predictors in a provenance trail; a card pooling them is a card about neither | Nothing foreseeable |

ESM-2 is offered for thermostability, activity, expression, solubility and
binding affinity — and **deliberately refused** specificity and solvent
tolerance. ThermoMPNN is thermostability only. Both are offered for
thermostability **on purpose**: their disagreement is the signal `BRIEF.md` §6 is
built around.

### Scientific decisions settled by the owner (Phase 5), encoded in `ARCHITECTURE.md` §11

- RSA = ASA / MaxASA using **Tien et al. 2013 *theoretical*** (doi:10.1371/journal.pone.0080635).
- Shrake–Rupley via **biotite**, probe 1.4 Å, 1000 points, **ProtOr radii** (Tsai
  et al. 1999), heavy atoms only. The owner's instruction was explicit: *do not
  write a SASA implementation.*
- Region cutoffs: core RSA < 0.25, boundary 0.25–0.40, surface > 0.40 — as a
  **project setting** with those defaults, not a constant, because it is a
  scientific decision.
- Distance to active site is the **minimum non-hydrogen atom separation** to the
  residues the user annotated, not Cα–Cα. An arginine side chain reaches ~7 Å
  past its own Cα. Nothing is inferred — no pocket detection, no database lookup.
- No conservation column until an MSA provider exists.

### Deviations from the brief, taken on the owner's instruction (2026-09-02)

The owner asked for a landing page and a real brand mark. `BRIEF.md` §5 lists
nine screens and a landing page is not among them, so three things here go
beyond the specification. None was a silent edit; the brief is unchanged and
each deviation is recorded where the rule it bends lives.

| Deviation | Why it is not a violation | Where it is written down |
| --- | --- | --- |
| A marketing surface exists | §4 bans a hero **inside the app**. `Shell` renders `/` with no rail and no demo bar, so the ban holds everywhere the application chrome is | `DESIGN.md` §13 |
| Two type sizes above 24px | §4's scale governs the nine application screens, and still does — a landing page is a surface it was never written for. `tokens.test.ts` fails the build if `text-32` or `text-44` appears outside `components/landing/` | `DESIGN.md` §1.5 |
| Two colour literals in `app/icon.svg` and `app/apple-icon.svg` | A favicon is a standalone document rendered with no stylesheet, so it cannot reference a custom property. Both carry `--accent`'s value and both need updating by hand if it moves | `DESIGN.md` §12 |

The owner asked twice for more visual impact and then for "very clean" with 3D.
What landed is the clean layout with a live structure rather than a dark or
heavily styled page; if that reading was wrong, the page is one file
(`components/landing/landing.tsx`) and the mark is another.

### Standing rules that bind future phases

- **No validation claim rests on a rank or correlation statistic alone**
  (`ARCHITECTURE.md` §13). Origin: a DSSP-agreement test was supposed to validate
  the radii set and **cannot** — swapping ProtOr for a uniform radius *raised*
  correlation to r = 0.998 while moving 8 of 1BTL's 263 residues across a region
  boundary. Correlation is invariant to monotonic transforms, and a systematic
  offset, a scale error and a miscalibration are all monotonic. **Binds Phase 8:**
  the scorecard must report a rank metric **and** an error metric (MAE, kcal/mol)
  **and** a bias term (mean signed error), with bias visually adjacent to rank.
- **Agreement is never called confidence.** Predictors trained on overlapping data
  share their biases; agreeing means they are alike, not that either is right.
- **Consensus is a mean of normalised ranks, not of scores**, and is **not
  stored** — it is not a model output and would need a fabricated `ModelVersion`
  to become a `Score`. Recomputed from stored scores on every read.
- **A run scores the entire single-point space and narrows afterwards.** Any
  pre-filter would be a scientific choice made without asking.
- **Starting a run is idempotent on its content address.** Enforced by a partial
  unique index (migration `0003_run_idempotency.py`), not only a service check, so
  a concurrent pair cannot both insert. Failed and cancelled runs leave the index.
- **`weights_hash` is a SHA-256 of the bytes actually loaded.** Never a
  placeholder — a made-up hash is indistinguishable from a real one in a
  provenance trail, which turns the whole claim into a lie.

### Earlier decisions, still standing

- **Tooling and dependency choices are delegated to the assistant** — pick them,
  state the reason in one line, do not open a question. **Scientific defaults are
  the opposite: always escalate.**
- **Goal parsing is Claude with a deterministic fallback**, not a form and not
  rules-only. The fallback is the offline path and the test path, not a degraded
  mode.
- **Parser model defaults to `claude-opus-5`** (`CODONLAB_PARSER_MODEL`). An
  earlier Sonnet 5 suggestion was withdrawn — downgrading for cost is the owner's
  call, not the assistant's.
- **UniProt constraint annotations are suggestions, never auto-applied**, and
  every position is translated into the canonical scheme first.
- **Alignment uses identity scoring, not BLOSUM62.** Assistant decision, flagged
  for review, **not yet re-confirmed**. `ARCHITECTURE.md` §9. Reversible.
- **Mutant rotamers dropped**, with a named path forward (`ARCHITECTURE.md` §12):
  a backbone-dependent rotamer library (Dunbrack), most probable rotamer, labelled
  as such, never energy-minimised. Filed as a decision, **not** as "reversible" —
  the owner pushed back on that framing specifically.
- **Proposed but never agreed:** doing Phase 8 before Phase 6. Moot now.

---

## 7. Conventions & working preferences

### The working agreement, as the owner has stated it repeatedly

- Build in the numbered phases from `BRIEF.md` §9. Before changing anything,
  **verify the existing gates** — if they fail, stop and report rather than
  proceeding.
- **Ask about open scientific decisions before writing code, and wait for an
  answer.** Do not begin a phase whose science is unsettled.
- After each phase: extend `scripts/verify_gates.py` with a section asserting that
  phase's exit gate; update this file in the **same commit**; run every gate; fix
  everything red; commit with a real message.
- **Stop and check in at the end of each phase. Do not silently continue.**
- Report plainly what was verified, what could not be verified, and what was left
  out.
- A smaller number of finished screens beats a full skeleton.
- Ask before adding a dependency outside `BRIEF.md` §3.

### Corrections the owner made during this session — these are the real signal

1. **"Verify that literally — count the clicks — rather than asserting the drawer
   exists."** On the two-clicks gate. Asserting that a component exists is not
   verifying a gate about user actions. The result used `event.isTrusted` in a
   real browser.
2. **"Never invent a threshold, cutoff, or sign convention."** Stated verbatim in
   two separate turns.
3. **"Measure the 10,000-row scroll — do not assert it. If you cannot measure it,
   say so rather than claiming it."** And afterwards: *"Frame rate becomes a
   manual check I run in a real browser. Don't claim it in code comments or docs
   until I do."*
4. **"Don't file it as 'reversible'; file it as a decision in `ARCHITECTURE.md`
   with the path forward named."** On the rotamer toggle. A deferred feature is a
   decision, not an open question.
5. **"`DESIGN.md` currently describes a palette that doesn't exist, which breaks
   the working agreement about docs matching the build."** Docs and code move in
   the same commit — this is enforced, not aspirational.
6. **"Your correction is accepted, and it generalises further than the test…
   apply that finding forward, because the brief has the same bug twice more."**
   A finding is not done when the one test is fixed.
7. **"You have not run it. Do not report `StabilityPredictor` as working until you
   have."** Working means executed, not implemented.
8. On mixed real/mock output: **"the demo flag is per-provider, not global, and
   mixed real/mock results must still badge every mock number."**

### Code and commit conventions

- **Commit messages run 40+ lines on purpose.** They carry the reasoning a
  summarised conversation loses. Lead with what would be most expensive to
  rediscover — an off-by-one that shipped, a claim that did not survive audit.
  Keep writing them that way. Use `git commit -F` on Windows.
- Comments explain **why**, and name the citation or the decision they rest on.
  Match the surrounding density — this codebase comments heavily by design.
- Tests are written to **discriminate**. Where a test guards something expensive,
  mutation-test it and record the result.
- Design system is enforced mechanically: add a token to `DESIGN.md`, never reach
  for an arbitrary value.
- No emoji anywhere in the codebase — `tokens.test.ts` fails the build on one.

---

## 8. Dead ends & known traps

### Real bugs that shipped and were caught — the expensive ones

- **ESM-2 off-by-one (the most serious).** `_token_offset` returned the *index* of
  the first residue and `score()` used it as an *additive offset*, so every
  substitution was scored against its neighbour. The values were plausible and
  correctly ordered. Caught only by recomputing masked marginals independently
  from the same checkpoint: `A10W` came out −1.53 where the model actually says
  −4.59. The fix is structural — the alignment is established by comparing tokens
  against the sequence at several positions across its length, the helper returns
  an index and is *named* one, and `score()` re-checks the residue it is about to
  mask. `tests/test_esm.py` would fail on a return to the old formula.
- **Mutation codes written in sequence index rather than the canonical scheme**
  (`S108A` where the confirmed scheme says `S77A`). The single most expensive
  error class in this application. Fixed by threading canonical labels through
  enumeration.
- **A duplicate-label dict comprehension** in the label→position map silently kept
  the *last* duplicate. `domain/schemes.py:positions_by_label` now refuses
  duplicates.
- **The transport retry could re-POST a run-start and create two runs.** Fixed
  with a service-level dedupe, migration 0003's partial unique index, `IntegrityError`
  recovery, and 200-vs-201 status. `verify_gates.call()` now only retries GET
  unless `retry_safe=True`.
- **The two mock predictors were anti-correlated by construction**, so every
  variant carried maximal disagreement. Fixed with a shared latent read in each
  metric's own direction (`providers/mock.py`, `_SHARED_WEIGHT`).

### The escaping trap, stated as a rule because it keeps recurring

Writing Python **through a shell heredoc** to patch a file has now silently
corrupted a file four times in this project: twice in `HANDOFF.md`, twice in
`scripts/verify_gates.py`. Two distinct failures, both silent:

- `` in a path like `appspi` inside a non-raw Python string becomes a **BEL
  character**. The replacement then never matches and the edit is skipped with
  no error.
- `"\n"` inside a heredoc inside a patch script resolves one level too far and
  becomes a **real newline** inside a string literal, producing a syntax error
  in the file being written — which is only noticed if something parses it.

**The rule: build patch scripts with the Write tool, not a heredoc.** A file
written directly has exactly one level of escaping, and raw strings behave.
Where a heredoc is unavoidable, use `r"..."` for anything containing a
backslash, and `chr(10)` rather than an escape for a newline. Always `ast.parse`
the result before trusting it — every one of these four was caught by parsing,
and none by reading.

### Traps in the tests themselves

- **`app.routes` does not contain the application's routes.** This FastAPI
  version wraps each `include_router` in a private `_IncludedRouter` whose real
  routes hang off `original_router`, rather than flattening them. A test that
  iterates `app.routes` looking for `APIRoute` finds four documentation
  endpoints and **no path parameters at all** — so every set-difference
  assertion over them passes vacuously.

  This was not hypothetical: `test_ownership.py` shipped that way for ten
  minutes and stayed green while `target_id`'s resolver was deleted out from
  under it. Caught by mutation, not by reading. `_api_routes()` now recurses
  through `original_router`, and `test_the_route_walk_actually_finds_the_
  application` asserts the walk finds more than 40 routes — a guard on the
  guard, because an empty set difference is always true.
- **A behavioural test can pass for an incidental reason.** The JWT
  key-confusion attack (sign with HS256 using the provider's *public* key as the
  shared secret) is refused even when `HS256` is in the algorithm allow-list —
  because a real JWKS returns an RSA key object and the crypto layer will not
  use it as an HMAC secret. That refusal depends on what key type a provider
  happens to publish and on a PyJWT implementation detail; it is not the
  guarantee. `auth.ALGORITHMS` is therefore asserted **directly**, and widening
  it turns exactly one test red.
- **Mutation testing found a real 500.** Widening the allow-list surfaced a
  `TypeError` escaping `auth.verify` from below PyJWT's exception hierarchy —
  which in production is a stack trace and an error-rate spike in response to a
  forged token, instead of a 401. `verify` now catches broadly and refuses.


- **A presence assertion is not a visibility assertion.** The first two-clicks
  test checked presence; a mutation hiding the Trace control behind a closed
  `<details>` — a genuine third click — passed it, because jsdom keeps closed
  `<details>` contents in the tree. If you touch the inspector or the drawer,
  **re-run the mutation check** rather than trusting a green tick.
- **The word doing the work in that gate is "any".** A mutation pointing every
  Trace control at the *first* score passed all six tests that existed. There is
  now a two-predictor block that catches it.
- **A correlation test cannot discriminate a radii set.** See §6. This is the
  general form and it has bitten once already.

- **A test whose fixture differs in two ways pins neither.** Found on Phase 8's
  commensurability gate by mutating it. `test_a_ddg_and_a_temperature_are_not_commensurable`
  uses a ΔΔG and a T50, which differ in **unit and in direction** — so deleting
  the unit check entirely left the test passing, via the sign check, with an
  assertion message that looked plausible. There is now a second test using an
  ESM log-odds ratio and a T50, which are both higher-is-better and still not
  subtractable, so the unit gate is pinned on its own. Look for this shape
  wherever a fixture is "obviously" different.

- **A `\b` after a CSS unit does not close the check it looks like it closes.**
  `tokens.test.ts` rejected arbitrary Tailwind values containing raw lengths with
  `/\d+(\.\d+)?(px|rem|em|vh|vw)\b/`. `_` is a word character and Tailwind uses
  it as the space separator, so `grid-cols-[4rem_1fr]` never matched and had
  been passing for as long as the check existed — while `grid-cols-[1fr_20rem]`
  was caught, because `]` *is* a boundary. Now a negative lookahead. Found by
  asking why one violation was reported and an identical one on the next line
  was not.

### Phase 8 mutation checks, and what they caught

The working agreement asks for a mutation test wherever a test guards something
expensive, and for the result to be recorded. All were run on 2026-09-01 and all
were caught.

| Mutation                                                             | Result |
| -------------------------------------------------------------------- | ------ |
| `domain/joining`: unanimity → "≥60% of rows agree"                    | Caught by `test_a_shift_that_explains_most_rows_is_not_proposed`. The failure output is the argument for the rule: the 60% version proposed −31 and would have silently reattributed `H99Y` to `H68Y`, a variant nobody measured |
| `domain/scorecard`: unit gate deleted                                 | Caught, but at first by the *sign* assertion — see the trap above. Now caught by both |
| `domain/scorecard`: sign-convention gate deleted                      | Caught by two tests |
| `domain/scorecard`: `spearman` stops orienting by the measured series | Caught by two tests |
| `scorecard-card.tsx`: bias figure moved out of the rank `<dl>`        | Caught by four tests. This is the `ARCHITECTURE.md` §13 contract; closing the list early fails the build |

### Environment dead ends

- **Frame rate cannot be measured from an agent session, at all.** The browser
  pane runs hidden, so nothing composites and `requestAnimationFrame` never fires
  — which also means the virtualiser never recalculates, so a scroll cannot even
  be simulated. Do not attempt it again. It needs a human with a real browser.
- **Mol\* cannot be verified from the DOM.** It reports `ready` and the focus call
  is wrapped so a failure cannot take the panel down, but everything it draws goes
  to a canvas. Nothing about the *image* is verified.
- **`verify_gates.py` crashed on a passing check** because cp1252 could not encode
  `→`. It now reconfigures its own stdout/stderr to UTF-8 with `errors="replace"`.
- **RQ job ids may not contain `:`.** They are `run-{uuid}`.
- **TanStack Table v9 was installed and had to be pinned back to v8.**
- **Three more Mol\* traps, all silent** (found building the landing page's 3D
  viewer, 2026-09-02). Each one produces a wrong picture and no error:
  - **`handleResize` is on the `PluginContext`, not on `canvas3d`.**
    `plugin.canvas3d.handleResize?.()` is a no-op — the property is simply
    undefined — and the symptom is a scene rendered into a 114x114 corner of a
    correctly sized 537x537 buffer. Mol\* does subscribe to its own resize
    input, but that is driven by *window* resize events, so a container that
    grows during layout never triggers it. Call `plugin.handleResize()`, and
    attach a `ResizeObserver` to the container.
  - **`Color.fromHexString` is `parseInt(s)` and wants `0xrrggbb`.** Handed a CSS
    `#rrggbb` it returns `NaN`, which renders as black rather than throwing.
    `Color.fromHexStyle` is the one that strips the `#`.
  - **The trackball spin animation requires `axis`.** `{ name: 'spin', params:
    { speed } }` throws `Cannot read properties of undefined (reading '0')` on
    the first animation tick and kills the whole loop, because `spin()` reads
    `params.axis[0]` directly. Pass `axis: [0, -1, 0]`, the default.

  A fourth thing was tried and abandoned: hand-building the state hierarchy with
  `createModel` / `createStructure` / `tryCreateComponentFromExpression`, to drop
  the signal peptide from the picture. It reported success and rendered nothing.
  The stock `applyPreset('default')` is what ships, with the theme patched
  afterwards — a correct structure beats a cleverer empty one.

- **Mol\*'s entry point is `initViewerAsync`, not `initViewer`**, and focusing a
  residue needs **author** numbering (`auth_seq_id`), not the sequence index.
- **ThermoMPNN's config object needs a `__contains__` shim** (`'lightattn' in cfg.model`),
  and its `forward` returns `(list_of_dicts, None)`, not tensors. Loading without
  pytorch-lightning means stripping the `model.` prefix Lightning puts on keys.
- **`P0CG48` is Polyubiquitin-C (685 aa), not the 76 aa ubiquitin monomer.**
  Reconciliation correctly refused it with nine candidate offsets. Not a bug.

### The Application Control policy is spreading (2026-09-02)

The machine-level Windows Application Control policy that HANDOFF has recorded
since 2026-09-01 — it blocks torch's DLLs and every pip-generated `.exe`
launcher in the venv — **now also blocks biotite's compiled extensions.**

    ImportError: DLL load failed while importing localungapped:
    An Application Control policy has blocked this file.

It tightened *during* a session: `python -m pytest` returned 396 passed earlier
on 2026-09-02 and, with no Python file changed in between, later returned four
collection errors. The affected modules are exactly those that reach
`codonlab.features.structure`: `test_meta`, `test_pair_distances`,
`test_run_pipeline`, `test_sasa`, plus one case in `test_schemes`.

**What this does and does not mean.**

- The host test suite cannot currently be run in full. Excluding those modules,
  **340 pass, 6 skip**, and the only other failure is the long-documented torch
  one. Nothing here is a code defect.
- **The Docker containers are unaffected** — they carry their own Python and
  their own biotite. `verify_gates.py` was **225/225** immediately after the
  host suite broke. When the host and the containers disagree, the containers
  are the ones that reflect the code.
- Do not "fix" this by reinstalling biotite or rebuilding the venv. Both were
  tried against the same policy for torch and neither helps; it is a machine
  setting. Run the affected checks through the container, or get the policy
  changed.

### Machine facts discovered during the rename (2026-09-01)

- **Renaming the project folder needs the old compose project's containers
  removed first.** `docker-compose.yml` pins `name: codon-lab`, so
  `docker compose down` does not touch containers created under the previous
  project name — five `catalyst-ai-*` containers survived it, and their bind
  mounts held the folder against a rename (`Device or resource busy`).
  `docker rm` them by name, **without** `-v`, so `catalyst-ai_postgres-data`
  survives as the pre-rename backup. An agent session also pins its own
  working directory, so it has to move out before the folder can be renamed.

- **Host port 5433 is no longer free.** Another project's container,
  `rihs-postgres`, holds it. This project moved to **5434** in the local `.env`.
  Nothing inside the compose network is affected — services still reach Postgres
  on 5432 by name — so only host tooling sees the change. Do not stop the other
  project's container to reclaim the port.
- **The `[models]` extra is NOT installed, so `import torch` fails.** The venv was
  rebuilt from scratch on 2026-09-01 (see the restore note below) with `[dev]`
  only. Reinstall it with `pip install -e "apps/api[dev,models]"` — several GB —
  when a real predictor is actually needed.

  Before that rebuild torch *was* installed and failed differently: a Windows
  Application Control policy blocked its DLLs with
  `OSError: [WinError 4551] ... Error loading "...torch/lib/shm.dll"`, on files
  unmodified since 2026-08-23. That policy is a machine-level setting and will
  bite again the moment `[models]` goes back in, so reinstalling torch is
  necessary but **not sufficient** to get the real predictors running here.

  Either way the same single test fails —
  `test_providers.py::test_a_predictor_cannot_produce_a_score_row[esm2_t33_650m]`,
  with `ModuleNotFoundError` now and `OSError` before. That it fails at all is
  the interesting part: `ESMScorer.available()` reports the predictor as
  available and then `score()` lets the raw exception escape, instead of
  reporting itself unavailable through `PredictorUnavailableError`. A predictor
  whose runtime is missing or unloadable should take the path the pipeline
  already handles, in which case the test passes trivially and more strongly.
  Filed as open thread 10; it is a real gap in the provider, not a property of
  this machine.

- **The working tree was deleted and restored from GitHub on 2026-09-01.**
  Everything tracked came back at `d38af75`. What did not, because it is
  git-ignored, was rebuilt by hand: `.env` (from `.env.example`, with
  `POSTGRES_PORT=5434` and the parser model this machine had set),
  `node_modules`, and `apps/api/.venv`. **The Docker volumes were untouched by
  the deletion** — they live in Docker's own storage, not the project folder —
  so `codon-lab_postgres-data` still holds the 4,028 real ESM-2 scores, and
  `catalyst-ai_postgres-data` is still the pre-rename backup. Verified after the
  restore: 162/162 gate checks — the count at that date; it is 225 as of Phase 8.
- **The Postgres role and database were renamed in place**, not recreated: the
  volume holds 4,028 real ESM-2 scores that cost ~56 minutes of CPU. Renaming a
  role does **not** carry its password across, which is the trap — the role
  renamed cleanly and then every connection failed with "password authentication
  failed" until `ALTER ROLE codonlab PASSWORD ...` was run. Note also that
  `pg_isready` does not authenticate, so the compose healthcheck reported
  *healthy* throughout; and `psql -h 127.0.0.1` inside the container uses trust
  auth, so it is **not** a valid test of a password. Verify credentials from
  another container, which is the path that actually matters.

### Workarounds currently in place

Stuck `RUNNING` run — nothing reaps it, so recover manually:

```sql
UPDATE run SET status='CANCELLED', error='abandoned' WHERE status='RUNNING';
```

### Fragile — touch carefully

- `providers/mock.py` line ~122 still passes the literal `"catalyst.mock.shared"`.
  It is **deliberately not renamed**: it is an opaque hash salt, and every
  synthetic number the product has produced derives from it. Changing the token
  changes the numbers and breaks reproducibility against every stored score. A
  comment beside it says so. Do not "finish the rename" there.

- `providers/esm.py::_residue_token_start` and the `index = start + position - 1`
  arithmetic in `score()`.
- `providers/thermompnn.py` position mapping — ThermoMPNN indexes by position
  within the *parsed chain*, which is neither the sequence index nor the author
  numbering. Every mutation is checked against the residue ThermoMPNN reports.
- `domain/hashing.py` — floats are hashed via `repr`; non-finite values are
  refused. An earlier over-strict version crashed on a legitimate goal value of
  `65.0`.
- `apps/web/test/two-clicks.test.tsx` — see the mutation traps above.

---

## 9. Open threads

Ranked by priority, and **the order changed at the end of Phase 9**. The top
item is no longer a code task. Everything a machine can check about this build
is checked; what is left at the top is the one judgement no gate can make.

1. **Nothing has ever been signed in to.** Clerk is wired — provider, middleware,
   token on every request in both runtimes, account control in the rail — and
   the whole path is exercised **only** with Clerk unconfigured, which is the
   mode that skips it. No Clerk account exists, so no real token has ever
   reached `auth.verify` outside `tests/test_auth.py`'s synthetic key pairs.

   What is genuinely unverified, and cannot be verified without an account:
   that Clerk's session token carries the claims the API requires (`exp` and
   `sub` are required; `iss` is checked when set); that its JWKS URL has the
   shape `DEPLOYMENT.md` §3.3 says; and that `aud` is absent by default, which
   is why that section says to leave `CODONLAB_JWT_AUDIENCE` unset. Those are
   documented from Clerk's published behaviour, **not** from having seen one.

   First run with real keys, check in this order: the sign-in modal opens; a
   request carries `Authorization`; the API answers 200 rather than 401; a
   `user` row appears. If the API answers 401, read its log — the refusal is
   deliberately generic to the caller but the cause is logged.

2. **Nobody has looked at a single screen with a design eye — and this now
   blocks the definition of done, not just a phase.** `BRIEF.md` §4 sets the bar
   ("a structural biologist opens this next to Benchling and it does not look
   like the odd one out") and §10's last clause repeats it. No test can evaluate
   it. The assistant has driven every screen in a real browser across Phases 8
   and 9 and they render **correctly** — the scorecard's four-figure row, the
   offset proposal, the calibration curve, the workbench at 4,000 rows — but
   *correct* and *good* are different claims and only the first has ever been
   checked.

   The owner was asked directly at the start of Phase 9 to walk the screens and
   report back. They answered the delegation question in the same message
   ("whichever one results in the strongest and best possible app") but **did
   not report on the screens**, so this is still open. It is recorded in §12 as
   **unverifiable from an agent session** rather than met. Open
   <http://localhost:3000> and look; the fix for anything found is small and
   local, and the person who can see it has not seen it yet.

3. **The wet-lab handoff needs a primer designer and a PDF; the DNA blocker is
   gone.** `Target.coding_sequence` exists and is validated by translation, so
   `services/exports` no longer refuses primers for want of a template — only
   for the run's numbers being synthetic, which is a different and correct
   refusal.

   What is left is the designer itself and the one-page PDF. Every scientific
   decision is already made and written down in `ARCHITECTURE.md` §16.1 —
   nearest-neighbour Tm (SantaLucia & Hicks 2004) via **Biopython's**
   `Bio.SeqUtils.MeltingTemp` rather than hand-rolled, Owczarzy salt correction,
   Liu & Naismith 2008 partially-overlapping layout, reaction conditions as a
   project setting. None of it is implemented. Biopython is not yet a
   dependency.

   Two things to keep when building it. The refusal must stay reachable: a set
   whose run used a fabricating provider is still refused primers, and that is
   asserted. And the asymmetry in §16 still holds — a **gene fragment** may
   legitimately be back-translated because it is ordered de novo; a **primer**
   may not, because it must anneal to something that already exists.

4. **A large target now finishes across several runs, not one.**
   `JOB_TIMEOUT_SECONDS` is 3600 and the seeded luciferase (P08659) needs ~142
   minutes, so it still cannot complete in a single job. What changed is that it
   no longer has to: scoring is chunked by sequence position and **committed per
   chunk**, and `_recover_partial_scores` lets an identical later run adopt
   everything an earlier attempt finished. Verified end to end in the gate — a
   run killed with half its scores written was resumed by the next one, which
   recomputed only the missing half.

   Two things are deliberately still open. The cap has **not** been raised.
   And continuation is **manual**: a timed-out run fails, and somebody has to
   press re-run. Automatic re-enqueue is the obvious next step and is not built;
   it needs a decision about how a run reports "partly done" in the interface,
   which is a design question rather than a plumbing one.

5. **The ΔΔG interval conflict with the brief.** `BRIEF.md` §7 requires an
   interval on a ΔΔG; ThermoMPNN has no per-variant uncertainty to give, and a
   stacked design has none either. Raised three times; **delegated back on
   2026-09-01**. The decision taken: **keep refusing and state the absence** —
   `reports_interval=False` with its reason, and `AdditiveEstimate.interval_note`
   for stacked totals. A benchmark RMSE dressed as a per-variant interval is a
   fabricated number wearing a real one's appearance, and it would render
   identically to a real interval on screen.

   This leaves `BRIEF.md` §7's requirement **formally unmet, visibly**, which is
   the honest state rather than a papered-over one. Phase 8 opened a real route
   to closing it: once the scorecard accumulates enough measurements, the
   residual spread per predictor per target class *is* an empirically grounded
   interval. That needs an owner decision on the minimum n before a band is
   shown, and it is not built.

6. **"Per target class" in the scorecard is unimplemented.** `BRIEF.md` §5.9
   asks for a scorecard "per predictor per target class". The data model has no
   target taxonomy, so cards are per target or pooled across all targets, and a
   class would be an invented grouping. `ARCHITECTURE.md` §17.4. Needs either a
   `Target.class` the user sets, or an owner decision that pooled-across-targets
   is what was meant.

7. **Stale variants exist on real targets and only the join is defended.**
   Changing a target's canonical scheme leaves behind `Variant` rows written in
   the old one — 4,446 on one seeded target, 3,274 on another (§3). Phase 8's
   join excludes them and says so, but the rows are still there and any other
   surface that resolves a mutation code against stored variants has the same
   exposure. Options: mark them on the row, or refuse to change a canonical
   scheme once variants exist. Both are owner decisions about a real trade-off.

8. **There is no UI for the cost basis.** `domain/costing` reads unit prices
   from `Project.settings.cost_basis` and there is no way to set them, so the
   budget panel always shows its reason rather than a total. Deliberate that it
   refuses to invent a price; not deliberate that there is no way to supply one.

9. **The seeded scorecard demonstrates the rank path and the refusal path, not
   the error path.** The vendored ProteinGym measurements are T50 in °C, which
   is not commensurable with any predictor's metric, so MAE and bias correctly
   read `—` on the seeded data. Exercising them with *real* measured numbers
   needs a measured ΔΔG in kcal/mol; no public dataset was seeded for it because
   none was found whose quantity could be verified to mean the same thing as
   ThermoMPNN's ΔΔG. The path is covered hermetically and in the gate with
   constructed values. See `apps/api/codonlab/data/proteingym/README.md`.

10. **Frame rate is still unmeasured**, by design. When the owner runs it, record
   it here as user-verified with a date. The case to look at is **scrolling the
   table while Mol\* is mounted and holding a WebGL context**.

11. **Two real predictors have never scored the same run.** The one real
    end-to-end run used a structureless target, so ThermoMPNN skipped. The
    disagreement column has never been observed with real numbers. Needs a
    target that has a structure. Phase 8 raises the stakes: with both real
    predictors on one run, the scorecard could compare them against the 2,172
    seeded measurements directly.

12. **The containerised real-provider path is unverified.** Build the image with
    `[models]` and run the opt-in gate section (`CODONLAB_GATE_REAL_MODELS=1`).

13. **`ESMScorer` lets a runtime failure escape as `OSError`.** `available()`
    says yes, then `score()` raises instead of `PredictorUnavailableError`. A
    predictor whose runtime is installed but unloadable should report itself
    unavailable with the reason, which is what the pipeline already handles.
    This is the cause of the one expected pytest failure (§8).

14. **`Variant.region` is dead weight** — populate it deliberately or drop it.

15. **The stale conservation label** at `workbench.tsx:51` says "(Phase 6)".

16. **Alignment identity-scoring was never re-confirmed** by the owner
    (`ARCHITECTURE.md` §9).

17. **The Claude goal parser has never run against the live API.** No
    `ANTHROPIC_API_KEY` is configured, so every parse falls back to the rule
    parser and is badged as such. Do not describe it as working until it has
    been called.

18. **A cold clone has never been tested.** `docker compose up` has only ever
    run on a machine that already had images and a populated database. Phase 8
    adds a new reason to care: the seed now creates a target, 4,028 variants and
    2,172 measurements on first boot, and that path has only been exercised
    against an already-migrated database.

19. **One dark-theme colour pair fails AA, latently.** `--accent` on
    `--accent-sunk` is **4.23:1** against the 4.5:1 floor.
    `apps/web/test/contrast.test.ts` asserts the failure rather than hiding it,
    and `DESIGN.md` §1.3 records it, because the pair is **not currently
    rendered**: `--accent-sunk` is a table-row selection fill and no dark
    surface in the product contains a table. It becomes a real defect the moment
    one does. Fix by lightening `--accent` in dark or darkening `--accent-sunk`;
    do not fix by deleting the test.

20. **The a11y pass covered structure and keyboard reach, not assistive
    technology.** What is asserted: accessible names on every focusable element,
    one `<h1>` per screen, no positive `tabindex`, no unlabelled input, no
    heading-level skip, full keyboard traversal of the workbench, and every
    ratio in `tokens.css` recomputed on each build. What is **not** asserted,
    and what nobody has done: opening the app in NVDA, JAWS or VoiceOver and
    listening to it. A screen that passes every structural check can still be
    incoherent read aloud, and §12 records the clause as met only for the part
    that was measured.

21. **The screenshots in the README are regenerable but not regenerated on
    demand.** `pnpm --filter @codonlab/web screenshots` takes them from the live
    stack against subjects it picks out of the database, so they cannot drift
    silently on a machine that runs it — but nothing *makes* anyone run it. If a
    screen changes, re-run it in the same commit.

---

## 10. Immediate next steps

The nine-phase plan is finished. There is no Phase 10, so this list is no longer
"the next phase" — it is what stands between the current state and the build
being genuinely done, in the order it should be attacked.

1. **Verify the gates before changing anything.** `docker compose up -d`, then
   `python scripts/verify_gates.py` (**263 checks**). Then the per-package gates
   in §5: `pnpm typecheck`, `pnpm lint`, `pnpm test` (221), `pnpm --filter
   @codonlab/web e2e` (6), and pytest **in the container** (399 pass, 6 skipped,
   1 known failure). If anything else is red, **stop and report**.

2. **Choose an identity provider and wire the token into the web app**
   (§9.1). Nothing about a deployment works until this is done, in either auth
   mode, and that is deliberate. The provider choice is the owner's — it is a
   vendor relationship, not a tooling pick.

3. **Get the owner to walk the screens** (§9.2). This remains the item no gate
   can reach. It is the one clause of `BRIEF.md` §10 that no gate can reach, it is
   recorded in §12 as unverifiable rather than met, and every hour spent on code
   before it is an hour spent without knowing whether the thing looks right.

4. **Resumable scoring** (§9.4), because a seeded target cannot be run at all
   without it. §9.4 carries the exact shape of the change and why it was not
   taken during Phase 9.

5. **`Target.coding_sequence` plus the translation validator** (§9.3), then the
   paste field, then the primer designer against `ARCHITECTURE.md` §16.1, then
   the PDF export. This is one chain and it closes both the §5.8 gap and the
   `BRIEF.md` §10 clause that depends on it (§12, clause 6).

6. **A cost-basis UI** (§9.8), so the budget panel can show a total instead of
   its reason.

7. **Then close the loop as the working agreement requires**: extend
   `scripts/verify_gates.py` with a gate for whatever was built, update this file
   in the **same commit**, run every gate, fix everything red, commit with a real
   message, and stop and check in.

---

## 11. External references

| Resource                          | URL / identifier                                              | Used for                                        |
| --------------------------------- | ------------------------------------------------------------- | ----------------------------------------------- |
| Repo remote                       | `https://github.com/vyom-aggarwal/codon-lab.git`              | `origin`. GitHub redirects the old `catalyst-ai` URL, so older clones still work |
| ThermoMPNN                        | `github.com/Kuhlman-Lab/ThermoMPNN` @ `2b04fd370e399911b1fa5848112cc9013f084110` | Vendored source + weights, MIT   |
| ThermoMPNN paper                  | doi:10.1073/pnas.2314853121                                   | Dieckhaus et al. 2024, PNAS 121(6)              |
| ESM-2 checkpoint                  | `facebook/esm2_t33_650M_UR50D` (HuggingFace)                  | Masked-marginal scoring                         |
| MaxASA reference table            | doi:10.1371/journal.pone.0080635                              | Tien et al. 2013 *theoretical* values           |
| ProtOr radii                      | Tsai et al. 1999                                              | The van der Waals set biotite is given          |
| UniProt                           | `https://rest.uniprot.org/uniprotkb`                          | Sequence + annotation retrieval                 |
| RCSB PDB                          | `https://files.rcsb.org/download`                             | Experimental structures                         |
| AlphaFold DB                      | `https://alphafold.ebi.ac.uk/api/prediction`                  | Predicted structures                            |
| Seeded targets                    | `P37957` (*B. subtilis* lipase A, 212 aa), `P08659` (firefly luciferase, 550 aa) | The two targets everything is measured on |
| Test fixtures                     | `1CRN`, `1BTL` (TEM-1), crambin                               | SASA golden tables, ThermoMPNN smoke tests      |
| ProteinGym                        | `OATML-Markslab/ProteinGym_v0.1` on HuggingFace, assay `ESTA_BACSU_Nutschel_2020` | The 2,172 measured T50 values the scorecard is demoable on. Vendored with its SHA-256 in `apps/api/codonlab/data/proteingym/` |
| The measured DMS itself           | doi:10.1021/acs.jcim.9b00954                                  | Nutschel et al. 2020, *J. Chem. Inf. Model.* 60(3) — T50 in °C for lipase A |

No dashboards, no ticketing system, no CI service — everything is local.

---

## 12. `BRIEF.md` §10 — the definition of done, clause by clause

`BRIEF.md` §10 is the owner's definition of done. This is the required
final-phase walkthrough: every clause, with a verdict and the evidence behind
it. **Three verdicts are used and they mean different things.** *Met* means a
gate or a test asserts it and it passes. *Not met* means it is absent and that
is known. *Unverifiable from an agent session* means the claim may well be true
but nothing in this session could establish it — it is not a soft "met", and it
must not be read as one.

**Summary: 6 met, 1 met with a stated limit, 2 not met, 1 unverifiable.**

### Clause 1 — "A structural biologist can go from a UniProt accession to a ranked, constrained, explainable design set without writing code."

**Met.** Asserted end to end by `scripts/verify_gates.py`, which drives the real
HTTP API from accession to design set on every run: create project → add target
`P37957` → confirm numbering → parse and confirm a goal → start a run → poll to
`succeeded` → read ranked scores → apply constraints → build a design set. The
the confirmation-gate and two-clicks flows drive the same path through the browser with trusted
events. No step requires code from the user.

### Clause 2 — "Every number on screen traces to the model version and weights that produced it, in at most two clicks."

**Met, and counted rather than asserted.** `apps/web/test/two-clicks.test.tsx`
counts click events rather than checking that a drawer exists — the correction
§7 records the owner making. `apps/web/e2e/two-clicks.spec.ts` re-counts them
with `event.isTrusted` in a real browser that lays the page out, which catches a
mutation jsdom passes (hiding the control inside a closed `<details>`). The
drawer is checked for the **weights** hash specifically, by a locator tight
enough that matching the model id instead fails. A second test asserts every row
reaches *its own* trace, not the first row's — the mutation §8 records passing
six tests.

### Clause 3 — "No run can start from an objective the user did not agree to."

**Met, at the layer that matters.** Enforced in
`services/goals.require_confirmed`, not in a route, because the job queue is a
second caller that would route around a route-level check. Asserted three ways:
over HTTP in `verify_gates.py` (400 with a reason naming confirmation), in the
service tests, and through the UI in
`apps/web/e2e/confirmation-gate.spec.ts`, which additionally asserts the run
button is **disabled with its reason on screen** before confirmation and enabled
after — because an API that refuses correctly while the UI invites the click
still teaches the user that the affordances lie.

### Clause 4 — "Fabricated or demo data is impossible to mistake for real data."

**Met.** A persistent bar renders on **every application screen** whenever a
fabricating provider is active — Phase 4 asserted it on two screens; the Phase 9
gate asserts it on all eight it fetches, against served HTML. The landing page has no bar
and correspondingly displays no scores. Provenance is structural rather than
cosmetic: `weights_hash` is a SHA-256 of the bytes actually loaded and is never
a placeholder, and `reports_interval=False` carries its reason rather than
rendering an invented interval. The screenshot script deliberately does not crop
the bar out.

### Clause 5 — "The scorecard shows predicted versus measured with an error term and a bias term, not a correlation alone."

**Met, and this one has teeth.** `ARCHITECTURE.md` §13 exists because a
correlation was caught validating nothing (r rose to 0.998 while 8 residues
moved across a boundary). `domain/scorecard.build()` is the only entry point and
always carries Spearman, precision@k, MAE and mean signed error together, with
bias rendered visually adjacent to rank. `commensurable()` gates the absolute
error terms on unit **and** sign-convention equality and returns a stated reason
when they are withheld. Seeded with 2,172 real ProteinGym T50 measurements,
which exercise the rank path and the refusal path honestly: T50 in °C is not
commensurable with any predictor's metric, so MAE reads `—` with its reason
(§9.8). A precision@k defect found during the Phase 9 audit is fixed (§3).

### Clause 6 — "A wet-lab scientist can take the output to the bench: a plate map, primers, and a one-page PDF."

**Not met.** The design set builder and the plate map ship; the primers and the
PDF do not. The blocker is single and named: the data model has no template DNA
(§9.2), a primer anneals to the construct actually on the bench, and
back-translating the protein would produce a plausible sequence that is not the
user's plasmid. The decision is taken (user-pasted coding sequence, validated by
translation) and nothing is implemented. **This clause is knowingly open**, and
the owner was asked at the start of Phase 9 whether to close the phase with it
outstanding.

### Clause 7 — "The interface is keyboard-navigable and meets WCAG AA."

**Met for what was measured; the limit is stated.** Keyboard: `test/keyboard.test.tsx`
drives the workbench end to end with `userEvent.keyboard` and never a click —
`⌘K` opens the command palette, `?` opens the shortcut sheet (and is ignored
while a text field has focus), the table, inspector and trace drawer are all
reachable and dismissible. The structural audit over nine served screens (the landing page and eight
application screens) found
every focusable element named, exactly one visible `<h1>` per screen, no
positive `tabindex`, no unlabelled input and no heading-level skip; 38
decorative icons across 27 files were given `aria-hidden`. Contrast:
`test/contrast.test.ts` recomputes all 30 documented ratios from `tokens.css`
on every build, across 35 tests, and fails if `DESIGN.md` §1.3 disagrees — which is how a documented
**8.6:1 AAA** claim that has been false since Phase 1 was caught (it is 6.70:1,
AA). One dark pair fails AA at 4.23:1 and is recorded, not hidden, because it is
not currently rendered (§9.18).

**The limit:** this is structure and computed contrast. **Nobody has opened the
app in a screen reader** (§9.19). "Meets WCAG AA" is asserted here for the
machine-checkable part of AA only.

### Clause 8 — "The app looks like it was made by a design team that has never heard of a landing page."

**Unverifiable from an agent session — and this is the clause to read carefully,
because a landing page now exists.** The owner asked for one after the brief was
written, so the constraint changed shape: it is no longer satisfied by absence
and is now a boundary that has to hold. Mechanically, it does. `Shell` switches
on pathname and renders `/` bare, outside the application chrome. The Phase 9
gate asserts against served HTML that every application screen is inside the
application chrome and that none carries the landing hero copy, a display type size (`text-32/44/56`), or
any banned decorative device (`bg-gradient-`, `backdrop-blur`, `rounded-3xl`);
`tokens.test.ts` fails the build if a display size appears outside
`components/landing/`. **No marketing pattern has leaked into the nine screens**
— that specific question is answered, and the answer is no.

The landing page did, however, ship a defect that no gate could see and that a
human eye would have caught in seconds: its primary call to action did nothing,
because the hero's 3D viewer was starving the router (§3, §8). It is fixed and
guarded. It is also the strongest available argument for the paragraph below —
the page passed every automated check in the build while being unusable.

What cannot be answered here is the clause itself, which is an aesthetic
judgement about whether the application *looks* like serious tooling. No test
can make it. The owner was asked at the start of Phase 9 to walk the screens and
report back, and has not yet. **This clause is recorded as unverified, not as
met** (§9.1).

### Clause 9 — "Nothing in the interface implies a confidence the model does not have."

**Met, and enforced in more than one place.** Agreement between predictors is
never labelled confidence — `ARCHITECTURE.md`'s standing rule, because
predictors trained on overlapping data share their biases. Consensus is a mean
of normalised ranks, never of scores, and is **not stored**, because storing it
would require fabricating a `ModelVersion`. `reports_interval=False` renders the
absence of an interval rather than a benchmark RMSE dressed as one — which is
why `BRIEF.md` §7's interval requirement is **formally unmet and visibly so**
(§9.4) rather than quietly satisfied by an invented number. The scorecard
withholds MAE with a reason rather than computing it across incommensurable
units.

### Clause 10 — "`README.md` is accurate."

**Met at the moment of this commit, and mechanically re-checkable.** The README
was written claim by claim against the code and every count in it is a number a
gate produces: 263 gate checks, 221 vitest, 6 Playwright, 421 pytest. The
screenshots are generated by `pnpm --filter @codonlab/web screenshots` from the
live stack, against subjects the script finds in the database rather than
hard-coded ids, so regenerating them is one command and a stale one is a diff.
It documents what does **not** work — the primers, the PDF, the ΔΔG interval —
in the README itself rather than only here. The standing risk is ordinary
drift: nothing forces the screenshots to be re-run (§9.20).

---

### A clause §10 does not have

`BRIEF.md` was written for a tool that runs on one researcher's machine, so its
definition of done says nothing about being deployed, and nothing about
authentication. That is not an omission on the owner's part — it was out of
scope, correctly, for all nine phases.

It is worth stating plainly that **the deployment work is therefore not measured
by §10 at all**. None of the ten clauses got closer or further away. What
changed is that the API can now be put behind a URL without handing every
project in the database to whoever finds it, and that a design run costs a
caller something. Neither was a requirement; both are prerequisites for anyone
other than the owner ever using this.

The verdicts above stand unchanged.

### What this adds up to

Eight of ten clauses are closed. One is knowingly open behind a single named
blocker with the decision already taken (clause 6). One cannot be closed by
anyone in an agent session and is waiting on the owner's eyes (clause 8).

The honest one-line summary is: **the build does what it claims, refuses what it
cannot support, and has never been looked at by someone who can judge whether it
looks right.**

To which the deployment work adds one more: **it is now safe to put behind a
URL, and not yet usable behind one**, because the web app cannot sign anybody
in (§9.1).
