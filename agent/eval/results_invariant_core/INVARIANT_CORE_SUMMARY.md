# Non-circular core is a FAMILY, not one operator (grid validation)

Each of the 12 core contracts is classified by whether it recomputes the
expected value (RECOMPUTATION; gold-equivalent under a known operator) or only
asserts a relational/structural/conservation property that derives NO reference
value (PURE INVARIANT; the non-circular core). We then validate every contract
offline on the shared fixtures: it must FIRE on the canonical silent slip
(recall) and must NOT fire on the intended transform or on any
representation-diverse VALID implementation incl. row-order-reversed (FP).

## PURE INVARIANT core (5 operator families)
- families: within_group_share, left_join_keep_all, cumulative_running, topn_with_ties, count_includes_empty
- recall on silent slips: **5/5**
- false-positive on intended transform: **0/5**
- false-positive on order/representation-diverse VALID impls: **0/6**
- fully clean (fire-on-slip AND pass all valid): **5/5**

## RECOMPUTATION contracts (7 operators, for contrast)
- operators: weighted_mean, pct_point, dedup_then_agg, pooled_rate, median_not_mean, nan_as_zero_sum, proportion_true
- recall 7/7, FP-correct 0/7, FP-alts 0/10

## Reading
The goldless non-circular core spans **5 operator families**, not one:
each derives no reference value yet separates the silent slip from every valid
(and row-order-diverse) implementation on the grid. within-group-share is simply
the family with a large REAL-Nature sample (538/539=99.8%); the pure-invariant
mechanism it demonstrates is shared across the family. (Grid = mechanism check,
not a generalization claim; real-data recall is Sec. Detection.)
