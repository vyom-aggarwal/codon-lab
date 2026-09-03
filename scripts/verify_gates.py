#!/usr/bin/env python3
"""Phase gate checks, run against a live stack over HTTP.

    docker compose up -d
    python scripts/verify_gates.py

Every phase in this build has an exit gate stated in the brief. These assert
those gates end to end, through the API rather than through the service layer,
because that is the boundary a future caller actually crosses.

Self-seeding: each run creates its own project and target, so the script is
idempotent and never depends on state a previous run left behind. It costs a
handful of UniProt and AlphaFold requests.

Exits non-zero on the first failure.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

# The checks print residue arrows and degree signs, and a Windows console
# defaults to cp1252, which cannot encode them — the script died on a *passing*
# check. Nothing is dropped: unencodable characters degrade rather than raise.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://localhost:8000"
WEB = "http://localhost:3000"

#: The Phase 6 checks that load a real model are opt-in. The default gate loop
#: runs against CODONLAB_PROVIDERS=mock and stays fast; ESM-2 650M is 2.6 GB and
#: one forward pass per position. Set CODONLAB_GATE_REAL_MODELS=1 to include them.
REAL_MODELS = os.environ.get("CODONLAB_GATE_REAL_MODELS") == "1"
ACCESSION = "P37957"  # B. subtilis lipase A: a 31-residue signal peptide, so the
# full-length and mature schemes genuinely disagree.

#: A run scores the whole single-point space, so give it room, but not forever:
#: a run that has not finished by now is stuck, and saying so is the point.
RUN_TIMEOUT_SECONDS = 180

failures = 0
checks = 0


def call(
    method: str,
    path: str,
    body: object | None = None,
    *,
    retry_safe: bool | None = None,
) -> tuple[int, object]:
    """One request, retried on a dropped connection — but only where that is safe.

    The polling loops below open a fresh connection every second, and Windows
    will occasionally reset one under that load. That is a property of the
    harness, not of the API, and it once killed a run in which every check had
    passed — so a transport-level failure is retried rather than reported as a
    gate failure. An HTTP error is never retried: that is an answer.

    **Retrying is opt-in for anything that is not a GET.** A retry after a lost
    response cannot tell "the request never arrived" from "the reply never came
    back", so retrying a POST that is not idempotent creates a second of
    whatever it makes. Starting a run is idempotent on its content address, so
    that one opts in explicitly; creating a project is not, so it does not.
    """
    if retry_safe is None:
        retry_safe = method == "GET"
    attempts = 3 if retry_safe else 1

    data = json.dumps(body).encode() if body is not None else None
    last: OSError | None = None

    for attempt in range(attempts):
        request = urllib.request.Request(
            f"{BASE}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "Connection": "close"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, json.loads(response.read() or "null")
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or "null")
        except OSError as error:
            last = error
            time.sleep(1 + attempt)

    raise SystemExit(f"{method} {path} failed after {attempts} attempt(s): {last}")


def fetch_html(url: str) -> str:
    """The rendered page, for the checks that are about what a screen says."""
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return response.read().decode("utf-8", errors="replace")
    except OSError as error:
        return f"<!-- unreachable: {error} -->"


def await_run(run_id: str) -> dict:
    """Poll a run until the API says it is terminal."""
    started = time.time()
    while True:
        _, run = call("GET", f"/runs/{run_id}")
        if run.get("is_terminal") or time.time() - started > RUN_TIMEOUT_SECONDS:
            return run
        time.sleep(1)


def step(label: str, ok: bool, detail: str = "") -> None:
    global failures, checks
    checks += 1
    if not ok:
        failures += 1
    mark = "PASS" if ok else "FAIL"
    suffix = f"  {detail}" if detail else ""
    print(f"  [{mark}] {label}{suffix}")


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_repo_file(*parts: str) -> str:
    """Read a file from the repository. Returns "" if it is not there, so a
    moved file fails the step that reads it rather than the whole run."""
    path = os.path.join(REPO_ROOT, *parts)
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def section(title: str) -> None:
    print(f"\n{title}")


def main() -> int:
    for attempt in range(30):
        try:
            status, _ = call("GET", "/health")
            if status == 200:
                break
        except OSError:
            pass
        if attempt == 29:
            print("API is not reachable. Start it with `docker compose up -d`.")
            return 2
        time.sleep(1)

    stamp = int(time.time())

    section("Setup: a fresh project and target")
    status, project = call(
        "POST",
        "/projects",
        {"name": f"Gate check {stamp}", "organism": "Bacillus subtilis"},
    )
    step("project created", status == 201)
    project_id = project["id"]

    status, target = call(
        "POST", f"/projects/{project_id}/targets", {"source": "uniprot", "accession": ACCESSION}
    )
    step("target loaded from UniProt", status == 201, f"{target['name']}, {target['length']} aa")
    target_id = target["id"]

    section("Phase 2: numbering is unambiguous or refused")
    step("not designable before reconciliation", target["is_designable"] is False)
    step("candidate schemes offered, none canonical",
         len(target["numbering_schemes"]) == 2
         and not any(s["is_canonical"] for s in target["numbering_schemes"]))

    status, target = call("POST", f"/targets/{target_id}/structures", {"source": "alphafold_db"})
    step("AlphaFold structure attached", status == 201)
    structure = target["structures"][0]
    step("labelled predicted, not experimental", structure["is_predicted"] is True)

    status, recon = call(
        "POST", f"/targets/{target_id}/reconcile", {"structure_id": structure["id"]}
    )
    step("prediction reconciles exactly",
         recon["outcome"] == "reconciled" and recon["method"] == "exact",
         f"coverage {recon['coverage']:.0%}")

    status, _ = call("GET", f"/targets/{target_id}/mutation/A123V")
    step("mutation codes refused before a canonical scheme", status == 409)

    call("POST", f"/targets/{target_id}/reconcile/accept", {"structure_id": structure["id"]})
    status, target = call("GET", f"/targets/{target_id}")
    step("saving a scheme is not confirming one", target["is_designable"] is False)

    mature = next(s for s in target["numbering_schemes"] if s["kind"] == "construct")
    status, target = call(
        "POST", f"/targets/{target_id}/numbering/confirm", {"scheme_id": mature["id"]}
    )
    step("canonical confirmed", target["is_designable"] is True,
         target["canonical_scheme_label"])

    status, rendered = call("GET", f"/targets/{target_id}/mutation/A123V")
    step("mutation code carries its scheme", status == 200
         and rendered["scheme_label"] == target["canonical_scheme_label"],
         rendered.get("rendered", ""))

    section("Phase 3: no run starts from an unconfirmed parse")
    status, goal = call(
        "POST",
        f"/targets/{target_id}/goals",
        {"text": "make this enzyme survive 65 C without killing activity, "
                 "one 96-well plate in E. coli, measured by DSF"},
    )
    step("goal parsed", status == 201, f"method={goal['method']}")
    spec = goal["spec"]
    step("objective read", spec["objective"] == "thermostability")
    step("stated target kept in its own unit",
         spec["target_value"] == {"value": 65, "unit": "°C"})
    step("budget read", spec["budget"]["variants"] == 96)

    _, pre = call("GET", f"/goals/{goal['id']}/preflight")
    step("preflight refuses an unconfirmed parse", pre["can_start"] is False)

    status, vague = call(
        "POST", f"/targets/{target_id}/goals", {"text": "do something clever with this protein"}
    )
    step("no objective invented", vague["spec"]["objective"] is None)
    status, _ = call("POST", f"/goals/{vague['id']}/confirm")
    step("an incomplete objective cannot be confirmed", status == 400)

    status, confirmed = call("POST", f"/goals/{goal['id']}/confirm")
    step("confirming unlocks the run", status == 200 and confirmed["is_confirmed"] is True)
    _, pre = call("GET", f"/goals/{goal['id']}/preflight")
    step("preflight allows", pre["can_start"] is True)

    edited = dict(spec)
    edited["target_value"] = {"value": 70, "unit": "°C"}
    status, after = call("POST", f"/goals/{goal['id']}", {"spec": edited})
    step("editing a chip clears the confirmation", after["is_confirmed"] is False)

    combined = " ".join(after["expectations"]["will_not"]).lower()
    step("states it will not predict a Tm shift", "melting temperature" in combined)
    step("states stacking is assumed additive", "additive" in combined)

    section("Phase 3: constraints are translated and never auto-applied")
    _, before = call("GET", f"/targets/{target_id}/constraints")
    status, suggestions = call("GET", f"/targets/{target_id}/constraints/suggestions")
    step("suggestions returned", status == 200 and len(suggestions) > 0,
         f"{len(suggestions)} from UniProt")
    _, unchanged = call("GET", f"/targets/{target_id}/constraints")
    step("fetching suggestions applied nothing", len(unchanged) == len(before))

    catalytic = [s for s in suggestions if s["kind"] == "catalytic"]
    step("catalytic residues suggested", len(catalytic) > 0)
    if catalytic:
        # The point of the whole numbering subsystem: UniProt annotates the
        # nucleophile at 108; under mature numbering it is residue 77.
        note = catalytic[0]["note"]
        step("position translated out of UniProt numbering",
             "108" in note and "77" in note, note[:100])

    status, created = call(
        "POST",
        f"/targets/{target_id}/constraints",
        {"kind": catalytic[0]["kind"], "positions": catalytic[0]["positions"]},
    )
    step("accepted on request", status == 201)
    step("labelled in the canonical scheme", created["labels"] == catalytic[0]["labels"],
         ", ".join(created["labels"]))

    status, _ = call(
        "POST", f"/targets/{target_id}/constraints", {"kind": "catalytic", "positions": [99999]}
    )
    step("out-of-range positions refused", status == 400)

    # ----------------------------------------------------------------- Phase 4

    section("Phase 4: a run completes end to end")

    # The objective was edited above, which cleared its confirmation. That makes
    # this the gate's second caller, checked where it actually matters.
    status, refused = call("POST", f"/goals/{goal['id']}/runs", {})
    step("a run cannot start from an unconfirmed parse", status == 400,
         refused["detail"]["message"])

    call("POST", f"/goals/{goal['id']}/confirm")
    status, run = call("POST", f"/goals/{goal['id']}/runs", {})
    step("run started once confirmed", status == 201, f"status={run['status']}")

    _, queue = call("GET", "/queue")
    step("a worker is consuming the queue", queue["connected"] and queue["workers"] >= 1,
         f"{queue['workers']} worker(s)")

    run = await_run(run["id"])
    step("run succeeded", run["status"] == "succeeded", run.get("error") or "")

    names = [stage["name"] for stage in run["stages"]]
    step("pipeline is the one the brief states",
         names[0] == "retrieve structure" and names[1] == "build MSA"
         and names[-3:] == ["aggregate", "filter by constraints", "rank"],
         " -> ".join(names))

    scoring = [stage for stage in run["stages"] if stage["model"]]
    step("every scoring stage names its model, version and weights",
         len(scoring) >= 2
         and all(s["model"]["name"] and s["model"]["version"] and s["model"]["weights_hash"]
                 for s in scoring))
    step("every stage that ran reports a runtime",
         all(s["runtime_ms"] is not None
             for s in run["stages"] if s["status"] in ("succeeded", "skipped")))
    step("streaming logs are recorded per stage",
         all(s["logs"] for s in run["stages"] if s["status"] in ("succeeded", "skipped")))

    section("Phase 4: demo banners are correct everywhere")
    _, meta = call("GET", "/meta")
    step("service reports demo mode", meta["demo_mode"] is True)
    step("every active predictor declares itself synthetic",
         len(meta["predictors"]) > 0 and all(p["is_mock"] for p in meta["predictors"]),
         ", ".join(p["id"] for p in meta["predictors"]))
    step("no provider id matched nothing", meta["unknown_providers"] == [])
    step("an unnamed objective is supported by nobody",
         "other" not in meta["supported_objectives"])
    step("the run is flagged synthetic", run["is_demo"] is True)

    _, ranking = call("GET", f"/runs/{run['id']}/ranking?limit=25")
    step("the ranking is flagged synthetic", ranking["is_demo"] is True)
    cells = [cell for row in ranking["rows"] for cell in row["cells"]]
    step("every individual number is badged", len(cells) > 0 and all(c["is_mock"] for c in cells),
         f"{len(cells)} numbers")
    step("every number carries the model version that produced it",
         all(c["model_version_id"] for c in cells))

    page = fetch_html(f"{WEB}/runs/{run['id']}")
    step("the run screen carries the persistent bar", "Demo data" in page)
    step("the projects screen carries it too", "Demo data" in fetch_html(f"{WEB}/projects"))

    section("Phase 4: results are traceable, numbered and honest")
    step("every metric states its sign convention",
         len(ranking["metrics"]) > 0 and all(m["sign_convention"] for m in ranking["metrics"]),
         "; ".join(f"{m['id']}: {m['sign_convention']}" for m in ranking["metrics"]))
    ddg = next((m for m in ranking["metrics"] if m["id"] == "ddg_kcal_per_mol"), None)
    step("stability is reported destabilizing-positive in kcal/mol",
         ddg is not None and ddg["unit"] == "kcal/mol"
         and ddg["sign_convention"] == "destabilizing positive")
    step("no stability value is a bare point estimate",
         all(c["uncertainty"] is not None and c["ci_low"] is not None
             for c in cells if c["metric"] == "ddg_kcal_per_mol"))
    step("the ranking is labelled with the canonical scheme",
         ranking["scheme_label"] == target["canonical_scheme_label"], ranking["scheme_label"])

    # The whole numbering subsystem, seen from the far end: UniProt annotates the
    # nucleophile at 108, mature numbering calls it 77, and the codes this run
    # produced must be written in the scheme the user confirmed.
    _, filtered = call("GET", f"/runs/{run['id']}/filtered")
    removed = filtered["removed"]
    step("constrained variants were removed with the reason kept",
         len(removed) > 0 and all(reasons for reasons in removed.values()),
         f"{len(removed)} removed")
    step("removed variants name the constraint that removed them",
         all("catalytic" in reasons for reasons in removed.values()))
    step("mutation codes are written in the canonical scheme, not sequence index",
         any(code.startswith("S77") for code in removed)
         and not any(code.startswith("S108") for code in removed),
         ", ".join(sorted(removed)[:3]))
    step("no removed variant survived into the ranking",
         not any(row["code"] in removed for row in ranking["rows"]))

    step("the stated budget bounds the ranking",
         ranking["budget"] == 96 and len(ranking["rows"]) <= 96)
    step("the full ranking stays retrievable behind the budget",
         ranking["total_ranked"] > len(ranking["rows"]),
         f"{ranking['total_ranked']} ranked, {len(ranking['rows'])} shown")
    step("disagreement is reported, not averaged away",
         all("disagreement" in row for row in ranking["rows"])
         and any(row["sources_scored"] > 1 for row in ranking["rows"]))

    section("Phase 4: a predictor that cannot run says so")
    # A second target from the same real sequence, with no structure attached.
    # The stability predictor requires one, so it must skip with a reason rather
    # than return something worthless.
    status, bare = call(
        "POST",
        f"/projects/{project_id}/targets",
        {"source": "sequence", "name": "Lipase A, no structure", "text": target["sequence"]},
    )
    step("a structureless target loads", status == 201)
    scheme = bare["numbering_schemes"][0]
    call("POST", f"/targets/{bare['id']}/numbering/confirm", {"scheme_id": scheme["id"]})
    _, bare_goal = call(
        "POST", f"/targets/{bare['id']}/goals", {"text": "improve thermostability"}
    )
    call("POST", f"/goals/{bare_goal['id']}/confirm")
    _, bare_run = call("POST", f"/goals/{bare_goal['id']}/runs", {})
    bare_run = await_run(bare_run["id"])
    step("the run still completes", bare_run["status"] == "succeeded", bare_run.get("error") or "")

    skipped = [s for s in bare_run["stages"] if s["status"] == "skipped" and s["model"]]
    step("the predictor needing a structure was skipped", len(skipped) == 1,
         skipped[0]["model"]["name"] if skipped else "")
    step("the skip states what is missing and how to fix it",
         bool(skipped) and "structure" in (skipped[0]["logs"] or "").lower()
         and "attach" in (skipped[0]["logs"] or "").lower())

    _, bare_ranking = call("GET", f"/runs/{bare_run['id']}/ranking?limit=5")
    step("its column reads unavailable with a reason, not zero",
         "ddg_kcal_per_mol" in bare_ranking["unavailable"]
         and bool(bare_ranking["unavailable"]["ddg_kcal_per_mol"]))
    step("no value was imputed for the predictor that did not run",
         all(c["metric"] != "ddg_kcal_per_mol"
             for row in bare_ranking["rows"] for c in row["cells"]))
    step("one opinion reports no disagreement rather than zero",
         all(row["disagreement"] is None for row in bare_ranking["rows"]))

    section("Phase 4: re-run with one parameter changed, and diff it")
    status, child = call("POST", f"/runs/{run['id']}/rerun", {"max_variants": 24})
    step("re-run started", status == 201)
    child = await_run(child["id"])
    step("re-run succeeded", child["status"] == "succeeded")

    _, diff = call("GET", f"/runs/{child['id']}/diff")
    step("exactly one parameter differs", len(diff["config_changes"]) == 1
         and diff["config_changes"][0]["key"] == "max_variants",
         str(diff["config_changes"]))
    reused = [s["name"] for s in diff["stages"] if s["reused"]]
    step("scoring did not re-execute for unchanged inputs",
         all(s["reused"] for s in diff["stages"] if s["name"].startswith("score with")),
         ", ".join(reused))
    step("no score changed", diff["scores"]["changed"] == 0 and diff["scores"]["unchanged"] > 0,
         f"{diff['scores']['unchanged']} unchanged")
    step("the ranking narrowed to the new budget",
         len(diff["left"]) > 0 and len(diff["entered"]) == 0)

    status, _ = call("POST", f"/runs/{run['id']}/rerun", {})
    step("a re-run that changes nothing is refused", status == 400)
    status, _ = call("GET", f"/runs/{run['id']}/diff")
    step("a run with no predecessor has nothing to diff", status == 400)

    section("Phase 4: cancelling")
    _, third = call("POST", f"/goals/{goal['id']}/runs", {"max_variants": 5})
    status, cancelled = call("POST", f"/runs/{third['id']}/cancel")
    # Either it was still in flight and is now cancelled, or it had already
    # finished and the API refused. What must never happen is a silent no-op.
    if status == 200:
        step("cancelling a live run stops it", cancelled["status"] == "cancelled")
        step("no stage is left waiting after a cancel",
             all(s["status"] != "pending" for s in cancelled["stages"]))
    else:
        step("cancelling a finished run is refused, not ignored", status == 400,
             cancelled["detail"]["message"])
    _, done = call("GET", f"/runs/{third['id']}")
    status, _ = call("POST", f"/runs/{done['id']}/cancel")
    step("a terminal run cannot be cancelled twice", status == 400)

    section("Phase 4: starting a run is idempotent")
    # The failure this prevents: a client retries after a lost response and
    # starts the same work twice. The duplicate is indistinguishable from a
    # deliberate re-run, and it is how a queue fills with duplicate jobs
    # overnight. `call` retries transport failures, so this endpoint has to be
    # safe under exactly that.
    _, before_runs = call("GET", f"/targets/{target_id}/runs")
    identical = {"max_variants": 31}

    status_a, first = call("POST", f"/goals/{goal['id']}/runs", identical, retry_safe=True)
    step("a run starts", status_a == 201, f"run {first['id'][:8]}")

    status_b, again = call("POST", f"/goals/{goal['id']}/runs", identical, retry_safe=True)
    step("an identical request returns the same run, not a second one",
         again["id"] == first["id"], f"{again['id'][:8]} == {first['id'][:8]}")
    step("and says so with 200 rather than 201", status_b == 200, f"status {status_b}")

    _, after_runs = call("GET", f"/targets/{target_id}/runs")
    step("exactly one run was created by the two requests",
         len(after_runs) == len(before_runs) + 1,
         f"{len(before_runs)} -> {len(after_runs)}")
    step("both requests share one content address",
         again["input_hash"] == first["input_hash"])

    # A different parameter is a different run, or deduplication would be
    # swallowing work the user asked for.
    status_c, different = call("POST", f"/goals/{goal['id']}/runs", {"max_variants": 32})
    step("a different parameter still starts a new run",
         status_c == 201 and different["id"] != first["id"])

    # ----------------------------------------------------------------- Phase 5

    section("Phase 5: any score traces to a model version")
    # The gate's second half, asserted at the boundary the workbench uses. Click
    # one is the row; click two is Trace. Both resolve through this data.
    _, full = call("GET", f"/runs/{run['id']}/ranking?limit=100000")
    row = full["rows"][0]
    cells = row["cells"]
    step("a ranked row carries its own scores", len(cells) > 0)

    versions = {
        stage["model"]["id"]: stage for stage in run["stages"] if stage["model"]
    }
    traced = [cell for cell in cells if cell["model_version_id"] in versions]
    step("every number resolves to a model version in this run", len(traced) == len(cells))
    if traced:
        model = versions[traced[0]["model_version_id"]]["model"]
        step("the model version carries what a PI needs to reproduce it",
             all(model[key] for key in ("name", "version", "weights_hash", "citation")),
             f"{model['name']} {model['version']} weights {model['weights_hash'][:19]}")
        step("and the stage that produced it carries its input hash",
             bool(versions[traced[0]["model_version_id"]]["input_hash"]))

    section("Phase 5: geometry is computed, cited and reproducible")
    manifest = full["features_manifest"]
    step("features were measured", bool(manifest), f"{len(full['rows'])} rows carry them")
    step("the normalisation table is cited by DOI",
         manifest.get("reference_doi") == "10.1371/journal.pone.0080635",
         str(manifest.get("reference_set")))
    sasa = manifest.get("sasa", {})
    step("SASA parameters are stated, not defaulted",
         sasa.get("probe_radius_angstrom") == 1.4 and sasa.get("point_number") == 1000
         and "ProtOr" in str(sasa.get("vdw_radii")),
         f"probe {sasa.get('probe_radius_angstrom')} A, {sasa.get('point_number')} points")
    step("the coordinate set is stated rather than assumed",
         "monomer" in str(manifest.get("assembly")) or "chains" in str(manifest.get("assembly")),
         str(manifest.get("assembly")))
    step("ligand handling is recorded", "excluded" in str(manifest.get("ligand_handling")))

    cutoffs = manifest.get("cutoffs", {})
    step("the cutoffs in force are in the run's record, not only in the code",
         cutoffs.get("core_rsa_below") == 0.25 and cutoffs.get("surface_rsa_above") == 0.40,
         f"core < {cutoffs.get('core_rsa_below')}, surface > {cutoffs.get('surface_rsa_above')}")

    measured = [r for r in full["rows"] if r["features"]["rsa"] is not None]
    step("RSA was computed for the ranked variants", len(measured) > 0,
         f"{len(measured)} of {len(full['rows'])}")
    step("no residue exceeds its published maximum",
         all(r["features"]["rsa"] <= 1.0 for r in measured))
    step("region follows the cutoffs exactly", all(
        (r["features"]["region"] == "core") == (r["features"]["rsa"] < 0.25)
        and (r["features"]["region"] == "surface") == (r["features"]["rsa"] > 0.40)
        for r in measured))
    step("the structure's own numbering travels with the geometry",
         all(r["features"]["author_label"] for r in measured),
         "author labels present for the viewer")

    distances = [r["features"]["distance_to_active_site"] for r in full["rows"]]
    step("distance to the annotated active site is measured",
         any(d is not None for d in distances),
         f"{min(d for d in distances if d is not None)}-"
         f"{max(d for d in distances if d is not None)} A")

    # A target with no catalytic annotation must say so rather than report zero.
    _, bare_full = call("GET", f"/runs/{bare_run['id']}/ranking?limit=100")
    step("no annotated active site means no distance, not a zero",
         all(r["features"]["distance_to_active_site"] is None for r in bare_full["rows"]))

    section("Phase 5: settings are a decision, recorded per run")
    _, project_before = call("GET", f"/projects/{project_id}")
    step("cutoffs are exposed as a project setting",
         project_before["rsa_cutoffs"] == {"core_max": 0.25, "surface_min": 0.4})
    status, _ = call("POST", f"/projects/{project_id}/settings/rsa-cutoffs",
                     {"core_max": 0.6, "surface_min": 0.2})
    step("cutoffs that are not an ordered partition are refused", status == 400)
    status, changed = call("POST", f"/projects/{project_id}/settings/rsa-cutoffs",
                           {"core_max": 0.10, "surface_min": 0.50})
    step("cutoffs can be changed", status == 200
         and changed["rsa_cutoffs"] == {"core_max": 0.1, "surface_min": 0.5})
    _, after = call("GET", f"/runs/{run['id']}/ranking?limit=5")
    step("changing them does not rewrite what an earlier run reported",
         after["features_manifest"]["cutoffs"]["core_rsa_below"] == 0.25,
         "the run still reports the values that were in force when it ran")
    call("POST", f"/projects/{project_id}/settings/rsa-cutoffs",
         {"core_max": 0.25, "surface_min": 0.40})

    section("Phase 5: filtered variants stay retrievable")
    _, without = call("GET", f"/runs/{run['id']}/ranking?limit=100000")
    _, with_removed = call("GET",
                           f"/runs/{run['id']}/ranking?limit=100000&include_filtered=true")
    step("a hard filter does not return its own output by default",
         len(with_removed["rows"]) > len(without["rows"]),
         f"{len(without['rows'])} vs {len(with_removed['rows'])}")
    reinstated = [r for r in with_removed["rows"] if r["filtered_by"]]
    step("each one is retrievable with the constraint that removed it",
         len(reinstated) > 0 and all("catalytic" in r["filtered_by"] for r in reinstated),
         f"{len(reinstated)} removed variants, each with its reason")

    section("Phase 5: the workbench holds ten thousand rows")
    # A real target large enough to exceed the bar, not a synthetic one:
    # firefly luciferase is 550 residues, so its single-point space is 10,450.
    status, big_project = call("POST", "/projects",
                               {"name": f"Scale check {stamp}", "organism": "Photinus pyralis"})
    status, big = call("POST", f"/projects/{big_project['id']}/targets",
                       {"source": "uniprot", "accession": "P08659"})
    step("a 550-residue target loads", status == 201, f"{big['length']} aa")
    status, big = call("POST", f"/targets/{big['id']}/structures", {"source": "alphafold_db"})
    big_structure = big["structures"][0]["id"]
    call("POST", f"/targets/{big['id']}/reconcile/accept", {"structure_id": big_structure})
    _, big = call("GET", f"/targets/{big['id']}")
    author = next(s for s in big["numbering_schemes"] if s["kind"] == "pdb_author")
    call("POST", f"/targets/{big['id']}/numbering/confirm", {"scheme_id": author["id"]})
    _, big_goal = call("POST", f"/targets/{big['id']}/goals",
                       {"text": "improve thermostability"})
    call("POST", f"/goals/{big_goal['id']}/confirm")
    _, big_run = call("POST", f"/goals/{big_goal['id']}/runs", {})
    big_run = await_run(big_run["id"])
    step("the run completes", big_run["status"] == "succeeded", big_run.get("error") or "")

    _, big_ranking = call("GET", f"/runs/{big_run['id']}/ranking?limit=100000")
    step("more than ten thousand variants are ranked and served",
         len(big_ranking["rows"]) > 10000, f"{len(big_ranking['rows']):,} rows")
    step("every one of them carries its scores",
         all(r["cells"] for r in big_ranking["rows"][:500]))
    # The exit gate's performance half is a rendering property and is not
    # asserted here: this script speaks HTTP and cannot see a frame. What it can
    # hold is that the data the workbench virtualises is genuinely this large.
    page = fetch_html(f"{WEB}/runs/{big_run['id']}/workbench")
    step("the workbench screen serves", "Variant workbench" in page or "workbench" in page.lower())
    step("and carries the persistent demo bar", "Demo data" in page)

    # ----------------------------------------------------------------- Phase 6

    section("Phase 6: real predictors declare themselves, and never fall back")
    _, meta = call("GET", "/meta")
    by_id = {p["id"]: p for p in meta["predictors"]}
    registry = fetch_html(f"{BASE}/openapi.json")  # cheap liveness on the API
    step("the API describes its predictors", len(by_id) > 0 and bool(registry),
         ", ".join(sorted(by_id)))

    real = [p for p in by_id.values() if not p["is_mock"]]
    mock = [p for p in by_id.values() if p["is_mock"]]
    step("the shipped default is the synthetic set", len(mock) >= 1 and not real,
         "CODONLAB_PROVIDERS=mock, so the gate loop stays fast")

    section("Phase 6: every predictor states what it will and will not answer")
    support = meta["objective_support"]
    step("every objective is accounted for", len(support) == 8, f"{len(support)} objectives")
    unsupported = {name: entry for name, entry in support.items() if not entry["supported"]}
    step("an unsupported objective carries a stated reason, never silence",
         all(entry["reason"] for entry in unsupported.values()),
         f"{len(unsupported)} greyed out")
    step("an unnamed objective is supported by nobody, and says why",
         support["other"]["supported"] is False
         and "has not been named" in (support["other"]["reason"] or ""))

    if REAL_MODELS:
        section("Phase 6: the real predictors load and produce scores")
        # Opt-in. Needs CODONLAB_PROVIDERS to include the real set on the API and
        # the worker, and the weights present where the worker can reach them.
        real_ids = [p["id"] for p in by_id.values() if not p["is_mock"]]
        step("a real predictor is configured", bool(real_ids), ", ".join(real_ids))

        for predictor in (p for p in by_id.values() if not p["is_mock"]):
            step(f"{predictor['id']} reports itself available",
                 predictor["available"] is True,
                 predictor["unavailable_reason"] or "")
            step(f"{predictor['id']} carries a real weights hash",
                 predictor["weights_hash"].startswith("sha256:")
                 and len(predictor["weights_hash"]) == 71,
                 predictor["weights_hash"][:26])
            step(f"{predictor['id']} cites a DOI", "doi.org" in predictor["citation"])

        _, real_goal = call("POST", f"/targets/{target_id}/goals",
                            {"text": "improve thermostability"})
        call("POST", f"/goals/{real_goal['id']}/confirm")
        _, real_run = call("POST", f"/goals/{real_goal['id']}/runs", {"max_variants": 10})
        real_run = await_run(real_run["id"])
        step("a run with real predictors completes", real_run["status"] == "succeeded",
             real_run.get("error") or "")
        step("the run is NOT flagged synthetic", real_run["is_demo"] is False)

        _, real_ranking = call("GET", f"/runs/{real_run['id']}/ranking?limit=10")
        real_cells = [c for row in real_ranking["rows"] for c in row["cells"]]
        step("real numbers are not badged synthetic",
             bool(real_cells) and not any(c["is_mock"] for c in real_cells),
             f"{len(real_cells)} numbers")
        step("every real number still carries its model version",
             all(c["model_version_id"] for c in real_cells))
    else:
        section("Phase 6: real-model checks skipped")
        step("opt-in checks are available", True,
             "set CODONLAB_GATE_REAL_MODELS=1 (and CODONLAB_PROVIDERS=real) to run them")

    # ----------------------------------------------------------------- Phase 7

    section("Phase 7: a design set is built from one run, and says what it assumes")
    _, design_set = call(
        "POST",
        f"/runs/{run['id']}/design-sets",
        {"name": f"Gate set {stamp}", "budget_amount": 4000, "budget_currency": "USD"},
    )
    set_id = design_set["design_set_id"]
    step("a design set starts from a run", bool(set_id) and design_set["run_id"] == run["id"])

    # Four singles the constraints did not remove, so nothing here needs an
    # override yet — the override path is exercised deliberately below.
    survivors = [r["code"] for r in full["rows"] if not r["filtered_by"]][:4]
    _, added = call("POST", f"/design-sets/{set_id}/members", {"codes": survivors})
    step("designs are added to the set", len(added["members"]) == len(survivors),
         f"{len(added['members'])} members")
    step("a single-point design carries no pair flag",
         all(not m["pairs"] for m in added["members"] if not m["is_stacked"]))
    step("the set is labelled with the canonical scheme",
         added["scheme_label"] == target["canonical_scheme_label"], added["scheme_label"])

    section("Phase 7: stacking is combinatorial, and says what it left out")
    call("POST", f"/design-sets/{set_id}/stack", {"codes": survivors, "size": 2})
    _, built = call("GET", f"/design-sets/{set_id}")
    combinations = [m for m in built["members"] if m["is_stacked"]]
    step("every pair of the selection was built", len(combinations) == 6,
         f"C(4,2) = 6, built {len(combinations)}")
    step("a stacked design renders both mutation forms",
         all("/" in m["hgvs"] and m["hgvs"].startswith("p.") for m in combinations))
    step("a stacked design is one variant row per combination",
         len({m["variant_id"] for m in combinations}) == len(combinations))

    _, capped = call("POST", f"/design-sets/{set_id}/stack",
                     {"codes": survivors, "size": 2, "limit": 2})
    step("a truncated enumeration says it was truncated",
         any("cap" in note for note in capped["notes"]), "; ".join(capped["notes"])[:70])

    section("Phase 7: the 8 A pair flag is measured, not assumed")
    warning = built["warning"]
    step("the cutoff is the one the brief states", warning["cutoff_angstrom"] == 8.0)
    step("the separation convention is stated, not implied",
         "non-hydrogen" in warning["distance_convention"]
         and "CA-CA" in warning["distance_convention"])
    flags = [pair for m in combinations for pair in m["pairs"]]
    step("every pair carries a proximity state", len(flags) == 6
         and all(p["proximity"] in ("within", "beyond", "unknown") for p in flags))
    measured_pairs = [p for p in flags if p["proximity"] != "unknown"]
    step("this target has a structure, so the pairs were measured",
         len(measured_pairs) == len(flags), f"{len(measured_pairs)} of {len(flags)}")
    step("a measured pair carries its separation and no stale reason",
         all(p["separation_angstrom"] is not None and p["reason"] is None
             for p in measured_pairs))
    step("the flag follows the cutoff exactly",
         all((p["separation_angstrom"] <= 8.0) == (p["proximity"] == "within")
             for p in measured_pairs))
    step("the geometry manifest records what was measured on",
         built["geometry_manifest"].get("measure")
         == "minimum non-hydrogen atom separation",
         str(built["geometry_manifest"].get("structure", "")))

    section("Phase 7: a stacked total is arithmetic, labelled as an assumption")
    values = {r["code"]: {c["metric"]: c["value"] for c in r["cells"]} for r in full["rows"]}
    recomputed = 0
    mismatched = []
    for member in combinations:
        for estimate in member["additive"]:
            parts = [values.get(code, {}).get(estimate["metric"]) for code in member["mutations"]]
            if any(part is None for part in parts):
                continue
            expected = round(sum(parts), 4)
            if estimate["total"] is None or abs(estimate["total"] - expected) > 1e-6:
                mismatched.append(f"{member['code']}/{estimate['metric']}")
            else:
                recomputed += 1
    step("a stacked total is the sum of its single-mutant values",
         recomputed > 0 and not mismatched,
         f"{recomputed} totals recomputed independently"
         + (f"; mismatched: {', '.join(mismatched[:3])}" if mismatched else ""))
    step("every total carries the additivity assumption",
         all("epistasis" in e["assumption"] and "not a prediction" in e["assumption"]
             for m in combinations for e in m["additive"]))
    step("a stacked total states it has no interval, rather than leaving a blank",
         all("No interval" in e["interval_note"]
             for m in combinations for e in m["additive"]))
    step("the sign convention travels with the total",
         all(e["sign_convention"] for m in combinations for e in m["additive"]))
    step("the epistasis warning counts what it found",
         warning["stacked_designs"] == 6 and warning["pairs_total"] == 6)

    section("Phase 7: unmeasured is not the same as far apart")
    _, bare_set = call("POST", f"/runs/{bare_run['id']}/design-sets",
                       {"name": f"Gate bare set {stamp}"})
    bare_set_id = bare_set["design_set_id"]
    bare_codes = [r["code"] for r in bare_full["rows"]][:3]
    call("POST", f"/design-sets/{bare_set_id}/members", {"codes": bare_codes})
    call("POST", f"/design-sets/{bare_set_id}/stack", {"codes": bare_codes, "size": 2})
    _, bare_built = call("GET", f"/design-sets/{bare_set_id}")
    bare_flags = [p for m in bare_built["members"] for p in m["pairs"]]
    step("a target with no structure still produces pairs", len(bare_flags) == 3)
    step("and every one of them reads unknown, never beyond",
         all(p["proximity"] == "unknown" for p in bare_flags))
    step("each unknown pair carries the reason it could not be measured",
         all(p["reason"] and "structure" in p["reason"] for p in bare_flags))
    step("and no separation is invented for it",
         all(p["separation_angstrom"] is None for p in bare_flags))
    step("the warning counts unknown pairs separately from flagged ones",
         bare_built["warning"]["pairs_unknown"] == 3
         and bare_built["warning"]["pairs_within_cutoff"] == 0)

    section("Phase 7: a constrained position needs an explicit, recorded override")
    constrained_code = next(iter(removed))
    status, refusal = call("POST", f"/design-sets/{set_id}/members",
                           {"codes": [constrained_code]})
    step("adding a constrained design is refused", status == 400, f"HTTP {status}")
    step("and the refusal names the constraint",
         "constrained positions" in refusal["detail"]["message"],
         refusal["detail"]["message"][:60])
    status, no_reason = call("POST", f"/design-sets/{set_id}/members",
                             {"codes": [constrained_code], "override": True})
    step("an override with no stated reason is refused too", status == 400,
         no_reason["detail"]["message"][:50])
    status, overridden = call(
        "POST",
        f"/design-sets/{set_id}/members",
        {"codes": [constrained_code], "override": True,
         "override_reason": "Gate check: deliberate probe of a constrained residue."},
    )
    step("an override with a stated reason is accepted", status == 200)
    overridden_member = next(
        (m for m in overridden["members"] if m["code"] == constrained_code), None
    )
    step("the override is recorded on the design itself",
         overridden_member is not None
         and overridden_member["included_via_override"] is True
         and bool(overridden_member["override_reason"]))

    section("Phase 7: exports refuse primers while anything fabricates")
    _, preflight = call("GET", f"/design-sets/{set_id}/exports")
    step("the run is synthetic, so the export is watermarked",
         preflight["is_demo"] is True and bool(preflight["watermark"]))
    step("primers are not offered", "primers_csv" not in preflight["available"],
         ", ".join(preflight["available"]))
    primer_refusals = [r for r in preflight["refused"] if r["what"] == "primers"]
    step("and the refusal is stated rather than silent", bool(primer_refusals),
         f"{len(primer_refusals)} reason(s)")
    step("every refusal carries a remedy",
         all(r["reason"] and r["remedy"] for r in preflight["refused"]))
    step("the fabricating provider is named as a reason",
         any("fabricates" in r["reason"] for r in primer_refusals))
    status, _ = call("GET", f"/design-sets/{set_id}/exports/primers.csv")
    step("asking for primers anyway is refused, not served", status == 409,
         f"HTTP {status}")

    csv_text = fetch_html(f"{BASE}/design-sets/{set_id}/exports/design-set.csv")
    step("the design set itself still exports", "code,hgvs,kind" in csv_text)
    step("and the export carries the demo watermark", "DEMO DATA" in csv_text)
    step("and states the additivity assumption inside the file",
         "assumed additive" in csv_text)
    step("and carries no primer sequence column", "forward_primer" not in csv_text)

    section("Phase 7: the design set screen serves")
    page = fetch_html(f"{WEB}/runs/{run['id']}/design-sets/{set_id}")
    # Assert this set's own content, not that a page came back. A 200 carrying
    # an error boundary would satisfy the latter.
    step("the builder screen serves this design set", design_set["name"] in page,
         design_set["name"])
    step("its stacked designs are on the page",
         all(m["code"] in page for m in combinations[:3]),
         f"{len(combinations)} stacked")
    step("the epistasis warning is on the page", "assumed additive" in page.lower())
    step("a flagged pair is marked on the page as within the cutoff",
         "Within 8" in page)
    step("and it carries the persistent demo bar", "Demo data" in page)


    # ======================================================================= #
    # Phase 8 — results intake, the join, and the scorecard
    # ======================================================================= #

    section("Phase 8: a column mapping is offered, never assumed")
    # Rows in *full-length* numbering, against a target whose canonical scheme is
    # the mature protein. This is the real shape of the problem, not a contrived
    # one: the seeded deep mutational scan is written exactly this way.
    shifted_csv = "mutant,T50\nA32N,48.60\nE33K,47.10\nH34Y,46.56\nN35D,43.28"
    status, inspected = call(
        "POST", f"/targets/{target_id}/measurements/inspect", {"text": shifted_csv}
    )
    step("a pasted table is read", status == 200,
         f"{inspected['row_count']} rows, split on "
         f"{'tab' if inspected['delimiter'] == chr(9) else 'comma'}")
    step("a mapping is suggested for the user to confirm",
         inspected["suggested"] is not None
         and inspected["suggested"]["label"] == "mutant"
         and inspected["suggested"]["value"] == "T50")
    step("each column carries a sample so a header can be recognised",
         all(column["sample"] for column in inspected["columns"]))

    mapping = {"label": "mutant", "value": "T50", "sd": None, "replicate": None}

    section("Phase 8: a numbering shift is proposed with evidence, never applied")
    status, preview = call(
        "POST",
        f"/targets/{target_id}/measurements/preview",
        {"text": shifted_csv, "mapping": mapping, "offset": None},
    )
    step("the preview writes nothing and answers", status == 200)
    step("nothing joined, because the file is in another scheme",
         preview["joined"] == 0, f"{preview['unjoined']} unplaced")
    step("a wild-type mismatch names the residue the scheme actually has",
         any("is S in" in row["detail"] for row in preview["rows"]),
         next((row["detail"] for row in preview["rows"] if "is S in" in row["detail"]), ""))
    step("one shift is proposed", preview["offset"] is not None
         and preview["offset"]["offset"] == -31,
         f"offset {preview['offset']['offset'] if preview['offset'] else None}")
    step("and it is unanimous over every unplaced row",
         preview["offset"]["witnesses"] == preview["unjoined"],
         f"{preview['offset']['witnesses']} witnesses")
    step("the proposal is not applied by the act of proposing it",
         preview["joined"] == 0)
    step("stale variants in a superseded scheme are excluded from the join",
         "stale_variants" in preview, f"{preview['stale_variants']} excluded")

    status, accepted = call(
        "POST",
        f"/targets/{target_id}/measurements/preview",
        {"text": shifted_csv, "mapping": mapping, "offset": -31},
    )
    step("accepting the shift joins the rows it explains",
         accepted["joined"] == accepted["total_rows"],
         f"{accepted['joined']}/{accepted['total_rows']}")
    step("and the rows still read back in the notation the file used",
         all(row["raw_label"].startswith(("A32", "E33", "H34", "N35"))
             for row in accepted["rows"]))
    step("the canonical code is what they joined to",
         {row["code"] for row in accepted["rows"]} == {"A1N", "E2K", "H3Y", "N4D"},
         ", ".join(sorted(row["code"] for row in accepted["rows"])))

    section("Phase 8: a similar code is not a match")
    # `A1N` is in this run. `A1Z` is not an amino acid, and `Q1N` names a residue
    # the scheme does not have there. Neither may be quietly attributed to A1N.
    status, strict = call(
        "POST",
        f"/targets/{target_id}/measurements/preview",
        {"text": "mutant,T50\nA1N,48.6\nQ1N,47.0\nA1Z,44.0\nnot a code,41.0",
         "mapping": mapping, "offset": None},
    )
    by_label = {row["raw_label"]: row for row in strict["rows"]}
    step("an exact code joins", by_label["A1N"]["code"] == "A1N")
    step("a different wild-type residue does not join",
         by_label["Q1N"]["code"] is None
         and by_label["Q1N"]["outcome"] == "wild_type_mismatch")
    step("a non-residue letter is not a mutation code",
         by_label["A1Z"]["code"] is None)
    step("free text is reported, not silently dropped",
         by_label["not a code"]["outcome"] == "unparseable")
    step("every uploaded row comes back", strict["total_rows"] == 4)

    section("Phase 8: a row that fails to join survives the import")
    status, imported = call(
        "POST",
        f"/targets/{target_id}/measurements",
        {
            "text": shifted_csv + "\nempty well,0.0",
            "mapping": mapping,
            "assay": "thermal_stability",
            "metric": "t50_celsius",
            "unit": "°C",
            "higher_is_better": True,
            "offset": -31,
            "source_note": f"verify_gates {stamp}",
        },
        retry_safe=False,
    )
    step("the import is accepted", status == 201)
    step("every row was written, not just the ones that joined",
         imported["written"] == 5, f"{imported['written']} written")
    step("four joined and one did not",
         imported["joined"] == 4 and imported["unjoined"] == 1)

    experiment_id = imported["experiment_id"]
    status, unjoined = call("GET", f"/experiments/{experiment_id}/unjoined")
    step("the unjoined row is retrievable", status == 200 and len(unjoined) == 1)
    step("and reads back in the label the file gave it",
         unjoined[0]["raw_label"] == "empty well", unjoined[0]["raw_label"])

    section("Phase 8: an import states its own sign convention")
    status, refused = call(
        "POST",
        f"/targets/{target_id}/measurements",
        {
            "text": "mutant,T50\nA32N,48.60",
            "mapping": mapping,
            "assay": "thermal_stability",
            "metric": "t50_celsius",
            "unit": "",
            "higher_is_better": True,
            "offset": -31,
        },
        retry_safe=False,
    )
    step("an import with no unit is refused", status == 400,
         refused.get("detail", {}).get("message", ""))
    step("and the refusal says why the unit matters",
         "unlike units" in refused.get("detail", {}).get("remedy", ""))

    section("Phase 8: a rank statistic never stands alone")
    status, report = call("GET", f"/targets/{target_id}/scorecard")
    step("the scorecard answers", status == 200, f"{len(report['cards'])} card(s)")
    step("it rests on measured values joined to variants",
         report["measured_variants"] >= 1)
    card = next((c for c in report["cards"] if c["measured_metric"] == "t50_celsius"), None)
    step("a card exists for the imported metric", card is not None)
    step("the rank statistic is reported over more than one variant",
         card["spearman"] is not None and card["n"] >= 4,
         f"n={card['n']}, rho={card['spearman']:.4f}" if card["spearman"] is not None else "none")
    # The important one. A ddG in kcal/mol and a T50 in degrees Celsius are not
    # the same quantity, so no absolute error between them is computed, and the
    # reason travels with the card rather than leaving a blank.
    step("no error term is invented across unlike units", card["mae"] is None)
    step("and no bias term either", card["mean_signed_error"] is None)
    step("the reason is on the card, not absent",
         len(card["error_unavailable_reason"]) > 0)
    step("and it names both units",
         card["predicted_unit"] in card["error_unavailable_reason"]
         and card["measured_unit"] in card["error_unavailable_reason"],
         card["error_unavailable_reason"][:80])
    step("no calibration curve is drawn across unlike units",
         card["calibration"] == [])
    step("the card names the weights its numbers came from",
         len(card["weights_hash"]) > 0)
    step("a synthetic predictor's card says so", card["is_mock"] is True)

    section("Phase 8: where the units do match, error and bias are reported")
    # The same predictor's own metric and unit, so the two series are genuinely
    # commensurable. This is the path the unit gate exists to permit.
    ddg_rows = "\n".join(
        f"{row['code']},{row['cells'][0]['value'] + 2.0:.4f}"
        for row in ranking["rows"][:24]
        if row["cells"] and row["cells"][0]["metric"] == "ddg_kcal_per_mol"
    )
    if ddg_rows:
        status, commensurable = call(
            "POST",
            f"/targets/{target_id}/measurements",
            {
                "text": "mutant,ddg\n" + ddg_rows,
                "mapping": {"label": "mutant", "value": "ddg", "sd": None, "replicate": None},
                "assay": "thermal_stability",
                "metric": "ddg_kcal_per_mol",
                "unit": "kcal/mol",
                "higher_is_better": False,
                "offset": None,
                "source_note": f"verify_gates {stamp}: synthetic, +2.00 kcal/mol by construction",
            },
            retry_safe=False,
        )
        step("commensurable measurements import", status == 201,
             f"{commensurable['joined']} joined")

        _, report2 = call("GET", f"/targets/{target_id}/scorecard")
        ddg_card = next(
            (c for c in report2["cards"]
             if c["measured_metric"] == "ddg_kcal_per_mol"
             and c["predicted_metric"] == "ddg_kcal_per_mol"),
            None,
        )
        step("a card exists for the matching unit", ddg_card is not None)
        step("MAE is reported in the shared unit",
             ddg_card["mae"] is not None and ddg_card["error_unit"] == "kcal/mol",
             f"MAE {ddg_card['mae']:.2f} kcal/mol")
        step("the bias term is reported beside it",
             ddg_card["mean_signed_error"] is not None,
             f"bias {ddg_card['mean_signed_error']:+.2f} kcal/mol")
        # The claim ARCHITECTURE.md §13 rests on, asserted end to end: a series
        # offset by a constant scores a perfect rank and is caught only by bias.
        step("a constant offset is invisible to rank",
             abs(ddg_card["spearman"] - 1.0) < 1e-9,
             f"rho {ddg_card['spearman']:.4f}")
        step("and is caught exactly by the bias term",
             abs(ddg_card["mean_signed_error"] + 2.0) < 0.01,
             f"{ddg_card['mean_signed_error']:+.4f} kcal/mol against a built-in -2.00")
        step("the bias states its own sign convention",
             "Predicted minus measured" in ddg_card["bias_note"])
        step("a calibration curve is drawn when the units match",
             len(ddg_card["calibration"]) > 0,
             f"{len(ddg_card['calibration'])} bins")

    section("Phase 8: the seeded deep mutational scan is real and joined")
    _, projects = call("GET", "/projects")
    seeded = next(
        (p for p in projects if p["name"] == "Lipase A thermostability, measured"), None
    )
    step("the seeded validation-loop project exists", seeded is not None)
    if seeded is not None:
        _, experiments = call("GET", f"/projects/{seeded['id']}/experiments")
        step("it carries one imported experiment", len(experiments) == 1)
        dms = experiments[0]
        step("with the whole deep mutational scan", dms["total"] == 2172,
             f"{dms['total']} measured values")
        step("every row joined to a variant", dms["unjoined"] == 0,
             f"{dms['joined']} joined")
        step("the values are temperatures, and say so", dms["unit"] == "°C")
        step("the direction was stated, not inferred", dms["higher_is_better"] is True)
        step("and the source is cited", "10.1021/acs.jcim.9b00954" in (dms["source_note"] or ""),
             (dms["source_note"] or "")[:60])

    section("Phase 8: the scorecard screen serves")
    page = fetch_html(f"{WEB}/targets/{target_id}/scorecard")
    step("the scorecard screen serves this target", "Predictor scorecard" in page)
    step("the rank statistic is on the page", "Spearman" in page)
    # ARCHITECTURE.md §13: the bias term is adjacent to the rank term, never in a
    # detail panel or behind a tab. If it is on the page at all it is in the row.
    step("the bias term is on the page beside it", "Mean signed error" in page)
    step("the error term is on the page", "MAE" in page)
    step("an uncomputable error explains itself on the page",
         "not the same quantity" in page)
    step("and says what a rank statistic alone does not establish",
         "not whether the numbers are" in page)

    section("Phase 8: the intake screen serves")
    page = fetch_html(f"{WEB}/targets/{target_id}/measurements")
    step("the intake screen serves", "Import measured results" in page)
    step("it says nothing is written until the preview is confirmed",
         "Nothing is written until" in page)

    section("Phase 8: a variant in a superseded scheme cannot take a measurement")
    # Deliberately last, because it changes this target's canonical scheme.
    #
    # A target keeps the variant rows an earlier scheme produced — they have
    # scores hanging off them, so nothing deletes them — and under a new scheme
    # those rows name residues the target no longer agrees with. Joining an
    # upload to one would file a bench measurement against the wrong residue,
    # which HANDOFF.md §8 records as the most expensive error class here. This
    # asserts the join excludes them, by creating the condition rather than
    # assuming it never arises: every variant so far is written in the mature
    # scheme, so confirming the full-length scheme makes all of them stale.
    _, target = call("GET", f"/targets/{target_id}")
    full_length = next(
        s for s in target["numbering_schemes"] if s["kind"] == "sequence"
    )
    status, reschemed = call(
        "POST", f"/targets/{target_id}/numbering/confirm", {"scheme_id": full_length["id"]}
    )
    step("the canonical scheme can be changed", status == 200
         and reschemed["canonical_scheme_label"] == full_length["label"],
         reschemed["canonical_scheme_label"])

    status, after = call(
        "POST",
        f"/targets/{target_id}/measurements/preview",
        # `S77A` was a legitimate code a moment ago. Under the full-length
        # scheme, position 77 is not S, so it must no longer join to anything.
        {"text": "mutant,T50\nS77A,48.6", "mapping": mapping, "offset": None},
    )
    step("variants written in the superseded scheme are excluded",
         after["stale_variants"] > 0, f"{after['stale_variants']} excluded")
    step("a code that was valid under the old scheme no longer joins",
         after["joined"] == 0, after["rows"][0]["detail"])
    # Either refusal is correct and which one depends on whether any variant
    # survived the exclusion at that label: `wild_type_mismatch` when one did,
    # `unknown_position` when none did. What must hold is that the message names
    # the scheme it is refusing under, so the reader can see *which* numbering
    # made the code wrong.
    step("and the refusal names the scheme it refused under",
         after["rows"][0]["outcome"] in {"wild_type_mismatch", "unknown_position"}
         and reschemed["canonical_scheme_label"] in after["rows"][0]["detail"],
         after["rows"][0]["outcome"])


    # ======================================================================= #
    # Phase 9 — accessibility, and the boundary the landing page must not cross
    # ======================================================================= #
    #
    # What this section can and cannot see is worth stating, because the
    # difference is where the rest of Phase 9's evidence lives.
    #
    # It reads **served HTML**. That covers document language, heading
    # structure, landmark naming, and whether a marketing pattern has leaked
    # into an application screen — all of which are server-rendered and all of
    # which a screen reader meets first.
    #
    # It cannot see the command palette or the shortcut sheet: both are client
    # components inside `Shell`, so they exist only after hydration. Their
    # behaviour is asserted in `apps/web/test/keyboard.test.tsx`, which drives
    # them with `userEvent.keyboard` and never a click. Nor can it see focus
    # rings or contrast — `contrast.test.ts` recomputes every ratio from
    # `tokens.css` on each build. Nor trusted clicks, which is what the
    # Playwright flows in `apps/web/e2e` exist for.

    section("Phase 9: every screen is navigable before any script runs")
    a11y_screens = [
        ("landing", f"{WEB}/"),
        ("projects", f"{WEB}/projects"),
        ("target", f"{WEB}/targets/{target_id}"),
        ("constraints", f"{WEB}/targets/{target_id}/constraints"),
        ("goal composer", f"{WEB}/targets/{target_id}/goal"),
        ("run view", f"{WEB}/runs/{run['id']}"),
        ("workbench", f"{WEB}/runs/{run['id']}/workbench"),
        ("results intake", f"{WEB}/targets/{target_id}/measurements"),
        ("scorecard", f"{WEB}/targets/{target_id}/scorecard"),
    ]
    pages = {name: fetch_html(url) for name, url in a11y_screens}

    step("every screen declares its language",
         all('lang="en"' in page for page in pages.values()),
         f"{len(pages)} screens")

    # Exactly one <h1>, counting only what assistive technology can reach.
    #
    # A streamed route serves **two** copies of itself: the `loading.tsx`
    # skeleton, visible inside the Suspense fallback, and the real page in a
    # `<div hidden id="S:1">` that client script swaps in. Both carry an `<h1>`,
    # by design — DESIGN.md §5 requires the skeleton to match the final
    # geometry — so a naive count reports two headings on every streamed screen
    # and the browser shows one.
    #
    # Hidden subtrees are what AT ignores, so they are what is stripped. Two
    # details cost time and are worth writing down: the attribute order is
    # `hidden id="S:1"`, not the other way round, so the match cannot assume
    # one; and a non-greedy `.*?</div>` stops at the first closing tag inside
    # the subtree rather than the matching one, so the close is found by
    # counting nested opens. The count is not loosened to "at least one" —
    # that would pass a page with a genuine duplicate.
    def strip_hidden(page: str) -> str:
        out = page
        while True:
            match = re.search(r"<div[^>]*\bhidden\b[^>]*>", out)
            if match is None:
                return out
            depth, index = 1, match.end()
            while depth and index < len(out):
                nxt = re.search(r"<div\b|</div>", out[index:])
                if nxt is None:
                    index = len(out)
                    break
                depth += 1 if nxt.group(0) == "<div" else -1
                index += nxt.end()
            out = out[: match.start()] + out[index:]

    def visible_h1_count(page: str) -> int:
        return len(re.findall(r"<h1[\s>]", strip_hidden(page)))

    wrong = {name: visible_h1_count(page) for name, page in pages.items()
             if visible_h1_count(page) != 1}
    step("each screen has exactly one top-level heading", not wrong, str(wrong) if wrong else "")

    step("the primary navigation is named",
         all('aria-label="Primary"' in page for name, page in pages.items() if name != "landing"))

    section("Phase 9: no marketing pattern reached the application")
    # BRIEF.md §4 bans a marketing hero *inside the app*, and §10's last clause
    # is that the app looks like it was made by a design team that has never
    # heard of a landing page. A landing page then shipped, at the owner's
    # request, so the boundary is now something to keep rather than something
    # that holds by absence. `Shell` is the boundary; these assert it held.
    app_pages = {name: page for name, page in pages.items() if name != "landing"}

    step("the landing page is outside the application chrome",
         'aria-label="Primary"' not in pages["landing"],
         "no rail on /")
    step("and every application screen is inside it",
         all('aria-label="Primary"' in page for page in app_pages.values()),
         f"{len(app_pages)} screens")

    # The display type sizes exist for the landing page only. tokens.test.ts
    # fails the build if they appear outside components/landing; this is the
    # same claim checked against what is actually served.
    display_leaks = {
        name: size
        for name, page in app_pages.items()
        for size in ("text-32", "text-44", "text-56")
        if re.search(rf'class="[^"]*\b{size}\b', page)
    }
    step("no display type size is served on an application screen",
         not display_leaks, str(display_leaks) if display_leaks else "32/44/56 confined to /")

    step("no application screen carries the landing hero copy",
         not any("Every number traces back to the model that made it" in page
                 for page in app_pages.values()))

    banned = ("bg-gradient-", "backdrop-blur", "rounded-3xl")
    found = {name: token for name, page in app_pages.items() for token in banned if token in page}
    step("no banned decorative device is served", not found, str(found) if found else "")

    section("Phase 9: the demo bar survives on every application screen")
    # Specification §6 requires the persistent bar wherever a fabricating
    # provider is active. Phase 4 asserted it on two screens; Phase 9 asserts it
    # on all of them, because that is the claim — and because the landing page
    # having no bar is correct only if it also has no numbers.
    step("every application screen carries the demo bar",
         all("Demo data" in page for page in app_pages.values()),
         f"{len(app_pages)} screens")
    step("the landing page has no demo bar, and no scores to need one",
         "Demo data" not in pages["landing"])

    section("Phase 9: the Playwright smoke flows are present and runnable")
    # The gate does not execute them — they need a browser binary and they are
    # a separate command (`pnpm --filter @codonlab/web e2e`). What it asserts is
    # that they exist and are wired, so "we have smoke flows" cannot become
    # untrue silently.
    e2e_dir = os.path.join(REPO_ROOT, "apps", "web", "e2e")
    specs = sorted(f for f in os.listdir(e2e_dir)) if os.path.isdir(e2e_dir) else []
    step("the smoke flows exist", len([f for f in specs if f.endswith(".spec.ts")]) >= 3,
         ", ".join(specs))
    config = os.path.join(os.path.dirname(e2e_dir), "playwright.config.ts")
    step("and a Playwright config points at them", os.path.isfile(config))

    section("Phase 9: the landing page's claims about the build are still true")
    # The landing page publishes a gate count. It was written by hand and it
    # went stale the moment Phase 9 added checks — it read 225 against a suite
    # of 237, which is a false claim on the most public surface in the product.
    #
    # So it is checked against the suite that is running. This step counts
    # itself, hence the +1: the number on the page is what the run will total.
    # A hand-maintained number on a public page drifts; one the gate asserts
    # cannot drift without going red.
    claimed = re.search(r'<Stat value="([\d,]+)" label="automated gate checks',
                        read_repo_file("apps", "web", "components", "landing", "landing.tsx"))
    total = checks + 1
    step("the published gate count matches the suite",
         claimed is not None and int(claimed.group(1).replace(",", "")) == total,
         f"page says {claimed.group(1) if claimed else 'nothing'}, suite runs {total}")

    print()
    if failures:
        print(f"{failures} gate check(s) FAILED.")
        return 1
    print("All phase gate checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
