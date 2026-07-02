"""Cross-domain (SQL substrate) contract test — offline, deterministic.

Locks in the W6 result: the SAME goldless operator contracts (written for pandas) fire on
SQL silent slips and pass on correct SQL, with zero SQL-specific contract code. Uses
sqlite3 from the stdlib, so it needs no network and no API.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.crossdomain_sql import run  # noqa: E402


def test_contracts_transfer_to_sql_substrate():
    recs = run()
    assert recs, "no cross-domain cases ran"
    # every operator's contract must fire on the SQL slip and pass on the correct SQL
    for r in recs:
        assert r["fired_on_slip"] is True, f"{r['op']}: contract did NOT fire on the SQL slip"
        assert r["fired_on_correct"] is False, f"{r['op']}: contract false-fired on correct SQL"
    assert all(r["ok"] for r in recs), "some operators failed cross-domain transfer"
