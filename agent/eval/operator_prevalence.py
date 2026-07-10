"""
operator_prevalence.py — §8 Experiment 3 (external validity: are the ambiguity-prone
operators our contracts cover actually COMMON in real-world code?).

There is no local notebook corpus, and the silent-error phenomenon was already shown on
a real Nature-data slice (§3.5: 841 tasks / 71 articles, oracle recall 98%, FP 0%). The
remaining external-validity question for the REPAIR extension is prevalence: do these
high-risk operator semantics show up in real code at scale, or are they a synthetic
concern? We answer with GitHub code search over public Python files (a large, real,
in-the-wild corpus), counting files that use each operator family our contracts target.

This module records a REPRODUCIBLE SNAPSHOT of those counts (query string + count +
harvest date) and maps each operator to (a) its contract family and (b) coverage status,
then emits a report. Re-harvest by re-running the listed queries via GitHub code search
(`search_code`, language:python) and updating SNAPSHOT.

Run:  cd agent && python eval/operator_prevalence.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import eval.transform_oracle as ORACLE  # noqa: E402

HARVEST_DATE = "2026-06-25"
CORPUS = "GitHub public code search, language:python (files matching the query)"

# Snapshot: operator family -> {query, count, contract, covered}
# count = GitHub code-search total_count on HARVEST_DATE (files, not occurrences).
SNAPSHOT: List[Dict[str, Any]] = [
    {"family": "aggregation granularity", "query": 'language:python ".groupby(" ".agg("',
     "count": 112416, "contract": "dedup_then_agg / pooled_rate / median_not_mean", "covered": True},
    {"family": "within-group share", "query": 'language:python ".transform(" "groupby"',
     "count": 117312, "contract": "within_group_share", "covered": True},
    {"family": "join how", "query": 'language:python ".merge(" "how="',
     "count": 161344, "contract": "left_join_keep_all", "covered": True},
    {"family": "rank / ties", "query": 'language:python ".rank(" "method="',
     "count": 26576, "contract": "topn_with_ties / dense_rank", "covered": True},
    {"family": "dedup timing", "query": 'language:python ".drop_duplicates("',
     "count": 170368, "contract": "dedup_then_agg", "covered": True},
    {"family": "NaN semantics", "query": 'language:python ".fillna("',
     "count": 304896, "contract": "nan_as_zero_sum", "covered": True},
    {"family": "median vs mean", "query": 'language:python ".median("',
     "count": 175792, "contract": "median_not_mean", "covered": True},
    {"family": "cumulative / running", "query": 'language:python ".cumsum("',
     "count": 320640, "contract": "cumulative_running", "covered": True},
    {"family": "count / value_counts", "query": 'language:python ".value_counts("',
     "count": 131392, "contract": "count_includes_empty / proportion_true", "covered": True},
    {"family": "top-n", "query": 'language:python ".nlargest("',
     "count": 38704, "contract": "topn_with_ties", "covered": True},
    {"family": "weighted mean", "query": 'language:python "np.average(" "weights="',
     "count": 28320, "contract": "weighted_mean", "covered": True},
    {"family": "percentage points", "query": 'language:python ".pct_change("',
     "count": 49792, "contract": "pct_point", "covered": True},
]

# Coverage / abstain evidence already measured on REAL data (do not re-run here; cite).
REAL_SLICE = {
    "source": "eval/results_real841/real_auto_report.md",
    "tasks": 841, "articles": 71,
    "oracle_recall": "1438/1471 = 98% [95% CI 97-98]",
    "oracle_fp": "4/1855 = 0% [95% CI 0-1]",
    "abstain_note": "uncovered/blind-spot operators degrade to ABSTAIN, not false alarms "
                    "(median_not_mean 95% recall is the honest blind spot; FP stays ~0).",
}


def _report() -> str:
    n_cov = sum(1 for r in SNAPSHOT if r["covered"])
    total = sum(r["count"] for r in SNAPSHOT)
    lines = ["# Experiment 3 — real-world operator prevalence + coverage/abstain (external validity)", ""]
    lines.append(f"corpus: {CORPUS}")
    lines.append(f"harvested: {HARVEST_DATE}  (counts = matching public Python files)")
    lines.append("")
    lines.append("## (1) Are the contract-covered operators common in real code?")
    lines.append("| operator family | real-code files | contract(s) | covered |")
    lines.append("|---|---:|---|:---:|")
    for r in sorted(SNAPSHOT, key=lambda x: -x["count"]):
        lines.append(f"| {r['family']} | {r['count']:,} | {r['contract']} | {'✅' if r['covered'] else '—'} |")
    lines.append(f"| **TOTAL (12 families)** | **{total:,}** | — | {n_cov}/12 |")
    lines.append("")
    lines.append("## (2) Coverage / abstain on REAL data (already measured — §3.5)")
    lines.append(f"- real slice: {REAL_SLICE['tasks']} tasks / {REAL_SLICE['articles']} independent Nature articles "
                 f"({REAL_SLICE['source']}).")
    lines.append(f"- oracle recall {REAL_SLICE['oracle_recall']}; false-positive {REAL_SLICE['oracle_fp']}.")
    lines.append(f"- abstain: {REAL_SLICE['abstain_note']}")
    lines.append("")
    lines.append("## reading")
    lines.append(f"- Every operator family our contracts target appears in tens-to-hundreds of thousands of real "
                 f"public Python files (total {total:,} across 12 families) — the silent-error surface is NOT "
                 "synthetic; these are exactly the high-frequency wrangling operators in the wild.")
    lines.append("- The most ambiguity-prone ones (NaN handling 304,896; cumulative 320,640; dedup 170,368; "
                 "median 175,792; join-how 161,344) are among the MOST common — high frequency × high silent-risk.")
    lines.append("- Coverage is honest: covered operators get high goldless recall / ~0 FP on real data; operators "
                 "outside coverage degrade to ABSTAIN (see Experiment 2a abstain-routing), so prevalence of an "
                 "uncovered operator never turns into mis-repair.")
    lines.append("")
    lines.append("> Note: GitHub code-search counts are a prevalence proxy (file-level, may double-count forks / "
                 "miss private code). They establish ORDER-OF-MAGNITUDE real-world frequency, not exact usage. "
                 "For a controlled notebook corpus (operator frequency per notebook, abstain rate per notebook), "
                 "PandasBench / CoCoNote / JunoBench are the next external sources (require download).")
    return "\n".join(lines)


def main() -> int:
    # sanity: every covered contract name in the snapshot exists in the oracle library
    known = set(ORACLE.CONTRACTS)
    referenced = set()
    for r in SNAPSHOT:
        for c in r["contract"].replace(" ", "").split("/"):
            referenced.add(c)
    missing = referenced - known
    if missing:
        print(f"[warn] snapshot references contracts not in oracle: {sorted(missing)}", file=sys.stderr)

    text = _report()
    d = Path(__file__).resolve().parents[1] / "eval/results_prevalence"
    d.mkdir(parents=True, exist_ok=True)
    (d / "operator_prevalence_report.md").write_text(text + "\n", encoding="utf-8")
    (d / "operator_prevalence.json").write_text(
        json.dumps({"harvest_date": HARVEST_DATE, "corpus": CORPUS,
                    "snapshot": SNAPSHOT, "real_slice": REAL_SLICE}, indent=2),
        encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
