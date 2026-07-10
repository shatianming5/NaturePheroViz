# Experiment 3 — real-world operator prevalence + coverage/abstain (external validity)

corpus: GitHub public code search, language:python (files matching the query)
harvested: 2026-06-25  (counts = matching public Python files)

## (1) Are the contract-covered operators common in real code?
| operator family | real-code files | contract(s) | covered |
|---|---:|---|:---:|
| cumulative / running | 320,640 | cumulative_running | ✅ |
| NaN semantics | 304,896 | nan_as_zero_sum | ✅ |
| median vs mean | 175,792 | median_not_mean | ✅ |
| dedup timing | 170,368 | dedup_then_agg | ✅ |
| join how | 161,344 | left_join_keep_all | ✅ |
| count / value_counts | 131,392 | count_includes_empty / proportion_true | ✅ |
| within-group share | 117,312 | within_group_share | ✅ |
| aggregation granularity | 112,416 | dedup_then_agg / pooled_rate / median_not_mean | ✅ |
| percentage points | 49,792 | pct_point | ✅ |
| top-n | 38,704 | topn_with_ties | ✅ |
| weighted mean | 28,320 | weighted_mean | ✅ |
| rank / ties | 26,576 | topn_with_ties / dense_rank | ✅ |
| **TOTAL (12 families)** | **1,637,552** | — | 12/12 |

## (2) Coverage / abstain on REAL data (already measured — §3.5)
- real slice: 841 tasks / 71 independent Nature articles (eval/results_real841/real_auto_report.md).
- oracle recall 1438/1471 = 98% [95% CI 97-98]; false-positive 4/1855 = 0% [95% CI 0-1].
- abstain: uncovered/blind-spot operators degrade to ABSTAIN, not false alarms (median_not_mean 95% recall is the honest blind spot; FP stays ~0).

## reading
- Every operator family our contracts target appears in tens-to-hundreds of thousands of real public Python files (total 1,637,552 across 12 families) — the silent-error surface is NOT synthetic; these are exactly the high-frequency wrangling operators in the wild.
- The most ambiguity-prone ones (NaN handling 304,896; cumulative 320,640; dedup 170,368; median 175,792; join-how 161,344) are among the MOST common — high frequency × high silent-risk.
- Coverage is honest: covered operators get high goldless recall / ~0 FP on real data; operators outside coverage degrade to ABSTAIN (see Experiment 2a abstain-routing), so prevalence of an uncovered operator never turns into mis-repair.

> Note: GitHub code-search counts are a prevalence proxy (file-level, may double-count forks / miss private code). They establish ORDER-OF-MAGNITUDE real-world frequency, not exact usage. For a controlled notebook corpus (operator frequency per notebook, abstain rate per notebook), PandasBench / CoCoNote / JunoBench are the next external sources (require download).
