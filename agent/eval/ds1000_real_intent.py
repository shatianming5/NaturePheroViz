"""
ds1000_real_intent.py — break the "our-tasks-our-gold" circularity with an
EXTERNAL real-task corpus.

The held-out Nature slice still uses OUR tasks (operator-semantic transforms we
authored) judged by OUR gold (template oracle). A reviewer can object that both
the task distribution and the gold are ours, so the 77% silent-error rate might
be an artifact of how we pose tasks. This experiment removes that circularity:

  * TASKS  = real StackOverflow data-wrangling problems (DS-1000, xlangai/DS-1000
             on HuggingFace). Natural-language intent written by real users.
  * GOLD   = DS-1000's own execution test cases (reference outputs the dataset
             authors verified), NOT our oracle. We never touch transform_oracle.
  * SIGNAL = the SAME quantity we care about: among solutions that EXECUTE, how
             often is the answer SILENTLY WRONG (runs fine, wrong result) vs a
             loud crash. DS-1000's harness distinguishes these natively (exec
             raises => crash; result produced but assert fails => silent).

We focus on the ambiguity-prone operator families our thesis targets
(groupby/agg, merge, rank, pivot, median/mean, fillna, ...) and report the
silent-error rate overall + per family, with 95% Wilson intervals, on these
REAL intents with REAL gold.

Usage:
  # sanity: run the dataset's OWN reference_code through our harness driver.
  # Must be ~100% pass / 0 silent (proves the pass/silent/crash classifier +
  # gold wiring are correct, analogous to the oracle false-fire check).
  python eval/ds1000_real_intent.py --offline

  # real run (paced LLM calls via the proxy):
  cd agent && LLM_API_BASE=http://.../v1 LLM_API_KEY=... \
      python eval/ds1000_real_intent.py --max-tasks 155 --out eval/results_ds1000

  python eval/ds1000_real_intent.py --families groupby_agg,merge_join --max-tasks 40
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import warnings  # noqa: E402
warnings.filterwarnings("ignore")

from eval.nature_real_transform import _wilson  # noqa: E402

# Ambiguity-prone operator families our thesis targets. Matched against the
# DS-1000 reference_code so the labelling is independent of the model's output.
FAMILIES: Dict[str, str] = {
    "groupby_agg": r"\.groupby\(|\.agg\(|\.transform\(",
    "merge_join": r"\.merge\(|pd\.merge|\.join\(",
    "rank": r"\.rank\(",
    "pivot": r"\.pivot|\.melt\(|\.stack\(|\.unstack\(",
    "median_mean": r"\.median\(|\.mean\(|\.quantile\(",
    "cumulative": r"\.cumsum\(|\.cumprod\(|\.cummax\(|\.cummin\(|\.shift\(|\.diff\(",
    "fillna_nan": r"\.fillna\(|\.dropna\(|\.isna\(|\.isnull\(|\.interpolate\(",
    "dedup": r"\.drop_duplicates\(|\.duplicated\(|\.nunique\(",
    "sort_topk": r"\.sort_values\(|\.nlargest\(|\.nsmallest\(",
    "apply_map": r"\.apply\(|\.applymap\(|\.map\(",
}

MODELS_DEFAULT = ["gpt-4o", "claude-sonnet-4.6"]


def _families_of(reference_code: str) -> List[str]:
    return [f for f, p in FAMILIES.items() if re.search(p, reference_code)]


def _is_completion_format(record: Dict[str, Any]) -> bool:
    """DS-1000 has two prompt protocols. Completion: `[insert]` sits at column 0
    after `df = test_input`, the solution is free-standing and must assign
    `result`. Insertion: `[insert]` is the body of a `def f(df):` and the
    solution must be indented and `return` the answer (reference_code is stored
    pre-indented). We keep only completion-format so every task shares one
    contract ("assign to result"); the 16 insertion-format pandas problems use a
    different protocol and are excluded (a presentation choice, not semantics)."""
    cc = record["code_context"]
    m = re.search(r"\n([^\n]*)\n\[insert\]", cc)
    prev = m.group(1).rstrip() if m else ""
    if prev.endswith(":"):
        return False
    if record["reference_code"][:1] in (" ", "\t"):
        return False
    return True


def _load_pandas(max_tasks: int, families: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Load DS-1000 pandas problems, optionally filtered to target families."""
    from datasets import load_dataset

    ds = load_dataset("xlangai/DS-1000", split="test")
    out: List[Dict[str, Any]] = []
    for r in ds:
        meta = r.get("metadata") or {}
        if not isinstance(meta, dict) or meta.get("library") != "Pandas":
            continue
        if not _is_completion_format(r):
            continue  # exclude insertion-format (different solution contract)
        fams = _families_of(r["reference_code"])
        if families is not None and not (set(fams) & set(families)):
            continue
        if families is None and not fams:
            continue  # default: only ambiguity-prone problems (>=1 target family)
        out.append({
            "problem_id": meta.get("problem_id"),
            "prompt": r["prompt"],
            "reference_code": r["reference_code"],
            "code_context": r["code_context"],
            "test_case_cnt": int(meta.get("test_case_cnt") or 1),
            "families": fams,
        })
        if max_tasks and len(out) >= max_tasks:
            break
    return out


# ---------------------------------------------------------------------------
# Harness driver: run a candidate solution through DS-1000's own code_context
# and classify the outcome as pass / silent / crash.
# ---------------------------------------------------------------------------
_MISSING = object()


def _harness_vars(exec_context: str) -> List[str]:
    """Names the harness binds from `test_input` (e.g. `df, List = test_input`).
    A model solution must NOT re-assign these or it would clobber the real test
    data with whatever it hallucinated from the prompt."""
    names: List[str] = []
    for ln in exec_context.splitlines():
        m = re.match(r"\s*([A-Za-z_][\w, ]*)=\s*test_input\b", ln)
        if m:
            for n in m.group(1).split(","):
                n = n.strip()
                if n:
                    names.append(n)
    return names or ["df"]


def _classify(item: Dict[str, Any], solution: str) -> str:
    """Drive DS-1000's own test harness for one problem and classify the outcome.

    Returns one of: 'pass' (all test cases correct), 'silent' (every test case
    EXECUTES and produces a `result`, but at least one result is WRONG), or
    'crash' (some test case raises during exec or never binds `result`).

    We deliberately re-implement the per-case loop instead of calling the
    dataset's `test_execution` (which only asserts) so we can separate an
    execution exception (crash / loud failure) from a wrong-but-running answer
    (silent semantic error) — the exact distinction the thesis measures.
    """
    ctx: Dict[str, Any] = {}
    try:
        exec(item["code_context"], ctx)  # noqa: S102 — defines harness functions
    except Exception:
        return "crash"
    gen = ctx.get("generate_test_case")
    exec_test = ctx.get("exec_test")
    exec_context = ctx.get("exec_context")
    if not (callable(gen) and callable(exec_test) and isinstance(exec_context, str)):
        return "crash"

    full = exec_context.replace("[insert]", _sanitize(solution, _harness_vars(exec_context)))
    any_wrong = False
    for i in range(1, item["test_case_cnt"] + 1):
        try:
            test_input, expected = gen(i)
        except Exception:
            # harness could not even build this case; skip it (don't punish model)
            continue
        env: Dict[str, Any] = {"test_input": test_input}
        try:
            exec(full, env)  # noqa: S102 — the candidate solution runs here
        except Exception:
            return "crash"  # solution raised -> loud failure
        if "result" not in env or env["result"] is _MISSING:
            return "crash"  # ran but never produced an answer
        try:
            ok = exec_test(env["result"], expected)
        except Exception:
            ok = 0
        if not ok:
            any_wrong = True
    return "silent" if any_wrong else "pass"


# ---------------------------------------------------------------------------
# LLM client (same proxy contract as the rest of the eval suite).
# ---------------------------------------------------------------------------
def _extract_code(content: str) -> Optional[str]:
    """Pull the solution body out of a model reply. Prefer strict JSON
    {"code": ...}; fall back to fenced/<code> blocks; finally trim DS-1000
    sentinels (BEGIN/END SOLUTION, </code>)."""
    if content is None:
        return None
    m = re.search(r"\{[^{}]*\"code\"\s*:\s*\".*\}", content, re.S)
    if m:
        try:
            code = json.loads(m.group(0)).get("code")
            if code:
                return code
        except Exception:
            pass
    fence = re.search(r"```(?:python)?\n(.*?)```", content, re.S)
    if fence:
        content = fence.group(1)
    else:
        cb = re.search(r"<code>\n?(.*?)</code>", content, re.S)
        if cb:
            content = cb.group(1)
    content = re.split(r"END SOLUTION|</code>", content)[0]
    content = content.replace("BEGIN SOLUTION", "")
    return content.strip() or None


def _sanitize(code: str, protected: Optional[List[str]] = None) -> str:
    """Keep imports and in-place transforms (real solutions legitimately do
    `df = df.groupby(...)`); drop ONLY a line that RE-CREATES a harness-provided
    variable from literals (`df = pd.DataFrame({...})` echoed from the prompt) —
    detected as an assignment to a protected name whose RHS references none of
    the protected names. That clobbering would score the model on fake data;
    a genuine transform (RHS uses df/df2/List) is preserved."""
    protected = protected or ["df", "df2", "List"]
    pset = set(protected)
    out = []
    for ln in code.splitlines():
        m = re.match(r"^\s*([A-Za-z_]\w*)\s*=\s*([^=].*)$", ln)
        if m and m.group(1) in pset:
            rhs_names = set(re.findall(r"[A-Za-z_]\w*", m.group(2)))
            if not (rhs_names & pset):
                continue  # re-creation from literals -> drop to protect injected data
        out.append(ln)
    return "\n".join(out)


def _llm_solution(item: Dict[str, Any], model: str) -> Optional[str]:
    import requests

    base = os.environ["LLM_API_BASE"].rstrip("/")
    key = os.environ["LLM_API_KEY"]
    prompt = (
        item["prompt"]
        + "\n\nReturn ONLY strict JSON: {\"code\": \"<the solution body that assigns"
        " the final answer to `result`>\"}. The dataframe(s) and inputs shown above"
        " ALREADY EXIST in scope; do NOT re-create them, do NOT import anything, do"
        " NOT print. Provide only the solution body (no test scaffolding)."
    )
    try:
        ml = model.lower()
        reasoning = ml.startswith(("gpt-5", "o1", "o3", "o4")) or "codex" in ml
        payload: Dict[str, Any] = {"model": model, "messages": [{"role": "user", "content": prompt}]}
        if reasoning:
            payload["max_completion_tokens"] = 8000
        else:
            payload["temperature"] = 0.0
            payload["max_tokens"] = 4000
        r = requests.post(
            base + "/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=(10, 180),
        )
        r.raise_for_status()
        choices = r.json().get("choices") or []
        if not choices:
            return None
        return _extract_code(choices[0]["message"]["content"])
    except Exception:
        return None


def _llm_solution_retry(item: Dict[str, Any], model: str, retries: int = 7, pace: float = 0.6) -> Optional[str]:
    """Retry on None (transient proxy overload) with backoff; pace successful
    calls so a bulk run does not flood the proxy. Same contract as
    nature_real_auto._llm_code_retry so proxy-induced crashes -> ~0 and the
    residual crashes are genuine model failures."""
    for attempt in range(retries):
        code = _llm_solution(item, model)
        if code is not None:
            time.sleep(pace)
            return code
        time.sleep(min(2.0 * (attempt + 1), 12.0))
    return None


# ---------------------------------------------------------------------------
# Offline sanity: run the dataset's own reference_code through our driver.
# ---------------------------------------------------------------------------
def _offline(max_tasks: int, families: Optional[List[str]]) -> int:
    tasks = _load_pandas(max_tasks, families)
    print(f"[offline] driving {len(tasks)} DS-1000 pandas problems with their OWN reference_code")
    tally = {"pass": 0, "silent": 0, "crash": 0}
    bad = []
    for t in tasks:
        outcome = _classify(t, t["reference_code"])
        tally[outcome] += 1
        if outcome != "pass":
            bad.append((t["problem_id"], outcome))
    print(f"  pass={tally['pass']}  silent={tally['silent']}  crash={tally['crash']}")
    if bad:
        print(f"  [warn] {len(bad)} reference solutions not 'pass' (harness/driver limitation): {bad[:20]}")
    # The driver is correct iff reference_code overwhelmingly passes. A few
    # crashes can occur from environment-specific reference code; report them but
    # only fail hard if the pass rate is implausibly low.
    ok = tally["pass"] >= 0.85 * max(1, len(tasks)) and tally["silent"] == 0
    print(f"\n{'VALIDATION OK' if ok else 'VALIDATION WEAK'}: reference pass-rate"
          f" {tally['pass']}/{len(tasks)}, silent={tally['silent']} (expected silent=0)")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# Main real run.
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="External real-task silent-error rate on DS-1000 (breaks our-tasks-our-gold circularity)")
    ap.add_argument("--max-tasks", type=int, default=0, help="cap #problems (0 = all ambiguity-prone)")
    ap.add_argument("--families", default=None, help="comma-separated subset of: " + ",".join(FAMILIES))
    ap.add_argument("--models", default=None, help="comma-separated models (default gpt-4o,claude-sonnet-4.6)")
    ap.add_argument("--offline", action="store_true", help="validate harness driver with reference_code (no LLM)")
    ap.add_argument("--out", default="eval/results_ds1000")
    a = ap.parse_args(argv)

    families = [f.strip() for f in a.families.split(",")] if a.families else None
    if families:
        bad = [f for f in families if f not in FAMILIES]
        if bad:
            print(f"[error] unknown families: {bad}; choose from {list(FAMILIES)}"); return 2

    if a.offline:
        return _offline(a.max_tasks, families)

    if not os.getenv("LLM_API_BASE") or not os.getenv("LLM_API_KEY"):
        print("[error] needs LLM_API_BASE / LLM_API_KEY (or --offline)."); return 1

    models = [m.strip() for m in a.models.split(",")] if a.models else MODELS_DEFAULT
    tasks = _load_pandas(a.max_tasks, families)
    print(f"[ds1000] {len(tasks)} real pandas problems x {len(models)} models "
          f"(families={families or 'all-ambiguity-prone'})", flush=True)

    # counters
    execok = 0   # produced a runnable result (pass or silent)
    silent = 0   # ran but wrong
    crash = 0    # raised / no result
    proxy_crash = 0
    total = 0
    fam_stat: Dict[str, Dict[str, int]] = {f: {"execok": 0, "silent": 0, "crash": 0} for f in FAMILIES}
    rows = []

    for t in tasks:
        rec = {"problem_id": t["problem_id"], "families": t["families"]}
        for m in models:
            code = _llm_solution_retry(t, m)
            if code is None:
                outcome = "crash"; proxy_crash += 1
            else:
                outcome = _classify(t, code)
            total += 1
            if outcome == "crash":
                crash += 1
            else:
                execok += 1
                if outcome == "silent":
                    silent += 1
            for f in t["families"]:
                if outcome == "crash":
                    fam_stat[f]["crash"] += 1
                else:
                    fam_stat[f]["execok"] += 1
                    if outcome == "silent":
                        fam_stat[f]["silent"] += 1
            rec[m] = outcome
            print(f"[p{str(t['problem_id']):>4} {','.join(t['families'])[:24]:24}] {m:18} {outcome}", flush=True)
        rows.append(rec)

    report = [
        f"# External real-task silent-error rate — DS-1000 pandas ({len(tasks)} problems)\n",
        "Breaks the our-tasks-our-gold circularity: TASKS are real StackOverflow",
        "data-wrangling intents (DS-1000), GOLD is DS-1000's own execution test cases",
        "(not our oracle). We measure the SAME signal — among solutions that EXECUTE,",
        "how often the answer is SILENTLY WRONG (runs fine, wrong result) vs a loud",
        f"crash — across {len(models)} models ({', '.join(models)}). 95% Wilson CIs.\n",
        "## (1) Silent-error rate on REAL external tasks",
        f"- silent / exec-ok: {silent}/{execok} ({_wilson(silent, execok)})",
        f"- crash / total:    {crash}/{total} (proxy-None after retries: {proxy_crash})",
        f"- overall accuracy:  {execok - silent}/{total} correct\n",
        "## (2) Silent-error rate by ambiguity-prone operator family",
    ]
    for f in sorted(FAMILIES, key=lambda x: -fam_stat[x]["execok"]):
        s = fam_stat[f]
        if s["execok"] + s["crash"] == 0:
            continue
        report.append(f"- {f:12} silent {s['silent']}/{s['execok']} ({_wilson(s['silent'], s['execok'])}), crash {s['crash']}")
    report += [
        "\n## Interpretation",
        "A high silent-error rate here corroborates the Nature-slice finding on a",
        "corpus we did not design with gold we did not author: real users' pandas",
        "intents are frequently met with confidently-wrong, non-crashing code. This",
        "is the external-validity anchor for the goldless-detection motivation.",
    ]

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ds1000_report.md").write_text("\n".join(report) + "\n")
    (out_dir / "records.json").write_text(json.dumps(rows, indent=2))
    print("\n".join(report))
    print(f"\n[written] {out_dir/'ds1000_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
