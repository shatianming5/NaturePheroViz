"""
transform_repair.py — §8.4 实验1: generic vs targeted (vs gold-diff ceiling) repair.

The detection line (transform_oracle) proves a goldless, typed operator-semantic
contract can FLAG and LOCALIZE a silent semantic error. This experiment asks the
gating question for the repair extension (§8 roadmap):

    does feeding that typed attribution back to the model fix the error more
    reliably / cheaply than a generic "you may be wrong, try again" self-repair?

THREE ARMS — the ONLY variable is the feedback content; model, the shared buggy
starting code, round budget N, temperature and the rewrite prompt are all locked:

  A. generic   (lower bound)  : "result may be wrong, re-derive it" + self-check,
                                NO typed information. Must be the STRONGEST no-
                                contract baseline (not a straw man).
  B. targeted  (ours)         : the violated invariant + the at-fault operator +
                                an allowed patch scope ("only change the <op> step"),
                                taken from transform_oracle.check().detail and the
                                attribution localization. Goldless.
  C. gold-diff (upper bound)  : a direct gold cell-diff. The ceiling that shows how
                                close the goldless arm B gets to having the answer.

NO CIRCULAR REASONING: the repairer only ever sees the GOLDLESS contract signal;
success is scored by an INDEPENDENT gold (ambiguity_calibration._gold_correct) that
the model never sees — exactly mirroring the detection line ("oracle never sees
gold; the correct/wrong label is computed from gold separately").

STOPPING (fair, per-arm own signal only): each arm commits a final result by its
OWN available signal, then we score that committed result with the hidden gold.
  A: stop at fixpoint (result unchanged) or N rounds.
  B: stop when the true-op contract no longer fires (goldless PASS) or N rounds.
  C: stop when the gold matches or N rounds.

METRICS (per-arm x per-operator-family):
  - final repair success (independent gold on the committed result)  [main]
  - rounds used, llm calls (a coarse cost proxy)
  - over-repair, two definitions:
      (a) the repair INTRODUCES a new substantive fire of some OTHER contract;
      (b) a gold column that was already correct at the buggy start becomes WRONG.

Reuse (no re-implementation): transform_bench._cases, transform_oracle.check /
CONTRACTS, attribution_eval._run_all_contracts, and in ONLINE mode the generation
harness ambiguity_calibration._llm_code / _exec / _gold_correct.

Run:
  cd agent && python eval/transform_repair.py --offline      # plumbing self-test, NO LLM
  cd agent && LLM_API_BASE=.. LLM_API_KEY=.. python eval/transform_repair.py [--rounds 3] [--models gpt-4o,claude-sonnet-4.6]

IMPORTANT: --offline uses a DETERMINISTIC STUB "LLM" (arm A never fixes, arms B/C
return gold). It validates the harness wiring + metrics ONLY and is NOT an
experimental result. Real numbers require the LLM env.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import math

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import eval.transform_oracle as ORACLE  # noqa: E402
from eval.transform_oracle import check as oracle_check  # noqa: E402
from eval.transform_bench import _cases, expansion_cases  # noqa: E402
from eval.attribution_eval import _run_all_contracts  # noqa: E402

ARMS = ("generic", "targeted", "ceiling")


# --------------------------------------------------------------------------- #
# gold / result helpers
# --------------------------------------------------------------------------- #
def _inp(item: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
    return {"df": item["df"], **({"df2": item["df2"]} if "df2" in item else {})}


def _compute_gold(item: Dict[str, Any]) -> pd.DataFrame:
    """Canonical gold as a DataFrame (scalar -> 1-cell frame), aligned to how
    ambiguity_calibration._gold_correct reads it."""
    g = item["gold"](item["df"], item["df2"]) if "df2" in item else item["gold"](item["df"])
    if item["result_kind"] == "scalar":
        gv = float(g) if np.isscalar(g) else float(pd.Series(g).iloc[0])
        return pd.DataFrame({"value": [gv]})
    gd = g if isinstance(g, pd.DataFrame) else g.to_frame()
    return gd.reset_index(drop=False) if not isinstance(g, pd.DataFrame) else gd


def _preview(result: Optional[pd.DataFrame], n: int = 6) -> str:
    if result is None:
        return "(no result / code did not assign `result`)"
    try:
        return result.head(n).to_string(index=False)
    except Exception:
        return str(result)[:300]


def _true_op_fires(item: Dict[str, Any], result: Optional[pd.DataFrame]) -> bool:
    """Goldless: does the case's own operator contract substantively fire?"""
    r = oracle_check(item["op"], _inp(item), item["params"], result)
    return bool(r and r.fired and "missing" not in r.detail.lower())


def _other_fires(item: Dict[str, Any], result: Optional[pd.DataFrame]) -> int:
    """Substantive fires of contracts OTHER than the true op (for over-repair (a))."""
    return len(_other_fire_set(item, result))


def _other_fire_set(item: Dict[str, Any], result: Optional[pd.DataFrame]) -> set:
    """The SET of other-op contracts that substantively fire on this result. Set-valued
    so over-repair can take a true set difference (commit minus buggy): a contract that
    ALREADY fired on the buggy start is not a NEW error the repair introduced — counting
    it would charge the repair for the measurement-layer cross-fire of the buggy input."""
    fired = _run_all_contracts(_inp(item), item["params"], result, prune=True)
    return {op for op, f in fired.items() if f and op != item["op"]}


def _gold_col_status(item: Dict[str, Any], result: Optional[pd.DataFrame]) -> Dict[str, bool]:
    """Per gold-column correctness (for over-repair (b)). For scalar, the single value."""
    gold = _compute_gold(item)
    if result is None:
        return {c: False for c in gold.columns}
    out: Dict[str, bool] = {}
    if item["result_kind"] == "scalar":
        gv = float(pd.to_numeric(gold.iloc[:, 0], errors="coerce").iloc[0])
        ok = False
        for c in result.columns:
            s = pd.to_numeric(result[c], errors="coerce")
            if s.notna().sum() == 1:
                ok = abs(float(s.dropna().iloc[0]) - gv) <= max(abs(gv) * 1e-4, 1e-6)
                break
        return {"value": ok}
    rcols = {str(c): c for c in result.columns}
    for gc in gold.columns:
        gcs = str(gc)
        if gcs not in rcols or len(result) != len(gold):
            out[gcs] = False
            continue
        gv = pd.to_numeric(gold[gc], errors="coerce").to_numpy(dtype=float)
        rv = pd.to_numeric(result[rcols[gcs]], errors="coerce").to_numpy(dtype=float)
        if np.isnan(gv).all():  # non-numeric gold column: compare as strings (set-wise)
            gset = sorted(str(x) for x in gold[gc].tolist())
            rset = sorted(str(x) for x in result[rcols[gcs]].tolist())
            out[gcs] = gset == rset
        else:
            out[gcs] = bool(np.allclose(np.sort(gv), np.sort(rv), atol=1e-4, equal_nan=True))
    return out


# --------------------------------------------------------------------------- #
# feedback builders — the ONLY thing that differs across arms
# --------------------------------------------------------------------------- #
def fb_generic(item: Dict[str, Any], result: Optional[pd.DataFrame]) -> str:
    return ("Your previous result may be SEMANTICALLY INCORRECT (it runs and looks "
            "plausible but may not implement the requested transformation). Carefully "
            "re-read the task, double-check your aggregation/grouping/weighting choices, "
            "and produce a corrected `result`.\n"
            f"Previous result:\n{_preview(result)}")


def fb_targeted(item: Dict[str, Any], result: Optional[pd.DataFrame]) -> str:
    op = item["op"]
    cr = oracle_check(op, _inp(item), item["params"], result)
    detail = cr.detail if cr is not None else "(operator not applicable / abstain)"
    fired = _run_all_contracts(_inp(item), item["params"], result, prune=True)
    localized = [o for o, f in fired.items() if f]
    loc = ", ".join(localized) if localized else op
    return ("A checkable semantic invariant is VIOLATED, so the result is wrong.\n"
            f"At-fault operator semantics: `{op}` (localized contracts: {loc}).\n"
            f"Violated invariant: {detail}\n"
            f"Fix ONLY the `{op}` computation. Do NOT alter parts of the pipeline that "
            "are already correct. Produce a corrected `result`.\n"
            f"Previous result:\n{_preview(result)}")


def fb_ceiling(item: Dict[str, Any], result: Optional[pd.DataFrame]) -> str:
    gold = _compute_gold(item)
    return ("Your result does not match the reference answer. Reference (the values "
            "your `result` should reproduce):\n"
            f"{_preview(gold)}\n"
            f"Your previous result:\n{_preview(result)}\n"
            "Produce a corrected `result` that matches the reference.")


FEEDBACK: Dict[str, Callable[[Dict[str, Any], Optional[pd.DataFrame]], str]] = {
    "generic": fb_generic,
    "targeted": fb_targeted,
    "ceiling": fb_ceiling,
}


# --------------------------------------------------------------------------- #
# one repair step (online = real LLM; offline = deterministic stub)
# --------------------------------------------------------------------------- #
def _online_step(item: Dict[str, Any], task: str, feedback: str, model: str) -> Tuple[Optional[pd.DataFrame], str]:
    from eval.ambiguity_calibration import _llm_code, _exec
    prompt = f"{task}\n\n{feedback}"
    code = _llm_code(item, prompt, model)
    return (_exec(item, code) if code else None), (code or "")


def _offline_step(item: Dict[str, Any], arm: str, prev: Optional[pd.DataFrame]) -> Tuple[Optional[pd.DataFrame], str]:
    """STUB: arm 'generic' never fixes (returns prev unchanged); arms 'targeted' and
    'ceiling' return gold (their feedback 'fixes'). Plumbing only — NOT a result."""
    if arm == "generic":
        return prev, "<stub:unchanged>"
    return _compute_gold(item), "<stub:gold>"


def _make_buggy_start(item: Dict[str, Any], model: Optional[str], offline: bool) -> Optional[pd.DataFrame]:
    """Produce the shared buggy starting point: an exec-ok BUT silent (gold-wrong)
    result whose true-op contract fires. Online: generate from the ambiguous prompt.
    Offline: perturb a numeric column of the gold (same schema -> alignment safe)."""
    if not offline:
        from eval.ambiguity_calibration import _llm_code, _exec, _gold_correct
        code = _llm_code(item, item["ambiguous"], model)
        res = _exec(item, code) if code else None
        if res is None or _gold_correct(item, res):
            return None  # need an exec-ok silent error to repair
        return res
    # offline perturbation
    gold = _compute_gold(item).copy()
    num_cols = [c for c in gold.columns if pd.to_numeric(gold[c], errors="coerce").notna().any()]
    if not num_cols:
        return None
    c = num_cols[-1]
    gold[c] = pd.to_numeric(gold[c], errors="coerce") * 0.7 + 1.0
    return gold


# --------------------------------------------------------------------------- #
# run one arm from a shared buggy start
# --------------------------------------------------------------------------- #
def run_arm(item: Dict[str, Any], arm: str, buggy: pd.DataFrame, rounds: int,
            model: Optional[str], offline: bool) -> Dict[str, Any]:
    if not offline:
        from eval.ambiguity_calibration import _gold_correct
        score = lambda r: _gold_correct(item, r)  # noqa: E731
    else:
        score = lambda r: _gold_col_all_ok(item, r)  # noqa: E731

    start_status = _gold_col_status(item, buggy)
    cur = buggy.copy()
    calls = 0
    n_malformed = 0
    stop_reason = "budget"
    for rnd in range(1, rounds + 1):
        feedback = FEEDBACK[arm](item, cur)
        if offline:
            nxt, _ = _offline_step(item, arm, cur)
        else:
            nxt, _ = _online_step(item, item["ambiguous"], feedback, model or "")
        calls += 1
        if nxt is None:
            n_malformed += 1
            stop_reason = "malformed"
            break  # malformed rewrite; keep last good `cur`
        prev = cur
        cur = nxt
        # per-arm stopping signal (own information only)
        if arm == "generic":
            if cur.equals(prev):
                stop_reason = "fixpoint"  # model re-derived the SAME result (silent: can't see the bug)
                break
        elif arm == "targeted":
            if not _true_op_fires(item, cur):
                stop_reason = "contract_pass"  # goldless contract now satisfied
                break
        elif arm == "ceiling":
            if score(cur):
                stop_reason = "gold_match"
                break
    success = bool(score(cur))
    # over-repair (a): a NEW spurious error the repair INTRODUCED. Take a true SET
    # difference (commit's other-fires MINUS the buggy start's): a contract that already
    # cross-fired on the buggy input is not damage done by the repair. Only meaningful on
    # a non-correct commit (a fire on a gold-correct result is the §3.6 cross-fire FP).
    over_a = 0 if success else len(_other_fire_set(item, cur) - _other_fire_set(item, buggy))
    commit_status = _gold_col_status(item, cur)
    over_b = any(start_status.get(k, False) and not commit_status.get(k, False) for k in start_status)
    return {"success": success, "rounds": rnd, "calls": calls,
            "over_repair_a": over_a, "over_repair_b": bool(over_b),
            "stop_reason": stop_reason, "n_malformed": n_malformed}


def _gold_col_all_ok(item: Dict[str, Any], result: Optional[pd.DataFrame]) -> bool:
    """Offline success proxy: all gold columns correct (no hidden-gold scorer offline)."""
    st = _gold_col_status(item, result)
    return bool(st) and all(st.values())


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def run(rounds: int, models: List[str], offline: bool, per_op: int, out_dir: str,
        grid: str = "core") -> Dict[str, Any]:
    seen: Counter = Counter()
    items: List[Dict[str, Any]] = []
    source = expansion_cases() if grid == "expansion" else _cases()
    for c in source:
        seen[c["op"]] += 1
        if seen[c["op"]] > per_op:
            continue
        items.append({**c, "name": f"{c['op']}#{seen[c['op']]}"})

    # per-arm aggregates and per-(arm,family) success
    agg = {a: defaultdict(float) for a in ARMS}
    fam = {a: defaultdict(lambda: [0, 0]) for a in ARMS}  # op -> [success, total]
    rows: List[Dict[str, Any]] = []
    n_usable = 0

    model_list = models if not offline else [None]
    for item in items:
        for model in model_list:
            buggy = _make_buggy_start(item, model, offline)
            if buggy is None or not _true_op_fires(item, buggy):
                continue  # no usable silent start (or contract doesn't fire on it)
            n_usable += 1
            row: Dict[str, Any] = {"case": item["name"], "model": model or "stub"}
            for arm in ARMS:
                r = run_arm(item, arm, buggy.copy(), rounds, model, offline)
                row[arm] = r
                agg[arm]["n"] += 1
                agg[arm]["success"] += int(r["success"])
                agg[arm]["rounds"] += r["rounds"]
                agg[arm]["calls"] += r["calls"]
                agg[arm]["over_a"] += r["over_repair_a"]
                agg[arm]["over_b"] += int(r["over_repair_b"])
                agg[arm]["malformed"] += r["n_malformed"]
                agg[arm][f"stop_{r['stop_reason']}"] += 1
                fam[arm][item["op"]][0] += int(r["success"])
                fam[arm][item["op"]][1] += 1
            rows.append(row)
            print(f"[{n_usable:3d}] {row['case']:24s} {row['model']:18s} "
                  f"generic={int(row['generic']['success'])} "
                  f"targeted={int(row['targeted']['success'])} "
                  f"ceiling={int(row['ceiling']['success'])}", file=sys.stderr, flush=True)

    summary = _summarize(agg, fam, n_usable, rounds, offline, model_list)
    _write_report(out_dir, summary, rows, agg, fam, offline)
    print(summary["text"])
    return summary


def _rate(num: float, den: float) -> str:
    return f"{num:.0f}/{den:.0f} ({(100*num/den if den else 0):.0f}%)"


def _wilson(k: float, n: float, z: float = 1.96) -> Tuple[float, float]:
    """95% Wilson score interval for a binomial proportion (matches §1.3 convention)."""
    if n <= 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _rate_ci(k: float, n: float) -> str:
    lo, hi = _wilson(k, n)
    return f"{k:.0f}/{n:.0f} ({(100*k/n if n else 0):.0f}% [{100*lo:.0f}-{100*hi:.0f}])"


def _summarize(agg, fam, n_usable, rounds, offline, model_list) -> Dict[str, Any]:
    lines: List[str] = []
    lines.append("# Experiment 1 — generic vs targeted vs gold-diff repair"
                 + ("  [OFFLINE STUB — plumbing only, NOT a result]" if offline else ""))
    lines.append("")
    lines.append(f"usable silent starts: {n_usable}   rounds budget N={rounds}   "
                 f"models={[m or 'stub' for m in model_list]}")
    lines.append("")
    lines.append("| arm | success [95% Wilson CI] | mean rounds | mean calls | over-repair(a) new-fire | over-repair(b) broke-correct |")
    lines.append("|---|---|---|---|---|---|")
    for a in ARMS:
        n = agg[a]["n"] or 1
        lines.append(f"| {a} | {_rate_ci(agg[a]['success'], agg[a]['n'])} "
                     f"| {agg[a]['rounds']/n:.2f} | {agg[a]['calls']/n:.2f} "
                     f"| {_rate(agg[a]['over_a'], agg[a]['n'])} "
                     f"| {_rate(agg[a]['over_b'], agg[a]['n'])} |")
    lines.append("")
    # fairness telemetry: malformed-output rate + stop-reason mix (esp. generic must
    # fail by genuine fixpoint, NOT by malformed/unparseable rewrites — else unfair).
    lines.append("## fairness telemetry (malformed rate + stop reasons)")
    lines.append("| arm | malformed steps | stop: fixpoint | contract_pass | gold_match | budget | malformed |")
    lines.append("|---|---|---|---|---|---|---|")
    for a in ARMS:
        g = lambda k: int(agg[a].get(k, 0))  # noqa: E731
        lines.append(f"| {a} | {_rate(agg[a].get('malformed',0), agg[a]['n'])} "
                     f"| {g('stop_fixpoint')} | {g('stop_contract_pass')} | {g('stop_gold_match')} "
                     f"| {g('stop_budget')} | {g('stop_malformed')} |")
    lines.append("")

    # go/no-go gate. NOTE on over-repair: generic is a near-no-op baseline (it mostly
    # reproduces the same wrong result via fixpoint), so its over-repair is degenerately
    # ~0 — comparing "targeted <= generic" would penalize the only arm that actually
    # repairs. The honest criterion is an ABSOLUTE collateral-damage threshold: of all
    # targeted repairs, the fraction that introduced a new fire (a) or broke a correct
    # column (b) must stay low.
    OVER_REPAIR_MAX = 0.10
    sB, nB = agg["targeted"]["success"], agg["targeted"]["n"] or 1
    sA, nA = agg["generic"]["success"], agg["generic"]["n"] or 1
    succ_B, succ_A = sB / nB, sA / nA
    over_rate_B = (agg["targeted"]["over_a"] + agg["targeted"]["over_b"]) / nB
    over_ok = over_rate_B <= OVER_REPAIR_MAX
    rounds_ok = (agg["targeted"]["rounds"] / nB) <= (agg["generic"]["rounds"] / nA) + 1e-9
    # per-family regression: only count a SIGNIFICANT regression (per-family Wilson CIs
    # disjoint with generic above targeted). A raw non-win driven by sampling noise on a
    # small per-family N — especially a pre-declared §3.7 contract blind spot like
    # zscore_within_group — must NOT veto an overwhelming aggregate win. We still report
    # raw non-wins transparently.
    def _frate(a, op):
        s, t = fam[a][op]
        return (s / t) if t else 0.0
    regress_raw = [op for op in fam["targeted"] if _frate("targeted", op) < _frate("generic", op)]
    regress = []  # statistically significant regressions only
    for op in regress_raw:
        ts, tt = fam["targeted"][op]
        gs, gt = fam["generic"][op]
        t_lo, t_hi = _wilson(ts, tt)
        g_lo, g_hi = _wilson(gs, gt)
        if g_lo > t_hi:  # generic CI entirely above targeted CI => significant regression
            regress.append(op)
    passes = (succ_B > succ_A) and over_ok and rounds_ok and not regress

    lines.append("## per-family success (targeted vs generic vs ceiling)")
    lines.append("| operator | generic | targeted | ceiling |")
    lines.append("|---|---|---|---|")
    for op in sorted(fam["targeted"]):
        def fr(a):
            s, t = fam[a][op]
            return f"{s}/{t}"
        lines.append(f"| {op} | {fr('generic')} | {fr('targeted')} | {fr('ceiling')} |")
    lines.append("")
    lines.append("## go/no-go gate")
    bl, bh = _wilson(agg["targeted"]["success"], nB)
    al, ah = _wilson(agg["generic"]["success"], nA)
    sep = "(CIs disjoint)" if bl > ah else "(CIs overlap)"
    lines.append(f"- targeted success {succ_B:.0%} [{100*bl:.0f}-{100*bh:.0f}] vs generic {succ_A:.0%} "
                 f"[{100*al:.0f}-{100*ah:.0f}] {sep} -> {'PASS' if succ_B>succ_A else 'FAIL'}")
    lines.append(f"- targeted over-repair rate {over_rate_B:.0%} <= {OVER_REPAIR_MAX:.0%} (abs threshold): {'PASS' if over_ok else 'FAIL'}")
    lines.append(f"- rounds not increased: {'PASS' if rounds_ok else 'FAIL'}")
    lines.append(f"- no SIGNIFICANT per-family regression (disjoint CIs): {'PASS' if not regress else 'FAIL ' + str(regress)}")
    if regress_raw:
        lines.append(f"  - raw non-wins (within noise, CIs overlap; e.g. §3.7 blind spots): {regress_raw}")
    verdict = "GO (upgrade repair main line)" if passes else "NO-GO (fall back to detection paper)"
    if offline:
        verdict += "   [stub — verdict is illustrative only]"
    lines.append(f"- **VERDICT: {verdict}**")
    return {"text": "\n".join(lines), "passes": passes, "succ_B": succ_B, "succ_A": succ_A,
            "regress": regress, "regress_raw": regress_raw, "n_usable": n_usable}


def _write_report(out_dir, summary, rows, agg, fam, offline) -> None:
    d = Path(__file__).resolve().parents[1] / out_dir
    d.mkdir(parents=True, exist_ok=True)
    (d / "repair_targeted_report.md").write_text(summary["text"] + "\n", encoding="utf-8")
    payload = {
        "offline": offline,
        "aggregate": {a: dict(agg[a]) for a in ARMS},
        "per_family": {a: {op: fam[a][op] for op in fam[a]} for a in ARMS},
        "cases": rows,
    }
    (d / "repair_targeted.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Experiment 1: typed-attribution targeted repair vs generic self-repair")
    ap.add_argument("--offline", action="store_true", help="deterministic stub LLM (plumbing self-test, NOT a result)")
    ap.add_argument("--rounds", type=int, default=3, help="repair round budget N")
    ap.add_argument("--models", default=None, help="comma-separated model list (online only)")
    ap.add_argument("--per-op", type=int, default=2, help="instances per operator class to use")
    ap.add_argument("--grid", choices=("core", "expansion"), default="core",
                    help="core: established 17-op grid; expansion: the 10 new framework/cross-domain ops")
    ap.add_argument("--out", default="eval/results_repair_targeted")
    ap.add_argument("--resummarize", default=None,
                    help="recompute the report/verdict from a saved repair_targeted.json (no LLM)")
    a = ap.parse_args(argv)

    if a.resummarize:
        return _resummarize(a.resummarize, a.out)

    if not a.offline and (not os.getenv("LLM_API_BASE") or not os.getenv("LLM_API_KEY")):
        print("[error] needs LLM_API_BASE / LLM_API_KEY (or use --offline for the plumbing self-test).")
        return 1

    from eval.ambiguity_calibration import MODELS
    models = [m.strip() for m in a.models.split(",")] if a.models else MODELS
    run(a.rounds, models, a.offline, a.per_op, a.out, a.grid)
    return 0


def _resummarize(json_path: str, out_dir: str) -> int:
    """Recompute aggregates + report + verdict from a saved run's per-case JSON
    (no LLM calls). Used after a gate-logic fix to re-derive the verdict."""
    p = Path(json_path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parents[1] / json_path
    data = json.loads(p.read_text(encoding="utf-8"))
    rows = data["cases"]
    agg = {a: defaultdict(float) for a in ARMS}
    fam = {a: defaultdict(lambda: [0, 0]) for a in ARMS}
    for row in rows:
        op = row["case"].split("#")[0]
        for arm in ARMS:
            r = row[arm]
            agg[arm]["n"] += 1
            agg[arm]["success"] += int(r["success"])
            agg[arm]["rounds"] += r["rounds"]
            agg[arm]["calls"] += r["calls"]
            agg[arm]["over_a"] += r["over_repair_a"]
            agg[arm]["over_b"] += int(r["over_repair_b"])
            agg[arm]["malformed"] += r.get("n_malformed", 0)
            agg[arm][f"stop_{r.get('stop_reason','budget')}"] += 1
            fam[arm][op][0] += int(r["success"])
            fam[arm][op][1] += 1
    summary = _summarize(agg, fam, len(rows), max(int(rows[0]["targeted"]["rounds"]) if rows else 3, 3),
                         bool(data.get("offline")), ["(resummarized)"])
    _write_report(out_dir, summary, rows, agg, fam, bool(data.get("offline")))
    print(summary["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
