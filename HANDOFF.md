# Start here

You are picking up a multi-session build. This file orients you; it is the first
thing to read and the last thing to update.

Status current as of **2026-08-16, end of Phase 5**.

---

## 1. Read these, in this order

| #   | File              | What it gives you                                                                        | Authority                                                                |
| --- | ----------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| 1   | `BRIEF.md`        | What the product is, why, all nine screens, the phase plan with exit gates, domain rules | **The owner's specification.** Verbatim. Never edited to match the code. |
| 2   | `DESIGN.md`       | Every colour, type size, space, radius, shadow, easing — and what is banned              | Contract. Update in the same commit as any deviation.                    |
| 3   | `ARCHITECTURE.md` | Module boundaries, the numbering subsystem, the confirmation gate, state ownership       | Contract. Same rule.                                                     |
| 4   | This file         | Status, what is unverified, decisions made in conversation, machine quirks               | Status. Rots. Trust code and tests over it.                              |

If this file contradicts `BRIEF.md`, the brief wins. If it contradicts the code,
the code wins and this file needs fixing.

## 2. The three things that must never break

From `BRIEF.md` §2 — everything else is table stakes:

1. **Parse, then confirm.** Nothing runs from an objective the user has not
   explicitly confirmed. Enforced in `services/goals.require_confirmed`, not in
   the UI, because workers are a second caller.
2. **Every number is traceable.** A `Score` cannot exist without a
   `ModelVersion` and a `Run` — `NOT NULL` foreign keys, asserted by tests that
   no future migration may relax.
3. **The validation loop** (Phase 8). The brief calls it the entire moat.

And the honesty rule that cuts across all three: **never fabricate a scientific
number outside `MockProvider`.** Unavailable means `—` with a tooltip, never an
imputed value. An unstated field means "not stated", never a plausible default.

## 3. Where things stand

| Phase                                                               | State       |
| ------------------------------------------------------------------- | ----------- |
| 1 — monorepo, Docker, migrations, token layer, primitives, one page | Done        |
| 2 — target setup, numbering reconciliation, sequence track          | Done        |
| 3 — constraints, goal composer, confirmable parse                   | Done        |
| 4 — job queue, `Predictor`, `MockProvider`, run view                | Done        |
| 5 — variant workbench, Mol\*, provenance drawer                     | Done        |
| 6 — real `ESMScorer` + `StabilityPredictor`                         | **Next**    |
| 7 — design sets, epistasis, wet-lab handoff                         | Not started |
| 8 — results intake, calibration, scorecard                          | Not started |
| 9 — Playwright, a11y, README                                        | Not started |

Exit gates for each phase are in `BRIEF.md` §9. Phase 6 has no stated exit
gate; it is real `ESMScorer` + `StabilityPredictor`, disagreement surfacing and
an agreement column.

## 4. Verify before you change anything

```sh
docker compose up -d
python scripts/verify_gates.py
```

111 checks asserting the Phase 2, 3, 4 and 5 exit gates end to end over HTTP.
It seeds its own projects and targets, so it is idempotent and safe to re-run.
**Add a section to it for each phase you complete.** The Phase 4 section needs the
`worker` container; it checks that first and says so if nothing is consuming the
queue. The Phase 5 section loads a 550-residue target and runs it, so a full pass
now takes a few minutes and several UniProt/AlphaFold fetches.

Per-package gates, all currently green:

```sh
pnpm typecheck && pnpm lint && pnpm test           # 127 vitest
cd apps/api && .venv/Scripts/python -m pytest -q   # 259 pytest
cd apps/api && .venv/Scripts/ruff check . && .venv/Scripts/mypy catalyst
```

Python tests are hermetic — no database, no network, no Redis. Anything that
genuinely crosses Postgres is asserted in `verify_gates.py` instead, because that
is the boundary a future caller actually crosses. Keep it that way.

The design system is enforced mechanically, not by discipline:
`apps/web/test/tokens.test.ts` fails the build on a hex literal, an off-scale
type size, a stock Tailwind radius, a gradient, `backdrop-blur`, emoji, a third
shadow, or `rounded-full` outside status dots. It also asserts `DESIGN.md` and
`tokens.css` agree on every colour value. **If you need a new size or colour, add
a token to `DESIGN.md` — do not reach for an arbitrary value.**

## 5. What is NOT verified — read before claiming anything works

**The Claude goal parser has never run against the real API.** No
`ANTHROPIC_API_KEY` is configured, so every parse falls back to the deterministic
rule parser and is badged as such in the UI. Its failure branches (refusal,
truncation, non-JSON, API error) are covered hermetically in
`tests/test_claude_parser.py` against a fake client. The live path is
unexercised. Do not describe it as working until it has been called.

**No screen has been looked at by a human.** Rendering was verified by fetching
HTML and asserting on content — not pixels. `BRIEF.md` §4 is emphatic about how
this must look and that judgement has not yet been made. Ask the owner to open
`localhost:3000` before Phase 9, ideally sooner.

**`docker compose up` is verified; a cold clone is not.** It has always run on a
machine that already had images and a populated database.

**Every scientific number in the product is currently synthetic.** The only
provider is `MockProvider`, registered as two predictors. Its output is
deterministic and plausibly shaped, and it is marked as synthetic in five places:
the persistent bar, a badge on every scoring stage, an asterisk on every
individual number, `ModelVersion.is_mock` in the database, and `is_demo` on the
run and the ranking. Nothing outside `catalyst/providers/mock.py` invents a
number. Do not describe any ranking this build produces as a prediction.

**The Phase 5 performance gate was rewritten by the owner** (2026-08-16) from
"10,000 rows scroll at 60fps" to **constant work per scroll update**, evidenced by
a DOM node count that does not grow with row count and a scroll height matching
rows x row height. That property is now asserted in CI —
`apps/web/test/virtualisation.test.tsx` renders 100 rows and 10,000 rows and
requires the same number of mounted `<tr>`, flat total DOM nodes, and a scroll
height accounting for every row. Disabling virtualisation fails all five.

Measured on a real 10,450-row ranking (firefly luciferase P08659, 550 residues):

| Measurement                        | Value                               |
| ---------------------------------- | ----------------------------------- |
| Ranked rows served                 | 10,450                              |
| `<tr>` in the DOM                  | 32                                  |
| DOM nodes, whole page              | 772 (0.074 per ranked row)          |
| Scroll height                      | 313,660px vs 10,450 x 30px expected |
| Synchronous scroll + forced layout | 0.8ms                               |

**Frame rate is a manual check, and it has NOT been done.** It cannot be done from
an agent session: the browser pane runs hidden, so nothing composites and
`requestAnimationFrame` never fires — which also means the virtualiser never
recalculates, so a scroll cannot even be simulated. Do not claim a frame rate in
code comments, in docs, or in a commit message until the owner has run it.

When it is run, record it here as user-verified with a date. The case the
structural evidence does not cover, and the one to look at: **scrolling the table
while Mol\* is mounted and holding a WebGL context.** That is the realistic worst
case — the viewer is live in the inspector on every selected row.

The gate's **other** half — "any score traces to a model version in two clicks" —
*is* verified, literally. Counted in a real browser with trusted clicks (row,
then Trace) for two different variants and both metrics, and locked by
`test/two-clicks.test.tsx`, which asserts the model version is invisible at zero
and one clicks and visible at two.

That test asserts **visibility**, not presence, and the difference is the point:
the first version checked presence, and a deliberate mutation hiding the Trace
control behind a closed disclosure — a genuine third click — passed it, because
jsdom keeps the contents of a closed `<details>` in the tree. If you touch the
inspector or the drawer, re-run the mutation check rather than trusting a green
tick.

The word doing the work in that gate is **any**. The original fixture carried one
metric, so "each score reaches its *own* model version" was verified in the
browser but not guarded — a mutation pointing every Trace at the first score
passed all six tests. There is now a two-predictor block that catches it, which is
the ordinary case anyway: two predictors are what make the disagreement column
mean anything.

**Mol\* has never been looked at.** It reports `ready` — WebGL initialised, the
coordinates were fetched from our own API, parsed, and the default preset
applied — and the residue-focus call is wrapped so a failure cannot take the
panel down. But everything it draws goes to a canvas, so *nothing* about the
image is verified: not that a structure is visible, not that the camera focused
the right residue, not that it is legible against our surface colour. This is
the one thing in the build that cannot be checked from the DOM.

**Nothing has been re-run after a structure changed underneath a target.** The
content-address check that would catch it exists and is unit-tested; the live
path has not been exercised.

## 6. Decisions taken in conversation

Not derivable from the code. These were agreed with the owner.

- **Tooling and dependency choices are delegated to the assistant.** Pick them,
  state the reason in one line, do not open a question. Scientific defaults are
  the opposite — always escalate.
- **Goal parsing is Claude with a deterministic fallback**, not a structured form
  and not rules-only. The fallback is not a degraded mode: it is the offline path
  and the test path, and it runs on any API failure or safety refusal.
- **Parser model defaults to `claude-opus-5`**, overridable via
  `CATALYST_PARSER_MODEL`. An earlier Sonnet 5 suggestion was withdrawn —
  downgrading for cost is the owner's call, not the assistant's.
- **UniProt constraint annotations are suggestions, never auto-applied**, and
  every position is translated into the canonical numbering scheme first.
- **3D constraint picking deferred to Phase 5** when Mol\* lands. Phase 3 ships
  the linear sequence track only.
- **Alignment uses identity scoring, not BLOSUM62.** This was an assistant
  decision, flagged for the owner's review and **not yet re-confirmed**.
  Rationale in `ARCHITECTURE.md` §9. Reversible.
- **Proposed, not agreed:** doing Phase 8 before Phase 6. The scorecard works
  against ProteinGym measurements and mock predictions, so the moat does not
  depend on real models, and it keeps the GPU question open.
- **A run scores the entire single-point space and narrows afterwards.** Every
  substitution at every nameable position, then rank, then apply the budget the
  user actually stated. Any pre-filter — only buried positions, only conservative
  substitutions — would be a scientific choice made without asking.
- **Consensus is a mean of normalised ranks, not of scores.** Averaging kcal/mol
  with a log-likelihood ratio would produce a number that sorts and means
  nothing. Assistant decision; the arithmetic is in `domain/aggregate.py` and is
  reversible.
- **The consensus is not stored.** It is not a model output and would need a
  fabricated `ModelVersion` to become a `Score`. Aggregation, filtering and
  ranking are recomputed from stored scores on every read.
- **Solvent accessibility uses `biotite`, not an implementation of ours** — the
  owner's call, and the reason is the radii set, not the effort. A DSSP-agreement
  test alone would not have caught a radii swap: a uniform-radius model correlates
  with DSSP at r=0.998 while moving 8 of TEM-1's 263 residues across a region
  boundary. Two tests ship: agreement with published DSSP for the absolute values,
  and a golden table to pin the radii set and the reference table.
- **Mutant rotamers are not modelled, and the toggle was dropped.** `BRIEF.md`
  §5.6 asks for a wild-type/mutant toggle in the viewer. Placing a mutant side
  chain needs a packer this build does not have, and a toggle that redrew the
  wild-type residue under a "mutant" label would fabricate structural data. The
  panel states the limitation instead. **Not filed as "reversible"** — it is a
  decision with a named path forward, recorded in `ARCHITECTURE.md` §12: a
  backbone-dependent rotamer library (Dunbrack), most probable rotamer, labelled
  as such, never energy-minimised. First thing to revisit when a packer lands.
- **No validation claim rests on a rank or correlation statistic alone.**
  `ARCHITECTURE.md` §13, now a standing rule. It came out of the DSSP work — a
  correlation test cannot discriminate a systematic offset, because correlation is
  invariant to the transform that produces the error. It binds Phase 6's agreement
  column (labelled *agreement*, never *confidence*) and Phase 8's scorecard, which
  must report a rank metric, an error metric (MAE, kcal/mol) and a bias term (mean
  signed error) together, with the bias visually adjacent to the rank.
- **Starting a run is idempotent on its content address.** Two identical POSTs
  return one run and a `200` on the second. Enforced by a partial unique index
  (migration 0003), not only by a service check, so a concurrent pair cannot both
  insert. Failed and cancelled runs leave the index, so retrying after a genuine
  failure starts fresh. `verify_gates.py` proves it; a direct SQL insert
  bypassing the application is refused by the database.

## 7. Open scientific decisions — ask, never decide

Each changes the advice this product gives a bench scientist.

| Decision                                                     | Blocks                  |
| ------------------------------------------------------------ | ----------------------- |
| Which objectives each **real** predictor may be offered for  | Phase 6                 |
| Primer Tm algorithm and its parameters                       | Phase 7 wet-lab handoff |
| Fuzzy-join thresholds matching bench measurements to variants | Phase 8 validation loop |

**Settled in Phase 5** by the owner, and now encoded — see `ARCHITECTURE.md` §11:
relative solvent accessibility is ASA / MaxASA using Tien et al. 2013 *theoretical*
(doi:10.1371/journal.pone.0080635); Shrake-Rupley via `biotite` with probe 1.4 Å,
1000 points, ProtOr radii, heavy atoms only; core RSA < 0.25, boundary 0.25–0.40,
surface > 0.40, as a **project setting** with those defaults; distance to the
active site is the minimum non-hydrogen atom separation to the residues the user
annotated as catalytic or ligand-contacting, and nothing is inferred.

On the second row: `Predictor.objectives` decides what the goal composer greys
out. The mock's coverage was chosen so the whole interface is exercisable and is
**not** a claim about any real model — `mock_fitness` currently claims seven
objectives. Before Phase 6 the owner must state, per real predictor, which
objectives it may be offered for. Inheriting the mock's list would have a
stability model quietly answering a specificity question.

`Variant.region` on the table is still null: burial is computed per run and stored
in that run's `FEATURES_COMPUTED` provenance event, not on the variant row, because
a variant is shared across runs and the cutoffs are not. The column on the table is
now unused — Phase 6 should either populate it deliberately or drop it.

Settled by the brief and **not** open: the ΔΔG sign convention (destabilizing
positive, kcal/mol, always with an interval), the >90% MSA conservation
high-risk flag, and the 8 Å epistasis pair-flag distance.

## 8. What Phase 6 will need to know

Phase 6 is real `ESMScorer` + `StabilityPredictor`. The seam is already there and
the mock is the proof it fits.

- **Implement the `Predictor` protocol in `providers/`** and register it in
  `providers/registry.py`. Nothing under `apps/web/components` should change —
  that is the test ARCHITECTURE.md §2 states, and it is worth actually running.
- **`objectives` is the open decision** (§7). State it per predictor. Do not copy
  the mock's list.
- **`is_mock=False` turns the whole demo apparatus off by itself**: the amber bar,
  the per-number asterisk, `is_demo` on the run and the ranking. There is no
  second switch to remember, and `/meta` derives the flag from the predictors
  rather than from `CATALYST_PROVIDERS`.
- **A predictor that needs a GPU declares `needs_gpu`**, but nothing checks it
  yet — `Capabilities.unmet` only tests structure, MSA and length. Add the check
  when there is a real predictor that would fail without one.
- **The MSA provider is the other half.** `build MSA` is a real stage that
  currently always skips, and conservation is deliberately not rendered (it is in
  the column menu, disabled, labelled "Requires MSA (Phase 6)"). Once an MSA
  exists: enable that column, and add the >90% conservation high-risk flag, which
  `BRIEF.md` §7 settles and which nothing currently implements.
- **Scores are content-addressed and cached across runs** on
  `hash(model_version + inputs)`. A real predictor gets that for free, which
  matters much more when a scoring stage costs GPU-minutes rather than a second.
  Bumping `version` or `weights_hash` correctly invalidates it.
- **`Variant.features` is still an empty dict.** Geometry lives in the run's
  `FEATURES_COMPUTED` provenance event, keyed by sequence position. Conservation
  should follow the same pattern rather than being written onto the variant row:
  a variant is shared across runs, an MSA is not.
- **`GET /runs/{id}/ranking` omits `limit` at your peril** — it applies the run's
  *budget*, not "everything". Pass `limit` for the whole ranking, and
  `include_filtered=true` to get constraint-removed variants back with their
  reasons. (An earlier version of this file said the opposite; it was wrong.)

## 9. Machine quirks

- **Postgres is on host port 5433**, not 5432 — another project's container
  (`nexus-db-1`) holds 5432. Configurable via `POSTGRES_PORT` / `REDIS_PORT`.
- **pnpm is a corepack shim** in `%APPDATA%\npm`. If missing:
  `corepack enable --install-directory "$env:APPDATA\npm"`.
- **Docker Desktop is under `%LOCALAPPDATA%\Programs\DockerDesktop`** and will
  not start from a non-interactive process — a human must launch it.
- **PowerShell 5.1 corrupts here-strings containing double quotes** when passing
  them to native commands. Write long commit messages to a file and use
  `git commit -F`.
- **The web container needs `API_INTERNAL_URL`.** Server components run inside
  the container, where `localhost` is the web container itself, not the API.
- **Adding a web dependency needs the image rebuilt, not just restarted.**
  `node_modules` lives in anonymous volumes that shadow the bind mount, so
  installing on the host is invisible to the container. Use
  `docker compose up -d --build --renew-anon-volumes web`.
- **The Windows console is cp1252** and cannot encode `→` or `°`.
  `verify_gates.py` reconfigures its own streams to UTF-8; anything else printing
  those characters needs `PYTHONIOENCODING=utf-8`.
- **The agent's browser pane runs hidden, so the page never composites.**
  `requestAnimationFrame` does not fire, which means anything driven by animation
  frames — virtualised scrolling, transitions, `screenshot` — cannot be observed
  or measured from an agent session. Plain DOM reads, `fetch`, timers and
  MutationObserver all work. Anything visual needs a human with a real browser.
- **`docker compose rm -f web` does not drop the anonymous `node_modules`
  volumes**, so a rebuilt image still starts with stale dependencies. Use
  `docker compose rm -fsv web` (note the `v`) and then `up -d`.

## 10. Working agreement

- Build in the numbered phases from `BRIEF.md` §9. After each: typecheck, lint,
  tests, fix everything red, commit with a real message.
- **Stop and check in at the end of each phase. Do not silently continue.**
- A smaller number of finished screens beats a full skeleton.
- Ask before adding a dependency outside `BRIEF.md` §3. Ask before inventing any
  scientific default.
- Commit messages here run 40+ lines on purpose. They carry the reasoning a
  summarised conversation loses. Keep writing them that way.
- Update this file's §3 and §5 in the same commit that changes them.
