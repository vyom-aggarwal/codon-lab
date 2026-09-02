# Start here

You are picking up a multi-session build. This file orients you; it is the first
thing to read and the last thing to update.

**Status current as of 2026-09-01.** Phase 8 is complete and committed on `main`.
Phase 7's wet-lab handoff is still blocked and the blocker is named in §3 and §9;
it is the only part of phases 1-8 that did not ship.

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
assistant sessions against a fixed nine-phase plan in `BRIEF.md` §9. **Phases 1–8
of 9 are complete and committed**, with one exception: Phase 7's wet-lab handoff
exports do not ship, and are blocked on something the data model does not have
(§3). Phase 9 — Playwright smoke flows, the a11y pass, screenshots — is
untouched apart from the README, which was pulled forward. Nothing is deployed;
everything runs locally under Docker on the owner's Windows 11 machine.

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
  `scripts/verify_gates.py` (**225 checks**, over HTTP, against a live stack).
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
- **All local gates green**, re-run 2026-09-01 at the end of Phase 8: **396
  pytest** passing (6 skipped, 1 expected failure — see §8), **145 vitest across
  9 files**, ruff clean, mypy strict clean on **69 source files**,
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
| `scripts/verify_gates.py`                         | 225 checks over HTTP                     | The real gate. Self-seeding and idempotent. **Add a section per phase you complete**                 |
| `apps/api/codonlab/domain/epistasis.py`           | Stacking, the 8 A pair flag, additivity  | `Proximity` is three-valued so "not measured" cannot render as "far apart". Totals carry their assumption |
| `apps/api/codonlab/services/exports.py`           | The primer refusal                       | Built before the exporter it constrains. The only entry point, so nothing routes around it           |
| `apps/api/codonlab/domain/joining.py`             | Matching bench rows to variants          | No similarity threshold anywhere. The offset proposal is unanimous-and-unique, so there is no fraction to set wrong |
| `apps/api/codonlab/domain/scorecard.py`           | Spearman, precision@k, MAE, bias         | `build()` is the only entry point and always carries the error terms or the reason they are absent. `accumulate()` refuses the averaging shortcut by name |
| `apps/api/codonlab/services/measurements.py`      | Intake, the join, the scorecard          | Holds `_known_variants`, which excludes variants written in a superseded numbering scheme. That check is load-bearing — §3 |
| `apps/api/codonlab/data/proteingym/`              | 2,172 real measured T50 values           | Vendored with its SHA-256, its citation, and what it can and cannot demonstrate. Read by `seed.py`, never fetched at boot |
| `apps/web/components/scorecard/scorecard-card.tsx`| Rank, error and bias in one row          | The shape is a contract, not a layout preference. `scorecard.test.tsx` asserts the adjacency from the DOM |

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
pnpm typecheck; pnpm lint; pnpm test                   # 145 vitest across 9 files
cd apps\api; .venv\Scripts\python -m pytest -q        # 396 pass, 6 skipped, 1 known fail
cd apps\api; .venv\Scripts\python -m ruff check .     # clean
cd apps\api; .venv\Scripts\python -m mypy codonlab    # strict, clean, 69 files
python scripts\verify_gates.py                        # 225 checks, needs the live stack
```

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

### Traps in the tests themselves

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
- **Mol\*'s entry point is `initViewerAsync`, not `initViewer`**, and focusing a
  residue needs **author** numbering (`auth_seq_id`), not the sequence index.
- **ThermoMPNN's config object needs a `__contains__` shim** (`'lightattn' in cfg.model`),
  and its `forward` returns `(list_of_dicts, None)`, not tensors. Loading without
  pytorch-lightning means stripping the `model.` prefix Lightning puts on keys.
- **`P0CG48` is Polyubiquitin-C (685 aa), not the 76 aa ubiquitin monomer.**
  Reconciliation correctly refused it with nine candidate offsets. Not a bug.

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

Ranked by priority. **Phase 8 closed the fuzzy-join question** — the owner
delegated it back on 2026-09-01 and the answer is recorded in
`ARCHITECTURE.md` §17.1 with what would change it.

1. **The wet-lab handoff has no template DNA to design against.** Still the top
   of this list, and now the only thing standing between the build and a
   complete `BRIEF.md` §5. `BRIEF.md` §5.8 assumes site-directed mutagenesis
   primers are designable; the data model has no DNA and neither seeded target
   has any. A primer anneals to the construct actually on the bench, so this
   cannot be worked around by back-translating the protein — that would produce
   a plausible sequence that is not the user's plasmid.

   **The owner delegated this on 2026-09-01 along with the Phase 8 question.**
   The decision taken, and recorded here rather than in `ARCHITECTURE.md`
   because nothing is built yet: **the coding sequence is pasted by the user**,
   stored on a new `Target.coding_sequence`, and validated by translating it and
   asserting it matches the protein already stored. It is the only source that
   is genuinely the construct on the bench, which is the whole point of the
   screen. ENA/EMBL cross-reference was rejected because it returns the
   *reference* CDS — usually codon-optimised differently and often tagged — and
   primers designed against it may not anneal to the user's plasmid; if it is
   ever added it must be badged reference-derived and not trusted for ordering.

   **Nothing is implemented.** The column, the translation validator, the paste
   UI and the primer designer are all still to build. `ARCHITECTURE.md` §16.1
   already holds the primer chemistry. Start with the validator: it is the
   valuable half and it is testable before the attachment UI exists.

2. **The ΔΔG interval conflict with the brief.** `BRIEF.md` §7 requires an
   interval on a ΔΔG; ThermoMPNN has no per-variant uncertainty to give, and a
   stacked design has none either. Raised three times; **delegated back on
   2026-09-01** with the rest. The decision taken: **keep refusing and state the
   absence** — `reports_interval=False` with its reason, and
   `AdditiveEstimate.interval_note` for stacked totals. A benchmark RMSE dressed
   as a per-variant interval is a fabricated number wearing a real one's
   appearance, and it would render identically to a real interval on screen.

   This leaves `BRIEF.md` §7's requirement **formally unmet, visibly**, which is
   the honest state rather than a papered-over one. Phase 8 opens a real route
   to closing it: once the scorecard accumulates enough measurements, the
   residual spread per predictor per target class *is* an empirically grounded
   interval. That needs an owner decision on the minimum n before a band is
   shown, and it is not built.

3. **`JOB_TIMEOUT_SECONDS` is 3600 and a 550-residue target would be killed.**
   The lipase used 93% of it; the seeded luciferase (P08659) needs ~142 min at
   the observed rate. **Delegated back on 2026-09-01.** The decision taken:
   **make the scoring stage resumable** rather than raising the cap, which is
   what `ARCHITECTURE.md` §14.1 already names as the better fix. **Not
   implemented** — it is real work in `services/runs`, it was outside Phase 8's
   scope, and the constant has deliberately not been edited in the meantime. Do
   this before anyone runs a large target.

4. **Nobody has looked at a single screen with a human eye.** `BRIEF.md` §4 is
   emphatic about how this must look and that judgement has never been made.
   Phase 8 added two more unlooked-at screens (results intake, the scorecard).
   The assistant has now driven both in a real browser and they render
   correctly — the scorecard's four-figure row, the offset proposal panel, the
   calibration curve — but *correct* and *good* are different claims and only
   the first has been checked. Ask the owner to open <http://localhost:3000>.
   This should happen before Phase 9.

5. **"Per target class" in the scorecard is unimplemented.** `BRIEF.md` §5.9
   asks for a scorecard "per predictor per target class". The data model has no
   target taxonomy, so cards are per target or pooled across all targets, and a
   class would be an invented grouping. `ARCHITECTURE.md` §17.4. Needs either a
   `Target.class` the user sets, or an owner decision that pooled-across-targets
   is what was meant.

6. **Stale variants exist on real targets and only the join is defended.**
   Changing a target's canonical scheme leaves behind `Variant` rows written in
   the old one — 4,446 on one seeded target, 3,274 on another (§3). Phase 8's
   join excludes them and says so, but the rows are still there and any other
   surface that resolves a mutation code against stored variants has the same
   exposure. Options: mark them on the row, or refuse to change a canonical
   scheme once variants exist. Both are owner decisions about a real trade-off.

7. **There is no UI for the cost basis.** `domain/costing` reads unit prices
   from `Project.settings.cost_basis` and there is no way to set them, so the
   budget panel always shows its reason rather than a total. Deliberate that it
   refuses to invent a price; not deliberate that there is no way to supply one.

8. **The seeded scorecard demonstrates the rank path and the refusal path, not
   the error path.** The vendored ProteinGym measurements are T50 in °C, which
   is not commensurable with any predictor's metric, so MAE and bias correctly
   read `—` on the seeded data. Exercising them with *real* measured numbers
   needs a measured ΔΔG in kcal/mol; no public dataset was seeded for it because
   none was found whose quantity could be verified to mean the same thing as
   ThermoMPNN's ΔΔG. The path is covered hermetically and in the gate with
   constructed values. See `apps/api/codonlab/data/proteingym/README.md`.

9. **Frame rate is still unmeasured**, by design. When the owner runs it, record
   it here as user-verified with a date. The case to look at is **scrolling the
   table while Mol\* is mounted and holding a WebGL context**.

10. **Two real predictors have never scored the same run.** The one real
    end-to-end run used a structureless target, so ThermoMPNN skipped. The
    disagreement column has never been observed with real numbers. Needs a
    target that has a structure. Phase 8 raises the stakes: with both real
    predictors on one run, the scorecard could compare them against the 2,172
    seeded measurements directly.

11. **The containerised real-provider path is unverified.** Build the image with
    `[models]` and run the opt-in gate section (`CODONLAB_GATE_REAL_MODELS=1`).

12. **`ESMScorer` lets a runtime failure escape as `OSError`.** `available()`
    says yes, then `score()` raises instead of `PredictorUnavailableError`. A
    predictor whose runtime is installed but unloadable should report itself
    unavailable with the reason, which is what the pipeline already handles.
    This is the cause of the one expected pytest failure (§8).

13. **`Variant.region` is dead weight** — populate it deliberately or drop it.

14. **The stale conservation label** at `workbench.tsx:51` says "(Phase 6)".

15. **Alignment identity-scoring was never re-confirmed** by the owner
    (`ARCHITECTURE.md` §9).

16. **The Claude goal parser has never run against the live API.** No
    `ANTHROPIC_API_KEY` is configured, so every parse falls back to the rule
    parser and is badged as such. Do not describe it as working until it has
    been called.

17. **A cold clone has never been tested.** `docker compose up` has only ever
    run on a machine that already had images and a populated database. Phase 8
    adds a new reason to care: the seed now creates a target, 4,028 variants and
    2,172 measurements on first boot, and that path has only been exercised
    against an already-migrated database.

---

## 10. Immediate next steps

1. **Verify the gates before changing anything.** `docker compose up -d`, then
   `python scripts/verify_gates.py` (**225 checks**). Also run the per-package
   gates in §5, invoking the Python tools as `python -m <tool>`. One pytest
   failure is expected and is not yours (§8). If anything else is red, **stop
   and report** — do not proceed.

2. **Phase 9 is what remains of the plan**: Playwright smoke flows, the a11y
   pass (keyboard-only traversal of the workbench, contrast audit), and accurate
   screenshots. The README was pulled forward and is already written and
   audited — keep it that way rather than rewriting it.

3. **Before or alongside Phase 9, close the three decided-but-unbuilt threads**,
   in this order, because each is now a decision with no open question in front
   of it:
   - **Resumable scoring** (§9.3). Do this first: without it a 550-residue
     target cannot be run at all, and one is already seeded.
   - **`Target.coding_sequence` plus the translation validator** (§9.1). The
     validator is the valuable half and is testable before any UI exists. Then
     the paste field, then the primer designer against
     `ARCHITECTURE.md` §16.1.
   - **A cost-basis UI** (§9.7), so the budget panel can show a total.

4. **Get a human to look at the screens** (§9.4). This is the largest unmeasured
   risk in the build and it needs a person, not another gate.

5. **Then close the loop as the working agreement requires**: extend
   `scripts/verify_gates.py` with the new phase's exit gate, update this file in
   the **same commit**, run every gate, fix everything red, commit with a real
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
