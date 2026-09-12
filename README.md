# Codon Lab

**A protein-engineering copilot.** You describe what you want the protein to do, in
English. It returns a ranked, constrained list of specific mutations — and every number on
screen traces back to the model, version and weights hash that produced it.

It also refuses. When it cannot know something, it says so and says why, instead of
returning a plausible number.

---

## The problem it exists for

The models that could help a wet-lab protein engineer — ESM, ProteinMPNN, ThermoMPNN,
RFdiffusion, AlphaFold — are Python repositories with CUDA requirements, not tools. So
bench scientists either do not use them at all, or get a one-off notebook from a
computational colleague, run it once, and never trust the output enough to spend $4,000 of
ordering budget on it.

**The gap is not capability. It is trust.** A scientist will not order oligos off the back
of a number they cannot interrogate. This is built for someone skeptical, busy, and
correct.

---

## What it actually does

Nine screens, in the order you meet them. This is the whole product.

**1 · Add a target.** Paste a UniProt accession or a sequence. It fetches the sequence,
the annotations, and an experimental structure from the PDB or a predicted one from
AlphaFold DB — labelled as which.

**2 · Agree on the numbering.** The same residue is `Ser77` in the mature protein and
`Ser108` in the full-length precursor. The app shows you every scheme it found and
**refuses to accept a mutation code until you confirm which one is canonical.** This is the
single most expensive error in the domain and the app treats it that way.

**3 · Set constraints.** Catalytic residues, disulfides, ligand contacts, do-not-touch
regions. It suggests them from UniProt annotations, translated into your confirmed
numbering — and never applies one on your behalf.

**4 · Write the goal in English.** *"Make this enzyme survive 65 °C without killing
activity, one 96-well plate in E. coli, measured by DSF."* It parses that into an explicit
objective — target, budget, host, assay — and shows it back as editable chips.
**Nothing runs until you confirm that parse.**

**5 · Run it.** Six stages, each showing its model, version, input hash and runtime —
including the stage that *skipped* and why. It scores the entire single-point
substitution space, then narrows.

**6 · The workbench.** Every substitution ranked — 10,450 rows on the seeded luciferase —
virtualised so that rendering 10,000 rows mounts the same number of table rows as
rendering 100. Click any row, click Trace: model, version, weights hash, the inputs it saw,
the run it belonged to. **Two clicks, counted in tests with trusted events.**

**7 · Build a design set.** Pick variants, stack them, get epistasis warnings when two
mutations sit within 8 Å of each other. Export a plate map.

**8 · Bring back the bench results.** Upload measured values from your assay. The app
joins them to the variants it predicted — exactly, with no similarity threshold anywhere,
because `A123V` and `A123L` differ by one character and are different experiments.

**9 · The scorecard.** Predicted versus measured, per predictor, accumulating across
projects. Rank correlation, absolute error and bias, together — never a correlation alone.
Over three projects, your lab learns which predictor to trust for *your* chemistry.

### Screenshots

Generated from a running stack by `pnpm --filter @codonlab/web screenshots`, so they can be
regenerated rather than redrawn. **Nothing is cropped** — the amber bar appears in every
application shot because the default providers are synthetic, and hiding it would be the
exact fabrication it exists to prevent.

**The variant workbench** — the main screen. Ranked substitutions, the numbering scheme
named in the column header, every value carrying its sign convention and its mark.

![The variant workbench](docs/screenshots/workbench.png)

**The scorecard** — rank, error and bias in one row, with the reason printed where the
error terms cannot be computed.

![The predictor scorecard](docs/screenshots/scorecard.png)

**The run view** — six stages, each with its model, version, input hash and runtime.

![The run view](docs/screenshots/run-view.png)

---

## The three invariants

Everything else is table stakes. These three are the product, and no change may weaken
them.

### 1 · Parse, then confirm — never silently interpret

You type a goal in English. The app parses it into an explicit objective and shows that
parse back as editable chips. **Nothing runs until you confirm it.**

A tool that guesses what "more thermostable" means, and quietly proceeds, is a tool you
abandon after the first surprising result. The refusal is enforced in the service layer,
not in a route — the job queue is a second caller, and a check placed in a route can be
routed around.

### 2 · Every number is traceable

Any score on any screen reaches its model, version and weights hash **in two clicks**.
Provenance is a first-class table, not a log file, and the database refuses to store a
score without a model version and a run.

`weights_hash` is a SHA-256 of the bytes actually loaded — never a placeholder. A made-up
hash is indistinguishable from a real one in a provenance trail, which turns the entire
traceability claim into a lie.

### 3 · Never fabricate a scientific number

A model that cannot run **reports why**. The cell reads as an em dash with the reason on
hover — never an imputed value, never an estimated placeholder. The one provider allowed to
invent numbers badges every one of them, watermarks exports, and refuses to generate
primers.

---

## What it refuses to do, and why

The refusals are the product. Each one names what is wrong and what would fix it.

| It refuses to | Because |
|---|---|
| Accept a mutation code before you confirm a numbering scheme | `Ser77` and `Ser108` can be the same residue. Guessing is the most expensive error in the domain. |
| Start a run from an unconfirmed parse | A tool that guesses what your goal meant is one you stop trusting after the first surprise. |
| Report a ΔΔG interval it does not have | ThermoMPNN has no per-variant uncertainty. A benchmark RMSE dressed as an interval renders identically to a real one. |
| Compute an error term across incompatible units | A measured T50 in °C and a predicted ΔΔG in kcal/mol cannot be subtracted. The card says so instead of producing a number. |
| Fall back to another model when one is unavailable | You would get numbers from a model you did not choose, labelled as the one you did. |
| Generate primers from synthetic scores | A synthetic ΔΔG is recognisable as synthetic on screen. An oligo ordered off one is not. |
| Generate primers without your construct's DNA | A primer anneals to the plasmid on your bench. Back-translating the protein invents a sequence that is nobody's plasmid. |
| Trim a signal peptide to make your DNA fit | Every primer position would shift by the length of the leader, and a primer at the wrong position anneals to nothing. |
| Apply a numbering offset on your behalf | Even when one constant shift explains every unplaced row, it proposes and waits. |

---

## Try it locally

Requires Docker. Postgres binds host port **5433** by default (`POSTGRES_PORT` to change
it), because 5432 is often already taken.

```bash
docker compose up -d
```

That runs migrations, seeds demo data, and starts Postgres 17, Redis 7, the FastAPI
service, an RQ worker and Next.js. Then open <http://localhost:3000>.

Out of the box every number is **synthetic and marked as such**. Real predictors are
opt-in because PyTorch plus the ESM-2 checkpoint is several gigabytes:

```bash
cd apps/api && pip install -e ".[models]"
```

Then set `CODONLAB_PROVIDERS=real`. A predictor whose runtime or weights are missing
reports itself unavailable **with the reason**, and the objectives it covered grey out
carrying that same sentence.

---

## Deploying it

Vercel hosts the web app. It cannot host the rest, and the reason is the worker: a design
run scores every substitution and can take the full hour-long job timeout, while
serverless functions cap out in the low hundreds of seconds. So the web app goes to Vercel
and the API, worker, Postgres and Redis go to a container host — `render.yaml` provisions
all four in one blueprint.

Two things are enforced at the boundary, because an API behind a URL is a different object
from one on `localhost`:

- **Ownership.** A project belongs to a user; everything else reaches its owner through
  `project_id`. Enforced as a router-level dependency rather than per handler, so a route
  added later cannot forget to opt in. Somebody else's resource answers `404`, never
  `403` — the difference confirms the row exists.
- **A ceiling on runs in flight**, not a rate limit. The scarce resource is one worker
  doing hour-long jobs, so what is rationed is unfinished runs.

Identity is Clerk, verified against its JWKS, though nothing in the API is Clerk-specific.
**No credential is stored by this service** — no password hash, no reset token, no session
table. This product holds unpublished sequence data, and every part of password handling
that could be got wrong is delegated to a service whose business is getting it right.

**The API refuses to start** with `CODONLAB_AUTH=disabled` once `CORS_ORIGINS` names a
non-local origin. That combination serves every project in the database to anyone who
finds the URL, and it has no symptom until it matters.

Full instructions, the environment matrix, and an honest list of what a deployment still
cannot do are in [`DEPLOYMENT.md`](DEPLOYMENT.md).

---

## Status

| Phase | | Verified by |
|---|---|---|
| 1 — Monorepo, Docker, migrations, token layer, primitives | ✅ | `tokens.test.ts` fails the build on any off-system colour or size |
| 2 — Target setup, numbering reconciliation, sequence track | ✅ | Gate: a mutation code is refused until a canonical scheme is confirmed |
| 3 — Constraints, goal composer, confirmable parse | ✅ | Gate: no run starts from an unconfirmed parse |
| 4 — Job queue, `Predictor`, `MockProvider`, run view | ✅ | Gate: a run completes end to end with demo banners correct everywhere |
| 5 — Variant workbench, Mol\*, provenance drawer | ✅ | Gate: two clicks counted with `isTrusted`; constant work per scroll asserted |
| 6 — Real `ESMScorer` + `StabilityPredictor` | ✅ | ESM-2 matched against independent computation; ThermoMPNN sign established two ways |
| 7 — Design sets, epistasis, wet-lab handoff | ◐ | Builder, epistasis warnings and plate maps ship. A target can now carry its construct's DNA, checked by translation — **the primer designer and PDF are not built** |
| 8 — Results intake, calibration, scorecard | ✅ | **The moat.** Rank + error + bias together, demonstrated on 2,172 real measured T50 values |
| 9 — Playwright, a11y pass, README, screenshots | ◐ | ⌘K, the `?` sheet, three Playwright flows, the keyboard suite, an enforced contrast audit and regenerable screenshots ship |
| — Deployment, identity, ownership, resumable scoring | ✅ | Gate: a killed run's work is adopted by the next; the API refuses to start unauthenticated behind a real origin |

**Phase 8 is the one that matters.** You upload measured results from the bench, the app
joins them to predicted variants, and a persistent scorecard accumulates per predictor.
`BRIEF.md` §2 calls it "the entire moat" — that is the owner's read of the market,
recorded here as their claim rather than a survey this repo has run.

It ships against real data. The build seeds 2,172 measured T50 values for *B. subtilis*
lipase A from ProteinGym's `ESTA_BACSU_Nutschel_2020` (Nutschel et al. 2020,
doi:10.1021/acs.jcim.9b00954), vendored with its SHA-256 and checked byte-identical against
UniProt P37957. Against those measurements, **real ESM-2 650M scores Spearman ρ = 0.30
where the synthetic predictor scores −0.06** — measured on this machine, not quoted from a
paper.

---

## How it is built

```
apps/web         Next.js 15 App Router · React 19 · TypeScript strict · Tailwind v4
apps/api         FastAPI · Python 3.12 · Pydantic v2 · SQLModel · Postgres · RQ
packages/schema  Zod schemas — the ONLY module both apps depend on
```

`apps/web` never imports from `apps/api` and vice versa. They meet at the HTTP boundary and
at the shared schema.

### Layers in `apps/api`

Dependencies point downward only. A module never imports from a layer above it.

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

`workers/` sits beside `routes/` as a second entry point at the same level. A job must be
runnable from either without changes — which is exactly why the confirmation gate lives in
`services/`.

### The one rule that shapes everything

> **The UI must never import a model client directly.**

The web app knows about *scores* and *model versions*. It does not know that ESM exists.
Anything that varies by model arrives as **data** — `Capabilities`, `MetricSpec`,
`ModelVersion` rows — never as a branch in a component. Units and sign conventions travel
with the provider, so a second screen cannot contradict the first.

The test for whether this still holds: **adding a fourth stability predictor must touch
zero files under `apps/web/components`.**

---

## The engineering worth reading

### Residue numbering is modelled, not assumed

A `NumberingScheme` stores one label per canonical sequence position, null where the scheme
does not cover it — **not** a single integer offset. Real schemes are not constant offsets:
Ambler numbering skips residues, crystal structures leave gaps, and insertion codes are not
integers at all. A stored offset would be a lie for all three.

Reconciliation returns one of four verdicts, and `NEEDS_ALIGNMENT` is a first-class answer
that stops the app and asks rather than picking.

### No validation claim rests on a rank statistic alone

A DSSP-agreement test was supposed to validate the van der Waals radii set and **could
not**: swapping ProtOr for a uniform radius *raised* correlation to r = 0.998 while moving
8 of 1BTL's 263 residues across a region boundary. Correlation is invariant to monotonic
transforms, and a systematic offset, a scale error and a miscalibration are all monotonic.

So the scorecard reports a rank metric **and** an error metric **and** a bias term, with
bias rendered visually adjacent to rank. `domain/scorecard.build()` is the only entry point
and always carries all three, or the stated reason they are absent.

### Scoring is chunked so a killed run leaves work behind

`predictor.score()` used to be called once over the whole candidate set with nothing
written until it returned — so a run killed at the timeout had computed hours of numbers
and persisted none. A 550-residue target could not be run **at all**.

Scoring now runs in chunks of whole sequence positions, each committed, and a later run
under the same input hash adopts what an earlier attempt finished. Chunks are whole
positions because ESM-2 does one masked forward pass per position; splitting one would
repeat the expensive half of the work.

### Content addressing and idempotency

Starting a run is idempotent on its content address, enforced by a partial unique index —
not only a service check — so a concurrent pair cannot both insert. An identical request
returns the run that already exists, with `200` rather than `201`.

---

## Verification

The discipline: **Python tests are hermetic** — no database, no network, no Redis. Anything
that genuinely crosses Postgres is asserted over HTTP in `verify_gates.py`, because that is
the boundary a future caller actually crosses.

```bash
pnpm typecheck && pnpm lint && pnpm test          # 230 vitest, 14 files
python scripts/verify_gates.py                    # 263 checks, live stack
pnpm --filter @codonlab/web e2e                   # 6 Playwright flows, needs the stack
docker compose exec -T api sh -c "cd /app && python -m pytest -q"
                                                  # 451 pass, 6 skipped, 1 known failure
```

The Playwright flows exist for claims a headless DOM cannot settle: that the run button is
genuinely disabled before a parse is confirmed, that a score reaches its weights hash in
exactly two **trusted** clicks, and that the landing page stays responsive once its 3D
viewer is running.

That third flow exists because the defect it guards **actually shipped**: an ambient
rotation in the hero viewer cost ~65 ms a frame, which starved the router so completely
that the "Open the workbench" button did nothing at all. The served HTML was correct, so
the gate saw nothing, and jsdom has no frame budget. It took a real browser and a
ten-second wait.

The design system is enforced mechanically rather than by discipline:
`apps/web/test/tokens.test.ts` fails the build on a hex literal, an `rgb()`/`hsl()` literal,
an off-scale type size, a stock Tailwind radius, a gradient, `backdrop-blur`, an emoji, a
font weight ≥ 700, a third shadow, or `rounded-full` outside a status dot.

Tests here are written to **discriminate**, and the consequential ones are mutation-tested
to prove it. A mutation pointing every Trace control at the *first* score passed all six
provenance tests that existed at the time — the gate says "**any** score", and six passing
tests did not cover the word.

### What is NOT verified

Tracked in `HANDOFF.md` and stated plainly, because on this project the distinction is the
point.

- **Nobody has looked at these screens with a design eye.** The brief is emphatic about how
  this must look, and no human has judged it. No test can.
- **Nothing has ever been signed in to.** Clerk is wired end to end, but no account exists,
  so no real token has reached the verifier outside synthetic key pairs in tests.
- **The containerised real-model path.** Real predictors are verified on this machine, not
  in the deployed image.
- **A screen reader.** Structure and computed contrast are asserted on every build; nobody
  has opened the app in NVDA or VoiceOver.

### Known gaps

- **Primers and the one-page PDF are not built** — the last clause of the definition of done
  that is not met. The blocker is gone (a target can carry its construct's DNA) and the
  chemistry is decided and recorded in `ARCHITECTURE.md` §16.1; the designer itself remains.
- **`JOB_TIMEOUT_SECONDS = 3600` is still marginal.** A 550-residue target needs ~142
  minutes, so it finishes across two or three runs rather than one. Continuation is manual.
- **ΔΔG intervals.** `BRIEF.md` §7 requires an interval and ThermoMPNN has none to give. It
  reports the point estimate with the reason stated, which leaves the brief's requirement
  formally unmet, and visibly so.
- **Projects cannot be shared.** Ownership is per user; a lab wanting a shared project needs
  an organisation model that is not built.

---

## Repository

```
BRIEF.md          The owner's specification, verbatim. Never edited to match the code.
DESIGN.md         Every colour, size, space, radius, shadow, easing — and what is banned.
ARCHITECTURE.md   Module boundaries, the numbering subsystem, delegated decisions.
DEPLOYMENT.md     How to deploy it, and what a deployment still cannot do.
HANDOFF.md        Status, what is unverified, machine quirks. Rots — trust code over it.

apps/api          16,519 lines + 5,536 lines of tests
apps/web          10,685 lines + 3,276 lines of tests and end-to-end flows
packages/schema      904 lines — the Zod contract shared by both
scripts/          verify_gates.py — the phase gates, over HTTP

apps/api/codonlab/providers/_vendor/thermompnn
                   1,769 lines, MIT, pinned to one commit, provenance in every
                   file header. Counted separately because it is not ours.
```

`BRIEF.md` is the source of truth. `DESIGN.md` and `ARCHITECTURE.md` are living contracts:
**if the code deviates, the document is updated in the same commit.** `HANDOFF.md` is
status and is expected to rot — the code and tests win.

Open scientific decisions are tracked in `HANDOFF.md` §9 and are **never** decided by the
implementation. They are put to the owner; where the owner delegates one back, it is
recorded in `ARCHITECTURE.md` with its reasoning and with what would change it, so a
delegated decision does not decay into folklore.

Commit messages here run 40+ lines on purpose. They carry the reasoning a summarised
conversation loses.

---

## Definition of done

`BRIEF.md` §10 is the owner's bar. `HANDOFF.md` §12 walks all ten clauses with the evidence
behind each verdict. In summary:

| | Clause |
|---|---|
| ✅ | A structural biologist goes from accession to ranked, constrained design set without writing code |
| ✅ | Every number traces to its model version and weights in at most two clicks |
| ✅ | No run starts from an objective the user did not agree to |
| ✅ | Fabricated data is impossible to mistake for real data |
| ✅ | The scorecard shows predicted vs measured with error and bias, not correlation alone |
| ❌ | A wet-lab scientist can take the output to the bench: plate map, **primers, and a one-page PDF** |
| ◐ | Keyboard-navigable and meets WCAG AA — *structure and contrast asserted; no screen reader* |
| ? | The app looks like it was made by a design team that has never heard of a landing page — *no human has judged this* |
| ✅ | Nothing implies a confidence the model does not have |
| ✅ | This README is accurate |

**Eight of ten are closed. One is knowingly open behind named work. One cannot be closed by
anyone who has not looked at the screens.**
