# Operator-taxonomy expansion — feasibility probe

Probed 12 candidate operators (goldless-contract method-viability, offline, no LLM). VIABLE = silent wrong runs + contract fires on wrong + passes on correct + 0 false-positives across alternative valid implementations.

- VIABLE (detects + FP-robust across 12 alt impls): 12/12
- VIABLE-FRAGILE (detects but false-positives on a valid variant): 0/12
- of the VIABLE, HIGH-NOVELTY (generic exec-pass/validity baselines miss it): 9/12

| id | dir | operator | silent? | fires✗ | pass✓ | FP-robust | verdict | generic baseline | non-obvious source |
|----|-----|----------|---------|--------|-------|-----------|---------|------------------|--------------------|
| D1-1 | D1 | index_align | ✓ | ✓ | ✓ | ✓ 1/1 | **VIABLE** | none (exec-pass + range both miss) | not a statistic choice — pandas aligns by index/position, not by key |
| D1-2 | D1 | dtype_coerce | ✓ | ✓ | ✓ | ✓ 1/1 | **VIABLE** | weak: a dtype-aware validity check could notice the type change | a framework cast, not a math error; classic leading-zero ID loss |
| D1-3 | D1 | groupby_dropna_key | ✓ | ✓ | ✓ | ✓ 1/1 | **VIABLE** | none (totals look fine in isolation) | groupby silently drops NaN KEYS by default (dropna=True) |
| D1-4 | D1 | order_dependent_dedup | ✓ | ✓ | ✓ | ✓ 1/1 | **VIABLE** | none | drop_duplicates keeps FIRST on UNSORTED data, not the intended latest/max |
| D1-5 | D1 | resample_boundary | ✓ | ✓ | ✓ | ✓ 1/1 | **VIABLE** | none (sum conservation holds for both — only per-bin differs) | default closed='left'/label='left' silently moves boundary points to the wrong bin |
| D1-6 | D1 | string_normalize_join | ✓ | ✓ | ✓ | ✓ 1/1 | **VIABLE** | none (NaN lookups look like genuine misses) | case/whitespace mismatch silently fails the match, not a logic error |
| D2-1 | D2 | join_fanout | ✓ | ✓ | ✓ | ✓ 1/1 | **VIABLE** | none | many-to-many join duplicates rows (SQL fan-out), the #1 silent SQL bug |
| D2-2 | D2 | null_in_agg_count | ✓ | ✓ | ✓ | ✓ 1/1 | **VIABLE** | none | COUNT(col) vs COUNT(*) NULL semantics (pandas .count skips NaN) |
| D2-3 | D2 | scale_before_split_leakage | ✓ | ✓ | ✓ | ✓ 1/1 | **VIABLE** | none (exec-pass + range both miss; this is the highest-impact case) | test stats leak into the scaler — invalidates the whole evaluation, not one cell |
| D2-4 | D2 | numpy_broadcast | ✓ | ✓ | ✓ | ✓ 1/1 | **VIABLE** | shape validity could catch it BEFORE it is aggregated to a scalar | silent broadcasting of (n,) vs (n,1), not an algorithm error |
| D2-5 | D2 | latlon_swap | ✓ | ✓ | ✓ | ✓ 1/1 | **VIABLE** | YES: a generic [-90,90] range check also catches it (lower novelty) | lat/lon order convention differs across libraries |
| D2-6 | D2 | lookahead_return | ✓ | ✓ | ✓ | ✓ 1/1 | **VIABLE** | none | uses FUTURE data (look-ahead bias) — silent and devastating in finance/forecasting |

## Per-operator evidence (wrong vs correct, as the goldless contract sees it)

### D1-1 index_align — VIABLE
- why silent: mis-paired/NaN values are plausible numbers; code runs clean
- fire on WRONG: by-key combine wrong at id(s) [1, 2, 3, 4] (positional mis-alignment / spurious NaN)
- pass on CORRECT: every id's combined value matches by-key recomputation
- honest boundary: undetectable only if result drops the key AND the value multiset coincides

### D1-2 dtype_coerce — VIABLE
- why silent: 1001 is a valid-looking number; no error on astype(int)
- fire on WRONG: identifier altered (leading-zero/precision loss), e.g. [('01001', '1001'), ('02134', '2134')]
- pass on CORRECT: identifier preserved exactly as string
- honest boundary: only matters for codes with leading zeros / >15-digit precision

### D1-3 groupby_dropna_key — VIABLE
- why silent: fewer-but-plausible group totals; no error
- fire on WRONG: total 70 < input 150: NaN-key rows silently dropped
- pass on CORRECT: group totals conserve all 150
- honest boundary: no firing if the key column has no NaN

### D1-4 order_dependent_dedup — VIABLE
- why silent: one row per id is returned; values are real rows
- fire on WRONG: kept non-latest row for id(s) [1, 2] (drop_duplicates keep=first on unsorted)
- pass on CORRECT: kept the max-order row per key
- honest boundary: needs an explicit 'which row' intent (latest/max) to define correctness

### D1-5 resample_boundary — VIABLE
- why silent: totals conserve; a normal hourly table is returned
- fire on WRONG: bin sums [3.0, 7.0] != intended [1.0, 4.0, 5.0] (wrong closed/label boundary)
- pass on CORRECT: bin sums match intended closed/label convention
- honest boundary: requires intent to pin closed/label; pure conservation cannot distinguish

### D1-6 string_normalize_join — VIABLE
- why silent: a left join returns all rows; missing prices are just NaN
- fire on WRONG: NaN lookup for key(s) ['Apple ', 'CHERRY'] that DO match after normalization
- pass on CORRECT: all normalizable keys matched
- honest boundary: cannot tell intended-miss from normalization-miss without a normalization rule

### D2-1 join_fanout — VIABLE
- why silent: a clean per-cat total; just numerically inflated
- fire on WRONG: measure total 1000 != pre-join 600: join fan-out duplicated rows
- pass on CORRECT: additive measure conserved (600)
- honest boundary: only additive left-measures; counts/ratios need a different invariant

### D2-2 null_in_agg_count — VIABLE
- why silent: smaller counts that look like real group sizes
- fire on WRONG: record count != group size for ['A', 'B']: COUNT(col) dropped NULL rows
- pass on CORRECT: per-group count equals group size
- honest boundary: no firing if the counted column has no NULLs

### D2-3 scale_before_split_leakage — VIABLE
- why silent: model trains/scores fine; ONLY the held-out score is silently optimistic
- fire on WRONG: train slice mean=-0.998 != 0 (std=0.056): scaled with GLOBAL stats (test leaked into fit)
- pass on CORRECT: train slice mean=0.000 (~0), std=1.000: fit on train, no leakage
- honest boundary: only OBSERVABLE when train/test distributions differ — but that is exactly when it biases results

### D2-4 numpy_broadcast — VIABLE
- why silent: downstream .mean() of the (n,n) array is a plausible scalar
- fire on WRONG: result shape (4, 4) (size 16) != length-4: silent broadcast
- pass on CORRECT: result is length-4 vector as intended
- honest boundary: once reduced to a scalar the shape evidence is gone; catch it at the array step

### D2-5 latlon_swap — VIABLE
- why silent: points still plot; just in the wrong place
- fire on WRONG: latitude out of [-90,90]: [139.7, 151.2] (lat/lon swapped)
- pass on CORRECT: latitude within [-90,90]
- honest boundary: undetectable when all true longitudes also fall within [-90,90]

### D2-6 lookahead_return — VIABLE
- why silent: a normal-looking return column; backtests just look too good
- fire on WRONG: return uses FUTURE price (look-ahead leakage)
- pass on CORRECT: return uses PAST price (no look-ahead)
- honest boundary: constant-growth series make past==future returns; needs varying returns to expose
