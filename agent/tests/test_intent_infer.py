"""Guards for the W3 NL->(op,params) inferer feeding the goldless oracle."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from eval.transform_intent_infer import infer, infer_op
from eval.transform_bench import _cases
from eval.transform_oracle import check


def test_keyword_and_schema_ops():
    assert infer("The MEDIAN of v per group", pd.DataFrame({"g": ["a"], "v": [1]}))[0] == "median_not_mean"
    # schema disambiguation: terse 'total per region' + id col -> dedup
    df = pd.DataFrame({"region": ["N"], "order_id": [1], "rev": [5]})
    assert infer_op_or_schema("Total revenue per region.", df) == "dedup_then_agg"


def infer_op_or_schema(p, df):
    op, _ = infer(p, df)
    return op


def test_grid_op_accuracy_full():
    # NOTE: 68/68 is a co-designed upper bound — signals were written to the grid
    # lexicon; this guards regressions, not generalization (see master_table row 11).
    cases = _cases()
    ok = sum(infer(c["ambiguous"], c["df"], c.get("df2"))[0] == c["op"] for c in cases)
    assert ok == len(cases)  # 68/68 on the templated grid


def test_no_false_fire_with_inferred_params():
    for c in _cases():
        op, P = infer(c["ambiguous"], c["df"], c.get("df2"))
        inp = {"df": c["df"], **({"df2": c["df2"]} if "df2" in c else {})}
        g = c["gold"](c["df"], c["df2"]) if "df2" in c else c["gold"](c["df"])
        g = g if isinstance(g, pd.DataFrame) else pd.DataFrame({"wavg": [float(g)]})
        r = check(op, inp, P, g)
        assert not (r and r.fired), f"{op} false-fired on gold"
