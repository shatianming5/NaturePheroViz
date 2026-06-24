# LARGE held-out real-data slice: 841 tasks across 71 INDEPENDENT Nature articles

Generator scanned 211 Nature articles / 1607 source-data tables. To guarantee
cross-paper independence, each article contributes at most 15 tasks (--max-per-
article 15), avoiding domination by a few big multi-sheet tables. Result: 841
real tasks across 71 independent articles, every gold oracle-validated. Same
(ambiguous, clarified) prompts + goldless oracle. 95% Wilson CIs.

## (1) Silent-error rate on REAL data (841 tasks / 71 articles)
- ambiguous: 1296/1682 (77% [95% CI 75-79])
- clarified: 175/1682 (10% [95% CI 9-12])

## (2) Oracle recall on real silent errors
- 1438/1471 (98% [95% CI 97-98])
- by operator: weighted_mean 140/140=100%, nan_as_zero_sum 16/16=100%,
  within_group_share 538/539=99.8%, pooled_rate 118/119=99%,
  median_not_mean 626/657=95% (minor contract blind spot, honest boundary)

## (3) Oracle false-positive on real correct results
- 4/1855 (0% [95% CI 0-1])

## Reading
- 841 tasks across 71 INDEPENDENT Nature articles (per-article capped at 15) is a
  genuinely independent cross-paper sample, not a few big tables squeezed.
- 77% ambiguous silent on real data [CI 75-79] is the paper's hardest alarm number.
- Oracle recall 98%, FP 0% (4/1855) — near-perfect detection on a 71-paper sample.
- Honesty note: an early version without the per-article cap produced "500 tasks"
  that actually came from only 3 articles (highly correlated); the cap fixes this
  to a true 71-paper independent sample.
