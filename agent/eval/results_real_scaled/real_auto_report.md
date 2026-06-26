# LARGE held-out real-data slice: 800 auto-generated real Nature tasks

Across 229 Nature articles, real scientific tables, same operator-semantic
tasks + (ambiguous, clarified) prompts + goldless oracle. Rates with 95% Wilson CIs.

## (1) Silent-error rate on REAL data (large slice)
- ambiguous: 1079/1393 (77% [95% CI 75-80])
- clarified: 312/1520 (21% [95% CI 19-23])

## (2) Oracle recall on real silent errors
- 1385/1391 (100% [95% CI 99-100])

## (3) Oracle false-positive on real correct results
- 2/1522 (0% [95% CI 0-0])

## Reading
- 800 real tasks (vs the 9-table curated slice) makes the external-validity
  claim hard to dismiss as small-sample; CIs are now tight.
- exec crashes (LLM/proxy or bad code): 287/3200 (silent rate is over exec-ok tasks; crashes must stay ~0 for a valid measurement).