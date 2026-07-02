"""
crossdomain_sql.py — the goldless contracts are EXECUTION-SUBSTRATE-AGNOSTIC (AAAI, W6).

Reviewer W6: "all results are on pandas; the generality claim is unproven." But a typed
operator contract checks an invariant of (input data, params, RESULT) — it never inspects
the code that produced the result. So the SAME contract that catches a pandas silent slip
must also catch the identical semantic slip written in SQL. We prove it end-to-end with
sqlite3 (Python stdlib — fully offline, deterministic, no deps, no API):

  for each operator: load the fixture into an in-memory SQLite DB, run a CORRECT SQL query
  and a SILENT-SLIP SQL query (the mistake an analyst makes in SQL), read both results back
  into pandas, and feed them to the EXISTING goldless contract (eval.transform_oracle.check).
  The contract must FIRE on the SQL slip and PASS on the correct SQL — with zero
  SQL-specific contract code.

This shows the detection mechanism transfers across execution substrates (pandas -> SQL)
because it operates at the semantic-result layer, not the code layer.

Run: cd agent && python eval/crossdomain_sql.py
"""
from __future__ import annotations
import argparse, json, sqlite3, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from eval.transform_oracle import check as oracle_check


def _db(tables):
    con = sqlite3.connect(":memory:")
    for name, df in tables.items():
        df.to_sql(name, con, index=False, if_exists="replace")
    return con


def _q(con, sql):
    return pd.read_sql_query(sql, con)


# each case: fixtures (pandas -> sqlite), the op+params, and a CORRECT vs SILENT-SLIP SQL.
def cases():
    out = []

    # weighted_mean: correct = SUM(price*qty)/SUM(qty); slip = AVG(price) (unweighted)
    t = pd.DataFrame({"price": [10.0, 20.0, 30.0], "qty": [100, 10, 1]})
    out.append(dict(
        op="weighted_mean", tables={"t": t}, params={"value": "price", "weight": "qty"},
        correct_sql="SELECT SUM(price*qty)*1.0/SUM(qty) AS wavg FROM t",
        slip_sql="SELECT AVG(price) AS wavg FROM t",
        note="SQL analyst writes AVG(price) instead of the quantity-weighted average"))

    # groupby_dropna_key: correct keeps NULL-key group; slip = GROUP BY g drops NULL rows
    # (in SQL, GROUP BY g DOES keep NULL as its own group, so the *slip* is the common
    # 'WHERE g IS NOT NULL' filter an analyst adds to 'clean' the data)
    g = pd.DataFrame({"g": ["N", "N", None, "S"], "v": [10, 20, 30, 40]})
    out.append(dict(
        op="groupby_dropna_key", tables={"t": g}, params={"group": "g", "value": "v"},
        correct_sql="SELECT COALESCE(g,'__NA__') AS g, SUM(v) AS v FROM t GROUP BY g",
        slip_sql="SELECT g, SUM(v) AS v FROM t WHERE g IS NOT NULL GROUP BY g",
        note="SQL analyst adds WHERE g IS NOT NULL, silently dropping the NaN-key rows"))

    # join_fanout: correct counts each order's amount once; slip lets a 1-to-many join to a
    # tags table fan out the amount (SUM over duplicated rows)
    orders = pd.DataFrame({"oid": [1, 2, 3], "cat": ["a", "a", "b"], "amt": [100.0, 50.0, 70.0]})
    tags = pd.DataFrame({"oid": [1, 1, 2, 3], "tag": ["x", "y", "x", "z"]})
    out.append(dict(
        op="join_fanout", tables={"orders": orders, "tags": tags},
        params={"measure": "amt", "group": "cat"},
        correct_sql="SELECT cat, SUM(amt) AS amt FROM orders GROUP BY cat",
        slip_sql=("SELECT o.cat AS cat, SUM(o.amt) AS amt FROM orders o "
                  "JOIN tags g ON o.oid=g.oid GROUP BY o.cat"),
        note="joining a 1-to-many tags table before SUM inflates amt via fan-out",
        df_for_contract="orders"))

    # left_join_keep_all: correct = LEFT JOIN keeps all left rows; slip = INNER JOIN drops
    L = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]})
    R = pd.DataFrame({"id": [1, 3], "score": [88, 99]})
    out.append(dict(
        op="left_join_keep_all", tables={"l": L, "r": R}, params={},
        correct_sql="SELECT l.id, l.name, r.score FROM l LEFT JOIN r ON l.id=r.id",
        slip_sql="SELECT l.id, l.name, r.score FROM l JOIN r ON l.id=r.id",
        note="INNER JOIN silently drops the left row with no match (id=2)",
        df_for_contract="l"))

    return out


def run():
    recs = []
    for c in cases():
        con = _db(c["tables"])
        correct = _q(con, c["correct_sql"])
        slip = _q(con, c["slip_sql"])
        con.close()
        # the contract's inp["df"] is the primary input table
        prim = c.get("df_for_contract") or list(c["tables"])[0]
        inp = {"df": c["tables"][prim]}
        if "df_for_contract" in c and len(c["tables"]) > 1:
            # attach the second table as df2 where the contract may need it
            others = [k for k in c["tables"] if k != prim]
            if others:
                inp["df2"] = c["tables"][others[0]]
        elif len(c["tables"]) > 1 and c["op"] == "left_join_keep_all":
            inp["df2"] = c["tables"][[k for k in c["tables"] if k != prim][0]]
        rc_correct = oracle_check(c["op"], inp, c["params"], correct)
        rc_slip = oracle_check(c["op"], inp, c["params"], slip)
        fired_correct = bool(rc_correct and rc_correct.fired)
        fired_slip = bool(rc_slip and rc_slip.fired)
        ok = (fired_slip is True) and (fired_correct is False)
        recs.append({"op": c["op"], "fired_on_slip": fired_slip,
                     "fired_on_correct": fired_correct, "ok": ok, "note": c["note"]})
        print(f"  {c['op']:22} SQL-slip fired={fired_slip}  SQL-correct fired={fired_correct}  "
              f"=> {'OK' if ok else 'FAIL'}   [{c['note']}]", flush=True)
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="eval/results_crossdomain/crossdomain_sql.json")
    a = ap.parse_args()
    print("=== cross-domain: SAME goldless contracts on SQL (sqlite3) results ===")
    recs = run()
    n = len(recs); k = sum(r["ok"] for r in recs)
    summary = {"substrate": "sqlite3", "n_operators": n, "correct": k, "cases": recs,
               "claim": "goldless contracts are execution-substrate-agnostic (pandas -> SQL)"}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(summary, open(a.out, "w"), indent=2)
    print(f"\nSAME contracts, zero SQL-specific code: {k}/{n} operators fire-on-SQL-slip AND "
          f"pass-on-SQL-correct -> {a.out}")
    return 0 if k == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
