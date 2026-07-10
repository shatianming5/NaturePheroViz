# LARGE held-out real-data slice: 800 auto-generated real Nature tasks

Across 229 Nature articles, real scientific tables, same operator-semantic
tasks + (ambiguous, clarified) prompts + goldless oracle. Rates with 95% Wilson CIs.

## (1) Silent-error rate on REAL data (large slice)
- ambiguous: 1092/1408 (78% [95% CI 75-80])
- clarified: 316/1539 (21% [95% CI 19-23])

## (2) Oracle recall on real silent errors
- 1398/1408 (99% [95% CI 99-100])

## (3) Oracle false-positive on real correct results
- 2/1539 (0% [95% CI 0-0])

## Reading
- 800 real tasks (vs the 9-table curated slice) makes the external-validity
  claim hard to dismiss as small-sample; CIs are now tight.
- exec crashes: 253/3200 (proxy/LLM None=73, bad-code-on-real-table=180); silent rate is over exec-ok only, so proxy hiccups cannot deflate it. Proxy crashes ~0 with retry+pace; exec_crash is a genuine model-failure rate on messy real tables.