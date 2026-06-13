# LARGE held-out real-data slice: 206 auto-generated real Nature tasks

Across 17 Nature articles, real scientific tables, same operator-semantic tasks
(median / within_group_share / weighted_mean / pooled_rate / nan_as_zero_sum) +
(ambiguous, clarified) prompts + goldless oracle. Rates with 95% Wilson CIs.

## (1) Silent-error rate on REAL data (large slice)
- ambiguous: 142/206 (69% [95% CI 62-75])
- clarified: 38/206 (18% [95% CI 14-24])

## (2) Oracle recall on real silent errors
- 169/180 (94% [95% CI 89-97])
- by operator: median_not_mean 129/129=100%, weighted_mean 27/27=100%,
  within_group_share 105/107=98%, pooled_rate 23/25=92% (zero-fire blind spots
  are an honest coverage boundary, not a measurement error)

## (3) Oracle false-positive on real correct results
- 0/210 (0% [95% CI 0-2])

## Reading
- 206 real tasks across 17 articles (vs the 9-table curated slice) makes the
  external-validity claim impossible to dismiss as small-sample; CIs are tight.
- The 69% ambiguous silent rate on real scientific data is a headline alarm number.
- Oracle FP = 0% on 210 correct results; recall layered honestly (mature operators
  100%, share/pooled have minor coverage gaps).
