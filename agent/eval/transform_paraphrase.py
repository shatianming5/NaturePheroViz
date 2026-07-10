"""
transform_paraphrase.py — honest generalization test for the NL inferer. The 68
grid uses templated prompts, so 100% op-acc there is co-designed. This is a
HELD-OUT set: each op gets 2 fresh paraphrases with DIFFERENT wording + different
column names, never matching the grid lexicon. Measures real op-accuracy + abstain.
Run: cd agent && python eval/transform_paraphrase.py
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from eval.transform_intent_infer import infer_op

P = pd.DataFrame
# (op, prompt, df) — wording deliberately off-lexicon
CASES = [
    ("weighted_mean", "Mean unit cost, accounting for units shipped.", P({"sku":["a"],"cost":[2.0],"units":[3]})),
    ("weighted_mean", "Average exam grade weighted by credit hours.", P({"c":["x"],"grade":[90.0],"credits":[4]})),
    ("within_group_share", "Each employee's fraction of their department's payroll.", P({"dept":["A"],"emp":["e"],"pay":[10]})),
    ("within_group_share", "Portion of regional sales held by each store.", P({"region":["N"],"store":["s"],"sales":[5]})),
    ("pct_point", "Lift in conversion from before to after, in points.", P({"team":["t"],"before":[0.2],"after":[0.3]})),
    ("pooled_rate", "Overall success rate per cohort = total wins / total attempts.", P({"cohort":["c"],"wins":[1],"tries":[10]})),
    ("median_not_mean", "Central salary per team.", P({"grp":["g"],"v":[5.0]})),
    ("nan_as_zero_sum", "Sum amounts per group; blanks count as zero.", P({"grp":["g"],"v":[np.nan]})),
    ("dedup_then_agg", "Sum revenue per store; invoices repeat.", P({"store":["s"],"order_id":[1],"rev":[5]})),
    ("left_join_keep_all", "Attach rating from df2; keep products with no rating.", P({"id":[1],"name":["n"]})),
    ("cumulative_running", "Account balance accumulating over time.", P({"day":[1],"delta":[5]})),
    ("cumcount_per_group", "Nth visit index per customer.", P({"user":["u"],"event":["e"]})),
    ("topn_with_ties", "Best 2 by score, keep all ties.", P({"name":["a"],"score":[9]})),
    ("count_includes_empty", "Tally per bucket including empty ones.", P({"cat":pd.Categorical(["a"],["a","b"]),"v":[1]})),
    ("proportion_true", "Share of yes per class.", P({"cls":["x"],"passed":[True]})),
    ("zscore_within_group", "Standardize values inside each lab.", P({"batch":["b"],"value":[3.0]})),
    ("dense_rank", "Rank, ties share a rank, no gaps.", P({"team":["t"],"pts":[9]})),
    ("rank_pct", "Percentile position of elo.", P({"player":["p"],"elo":[1200]})),
    ("clip_outlier", "Cap reading to 0..100.", P({"sensor":["s"],"reading":[5.0]})),
]

ok=ab=wr=0
for op, prompt, df in CASES:
    g=infer_op(prompt)
    if g==op: ok+=1
    elif g is None: ab+=1
    else: wr+=1; print(f"  WRONG {op} -> {g}: {prompt}")
n=len(CASES)
print(f"\nheld-out paraphrases N={n}: correct {ok} ({round(100*ok/n)}%), abstain {ab}, miswired {wr}")
print("(grid was 100% by co-design; this off-lexicon set is the honest generalization number)")
