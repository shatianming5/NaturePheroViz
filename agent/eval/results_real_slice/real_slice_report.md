# Held-out REAL-DATA slice: transform fidelity on real Nature source tables

Real input frames (scientific column names: ETR/PAR/VAF/log2FoldChange/ddCt), same
operator-semantic taxonomy + (ambiguous, clarified) prompts + goldless oracle.

## (1) Silent-error rate on REAL data
- ambiguous prompts: 13/18 silent-wrong (72%)
- clarified prompts: 5/18 silent-wrong (28%)

## (2) Oracle recall on real silent errors
- fired on 18/18 truly-wrong (100%)

## (3) Oracle false-positive on real correct results
- fired on 0/18 truly-correct (0%)

## Reading
- Real domain column names + real distributions => the silent-error phenomenon is
  not an artifact of synthetic toy tables; the oracle transfers to held-out real data.