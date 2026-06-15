# Held-out REAL-DATA slice: transform fidelity on real Nature source tables

Real input frames (scientific column names: ETR/PAR/VAF/log2FoldChange/ddCt), same
operator-semantic taxonomy + (ambiguous, clarified) prompts + goldless oracle.
Sample: 9 curated real tables across multiple Nature papers; rates with
95% Wilson score intervals (the slice is deliberately small + held-out, so CIs are wide).

## (1) Silent-error rate on REAL data
- ambiguous prompts: 13/18 silent-wrong (72% [95% CI 49-88])
- clarified prompts: 6/18 silent-wrong (33% [95% CI 16-56])

## (2) Oracle recall on real silent errors
- fired on 19/19 truly-wrong (100% [95% CI 83-100])

## (3) Oracle false-positive on real correct results
- fired on 0/17 truly-correct (0% [95% CI 0-18])

## Reading
- Real domain column names + real distributions => the silent-error phenomenon is
  not an artifact of synthetic toy tables; the oracle transfers to held-out real data.
- CIs are wide (small held-out slice) but the ambiguous-silent lower bound stays well
  above 0, and the oracle FP upper bound stays low — the direction is robust to sample size.