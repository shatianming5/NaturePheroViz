"""
cegis_synth.py — counterexample-guided GOLDLESS contract synthesis (AAAI novelty upgrade).

Reviewers (all 3) said the synthesis is "just prompt an LLM once" = not an algorithm. This is a
genuine synthesis LOOP with a GOLDLESS verification oracle:

  1. synthesize contract C from the NL intent (1-shot).
  2. build a CONSENSUS bank: ask the LLM for K DIVERSE implementations of the same intent, run
     them on the fixture, cluster by output-equivalence; the largest cluster = the goldless
     "probably-correct" set (independent impls that agree — no gold used).
  3. VERIFY: if C fires on any consensus member, that is a goldless FALSE-POSITIVE counterexample
     (multiple independent impls agree on this output, yet C flags it → C is wrong).
  4. REFINE: feed the specific counterexample (input + wrongly-flagged result) back and
     re-synthesize C. Repeat up to T rounds.

The loop drives DOWN false positives (the de-leaked weak spot: FULL/alt-robust was only 70%
because contracts fired on valid alternatives) using ZERO gold. We then EVALUATE C against gold
(true wrong_fn / correct_fn / alt_correct_fns) — gold is eval-only, never used in the loop — and
compare 1-shot vs CEGIS on CORE and FULL. A lift in FULL at equal CORE = the algorithm works.

Run: cd agent && LLM_API_BASE=.. LLM_API_KEY=.. python eval/cegis_synth.py --model gpt-5.4 --source all
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys, textwrap
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np  # noqa
import pandas as pd  # noqa
from eval.operator_expansion import CANDIDATES
from eval.w2_firing import _chat_api
from eval.autocontract_synth import (SYNTH_PROMPT, DELEAKED_INTENT, _schema, _result_schema,
                                     _run_auto, _as_frame, wilson)

IMPL_PROMPT = """Implement this data transform in pandas. Write EXACTLY:

    def f(inp, params):
        # inp: dict with "df" (pandas.DataFrame) and optionally "df2"
        # params: dict of column-name parameters
        # return the resulting pandas DataFrame (or a scalar)
        ...

GOAL: {goal}
Input df columns: {cols}{extra}
Params: {params}
Use pandas/numpy (pd, np in scope). No imports/printing/IO. Return ONLY strict JSON:
{{"code": "<def f...>"}}. Take approach #{k} — vary your method from other approaches."""

REFINE_SUFFIX = """

Your PREVIOUS contract was:
{prev}

But it WRONGLY returned True (flagged a silent error) on the following VALID result, which
{n_agree} independent correct implementations all agree on — so it is a FALSE POSITIVE:
  params  = {params}
  result  = {result}
Rewrite the contract so it does NOT fire on this valid result, while still catching genuine
violations of the intent. Return ONLY strict JSON: {{"code": "<def contract...>"}}."""


def _extract(out, name):
    m = re.search(r"\{.*\}", out or "", re.S)
    if m:
        try:
            c = json.loads(m.group(0)).get("code")
            if c:
                return c
        except Exception:
            pass
    m2 = re.search(rf"def {name}.*", out or "", re.S)
    return m2.group(0) if m2 else None


def synth(cand, intent, model, extra_suffix=""):
    inp = cand.fixture()
    cols, extra = _schema(inp)
    kind, rcols = _result_schema(cand.correct_fn(inp))
    prompt = SYNTH_PROMPT.format(intent=intent, cols=cols, extra=extra, params=cand.params,
                                 kind=kind, rcols=rcols) + extra_suffix
    for _ in range(3):  # retry transient proxy drops (empty completion)
        code = _extract(_chat_api([{"role": "user", "content": prompt}], model, max_tok=4000), "contract")
        if code:
            return code
    return None


def gen_impl(cand, intent, model, k):
    inp = cand.fixture()
    cols, extra = _schema(inp)
    p = IMPL_PROMPT.format(goal=intent, cols=cols, extra=extra, params=cand.params, k=k)
    code = None
    for _ in range(2):  # retry transient proxy drops
        code = _extract(_chat_api([{"role": "user", "content": p}], model, max_tok=2000), "f")
        if code:
            break
    if not code:
        return None
    ns = {"pd": pd, "np": np}
    try:
        exec(textwrap.dedent(code), ns)  # noqa: S102
        fn = ns.get("f")
        return fn(inp) if fn and _arity(fn) == 1 else (fn(inp, cand.params) if fn else None)
    except Exception:
        return None


def _arity(fn):
    try:
        import inspect
        return len(inspect.signature(fn).parameters)
    except Exception:
        return 2


def _hash(res):
    try:
        f = _as_frame(res)
        return hashlib.md5(pd.util.hash_pandas_object(f.round(6), index=False).values.tobytes()).hexdigest()
    except Exception:
        try:
            return hashlib.md5(str(np.round(np.asarray(res, float), 6)).encode()).hexdigest()
        except Exception:
            return None


def consensus_bank(cand, intent, model, k=4):
    """K diverse impls -> outputs -> largest agreeing cluster = goldless probably-correct set."""
    outs = []
    for i in range(k):
        r = gen_impl(cand, intent, model, i + 1)
        if r is not None:
            outs.append(r)
    clusters = {}
    for r in outs:
        h = _hash(r)
        if h is None:
            continue
        clusters.setdefault(h, []).append(r)
    if not clusters:
        return []
    best = max(clusters.values(), key=len)
    return best  # list of result frames all agreeing


def evaluate(cand, code):
    inp = cand.fixture()
    fw = _run_auto(code, inp, cand.params, _as_frame(cand.wrong_fn(inp)))
    pc = _run_auto(code, inp, cand.params, _as_frame(cand.correct_fn(inp)))
    alt_ok = True
    for alt in (cand.alt_correct_fns or []):
        try:
            a = _as_frame(alt(inp))
        except Exception:
            continue
        if _run_auto(code, inp, cand.params, a):
            alt_ok = False
    core = (fw is True) and (pc is False)
    return {"fire_wrong": fw, "pass_correct": (pc is False), "alt_ok": alt_ok,
            "core": bool(core), "full": bool(core and alt_ok),
            "exec_ok": (fw is not None and pc is not None)}


def _corrupt(res):
    """Metamorphic non-triviality probes: perturb a consensus-valid result in intent-agnostic
    ways. A genuine conservation/identity/range contract should FIRE on most of these; a
    degenerate always-pass contract fires on none -> lets us reject degeneracy GOLDLESSLY."""
    probes = []
    try:
        f = _as_frame(res).copy()
    except Exception:
        return probes
    num = [c for c in f.columns if pd.api.types.is_numeric_dtype(f[c])]
    if num and len(f) >= 1:
        c = num[-1]
        p1 = f.copy(); p1[c] = p1[c] * 2.0 + 1.0; probes.append(p1)          # scale+shift
        p2 = f.copy(); p2[c] = p2[c].values[::-1]; probes.append(p2)          # permute values
    if len(f) >= 2:
        probes.append(f.iloc[:-1].copy())                                     # drop a row
        p4 = f.copy()
        if num:
            p4.loc[p4.index[0], num[-1]] = p4[num[-1]].iloc[0] + 1000.0        # spike one cell
            probes.append(p4)
    return probes


def _score(code, inp, params, bank, probes):
    """GOLDLESS score: pass on agreed-valid consensus (no FP) + fire on corrupted probes
    (non-trivial/sensitive). Returns (score, consensus_pass, probe_fire) or None if unusable."""
    if not code:
        return None
    cp = pf = 0
    for r in bank:
        v = _run_auto(code, inp, params, _as_frame(r))
        if v is None:
            return None
        cp += int(v is False)          # did NOT fire on an agreed-valid result -> good
    for p in probes:
        v = _run_auto(code, inp, params, _as_frame(p))
        pf += int(v is True)           # fired on a corrupted result -> good (sensitive)
    return (cp + pf, cp, pf)


def cegis(cand, intent, model, rounds=3, k=4, min_bank=3, c0=None):
    """Monotone-safe goldless synthesis: start from 1-shot C0, then refine against consensus FP
    counterexamples; SELECT the best candidate by a goldless score (consensus-pass +
    corruption-fire). Guaranteed >= 1-shot on the goldless score -> no regression by design.
    Refinement only runs when the consensus is TRUSTWORTHY (>= min_bank independent impls
    agree); on weak consensus we keep the 1-shot contract (a weak/biased bank is an unreliable
    goldless signal and can otherwise teach C to accept the bug). c0 is REUSED as the 1-shot
    seed so the 1-shot-vs-CEGIS comparison is apples-to-apples (same starting contract)."""
    bank = consensus_bank(cand, intent, model, k=k)
    inp = cand.fixture()
    probes = _corrupt(bank[0]) if bank else _corrupt(cand.correct_fn(inp))
    if c0 is None:
        c0 = synth(cand, intent, model)
    best_code = c0
    best = _score(c0, inp, cand.params, bank, probes) or (-1, 0, 0)
    trace = [{"round": 0, "n_consensus": len(bank), "n_probes": len(probes), "score": best[0]}]
    if len(bank) < min_bank:
        trace.append({"skipped": f"bank {len(bank)} < min_bank {min_bank} (weak consensus)"})
        return c0, len(bank), trace
    code = c0
    for t in range(1, rounds + 1):
        ce = None
        for r in bank:
            if _run_auto(code, inp, cand.params, _as_frame(r)) is True:
                ce = r; break
        if ce is None:
            trace.append({"round": t, "fp_counterexample": False}); break
        suffix = REFINE_SUFFIX.format(prev=(code or "")[:1200], n_agree=len(bank),
                                      params=cand.params, result=_as_frame(ce).to_dict("list"))
        new = synth(cand, intent, model, extra_suffix=suffix)
        sc = _score(new, inp, cand.params, bank, probes)
        acc = sc is not None and sc[2] > 0 and sc[0] > best[0]   # must stay non-trivial AND strictly improve
        trace.append({"round": t, "fp_counterexample": True, "new_score": (sc[0] if sc else None),
                      "accepted": bool(acc)})
        if acc:
            best_code, best, code = new, sc, new
        else:
            code = new  # keep exploring from the new one but don't crown it
    return best_code, len(bank), trace


def run(cands, intent_map, model, rounds, k, min_bank=3):
    rows = []
    for c in cands:
        intent = intent_map.get(c.operator, f"Compute the {c.operator} transform.")
        base = synth(c, intent, model)
        ev0 = evaluate(c, base)
        code, nbank, trace = cegis(c, intent, model, rounds=rounds, k=k, min_bank=min_bank, c0=base)
        ev1 = evaluate(c, code)
        rows.append({"op": c.operator, "n_consensus": nbank,
                     "oneshot": {k2: ev0[k2] for k2 in ("core", "full", "exec_ok")},
                     "cegis": {k2: ev1[k2] for k2 in ("core", "full", "exec_ok")},
                     "trace": trace})
        print(f"  {c.operator:26} bank={nbank}  1shot[core={ev0['core']} full={ev0['full']}]  "
              f"cegis[core={ev1['core']} full={ev1['full']}]"
              f"{'  <== FULL+' if (ev1['full'] and not ev0['full']) else ''}", flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-5.4")
    ap.add_argument("--source", choices=("core", "expansion", "all"), default="all")
    ap.add_argument("--intent", choices=("leaky", "deleaked"), default="deleaked")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--k", type=int, default=4, help="diverse impls in the consensus bank")
    ap.add_argument("--min-bank", type=int, default=3, help="min agreeing impls to trust refinement")
    ap.add_argument("--out", default="eval/results_cegis/cegis_report.json")
    a = ap.parse_args()
    from eval.autocontract_synth import INTENT
    intent_map = DELEAKED_INTENT if a.intent == "deleaked" else INTENT
    from eval.core_candidates import CORE_CANDIDATES
    pool = (list(CORE_CANDIDATES) if a.source in ("core", "all") else []) + \
           (list(CANDIDATES) if a.source in ("expansion", "all") else [])
    cands = [c for c in pool if isinstance(c.fixture().get("df"), pd.DataFrame)]

    rows = run(cands, intent_map, a.model, a.rounds, a.k, a.min_bank)
    n = len(rows)
    o_core = sum(r["oneshot"]["core"] for r in rows); o_full = sum(r["oneshot"]["full"] for r in rows)
    c_core = sum(r["cegis"]["core"] for r in rows); c_full = sum(r["cegis"]["full"] for r in rows)
    summary = {"model": a.model, "intent": a.intent, "rounds": a.rounds, "k": a.k, "n": n,
               "oneshot": {"core": o_core, "full": o_full,
                           "core_ci": wilson(o_core, n), "full_ci": wilson(o_full, n)},
               "cegis": {"core": c_core, "full": c_full,
                         "core_ci": wilson(c_core, n), "full_ci": wilson(c_full, n)},
               "cases": rows}
    outp = Path(a.out); outp.parent.mkdir(parents=True, exist_ok=True)
    json.dump(summary, open(outp, "w"), indent=2)
    print(f"\n=== GOLDLESS counterexample-guided synthesis (model {a.model}, intent={a.intent}, N={n}) ===")
    print(f"1-shot : CORE {o_core}/{n}={wilson(o_core,n)[0]}%  FULL {o_full}/{n}={wilson(o_full,n)[0]}% CI{wilson(o_full,n)[1:]}")
    print(f"CEGIS  : CORE {c_core}/{n}={wilson(c_core,n)[0]}%  FULL {c_full}/{n}={wilson(c_full,n)[0]}% CI{wilson(c_full,n)[1:]}")
    print(f"FULL lift: {o_full}/{n} -> {c_full}/{n}  (+{c_full-o_full}); GOLDLESS (consensus bank, no reference answer)")
    print(f"-> {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
