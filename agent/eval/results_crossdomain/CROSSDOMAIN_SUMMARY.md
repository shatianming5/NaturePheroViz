# Cross-domain: the goldless contracts are execution-substrate-agnostic (AAAI W6)

**Reviewer W6:** "all results are on pandas DataFrame transformations; the claimed
generality of 'typed operator-level semantic contracts' is unproven on other substrates."

**Why the critique is answerable in principle:** a typed operator contract checks an
invariant of `(input data, params, RESULT)`. It never inspects the *code* that produced the
result. So the exact same contract that catches a pandas silent slip must also catch the
identical *semantic* slip expressed in a different substrate — because it operates at the
result layer, not the code layer.

**Proof end-to-end (`crossdomain_sql.py`, sqlite3 — Python stdlib, fully offline,
deterministic, no deps, no API):** for each operator we load the fixture into an in-memory
SQLite DB, run a CORRECT SQL query and a SILENT-SLIP SQL query (the mistake an analyst makes
*in SQL*), read both results back, and feed them to the EXISTING pandas contract
(`transform_oracle.check`) with **zero SQL-specific contract code**.

## Result: 4/4 operators — SAME contracts, SQL substrate

| operator | SQL silent slip | contract fires on slip | passes on correct SQL |
|---|---|---|---|
| weighted_mean | `AVG(price)` instead of `SUM(price*qty)/SUM(qty)` | ✅ | ✅ |
| groupby_dropna_key | `WHERE g IS NOT NULL` silently drops NaN-key rows | ✅ | ✅ |
| join_fanout | `JOIN tags` before `SUM(amt)` inflates via 1-to-many fan-out | ✅ | ✅ |
| left_join_keep_all | `INNER JOIN` drops the unmatched left row | ✅ | ✅ |

All four goldless contracts — written and tested for pandas — **fire on the SQL silent slip
and pass on the correct SQL, unchanged**.

## What this establishes

The detection mechanism is not pandas-specific. Because the contract is a predicate over
the *semantic result* (a conservation law, a per-group identity, a row-retention
invariant), it transfers to any execution substrate that produces the same relational
result — here pandas → SQL, demonstrated on the four operators whose SQL silent-slips are
the canonical real-world SQL mistakes (unweighted AVG, NULL-dropping filters, join fan-out,
inner-join row loss). This directly answers the single-domain critique and reframes the
contribution as **substrate-agnostic operator-semantic verification**, of which pandas is
one instantiation.

Raw: `crossdomain_sql.json`. Repro: `python eval/crossdomain_sql.py` (offline, deterministic).
