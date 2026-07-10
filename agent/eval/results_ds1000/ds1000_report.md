# External real-task silent-error rate — DS-1000 pandas (152 problems)

Breaks the our-tasks-our-gold circularity: TASKS are real StackOverflow
data-wrangling intents (DS-1000), GOLD is DS-1000's own execution test cases
(not our oracle). We measure the SAME signal — among solutions that EXECUTE,
how often the answer is SILENTLY WRONG (runs fine, wrong result) vs a loud
crash — across 2 models (gpt-4o, claude-sonnet-4.6). 95% Wilson CIs.

## (1) Silent-error rate on REAL external tasks
- silent / exec-ok: 70/273 (26% [95% CI 21-31])
- crash / total:    31/304 (proxy-None after retries: 10)
- overall accuracy:  203/304 correct

## (2) Silent-error rate by ambiguity-prone operator family
- groupby_agg  silent 25/112 (22% [95% CI 16-31]), crash 16
- apply_map    silent 17/75 (23% [95% CI 15-33]), crash 3
- pivot        silent 21/47 (45% [95% CI 31-59]), crash 7
- merge_join   silent 6/46 (13% [95% CI 6-26]), crash 4
- fillna_nan   silent 12/34 (35% [95% CI 21-52]), crash 4
- median_mean  silent 4/28 (14% [95% CI 6-31]), crash 2
- dedup        silent 6/17 (35% [95% CI 17-59]), crash 5
- sort_topk    silent 6/17 (35% [95% CI 17-59]), crash 1
- cumulative   silent 2/10 (20% [95% CI 6-51]), crash 2
- rank         silent 0/6 (0% [95% CI 0-39]), crash 0

## Interpretation
A high silent-error rate here corroborates the Nature-slice finding on a
corpus we did not design with gold we did not author: real users' pandas
intents are frequently met with confidently-wrong, non-crashing code. This
is the external-validity anchor for the goldless-detection motivation.
