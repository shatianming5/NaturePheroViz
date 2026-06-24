"""
plot_trace.py — execution-traced fidelity capture (PlotTrace, P0).

The core wedge of "silent-error self-repair": because we control the plotting
code's execution, we can monkeypatch matplotlib's Artist-producing methods
(ax.bar / ax.plot / ax.scatter / ...) and capture the EXACT arrays the code
passed to them — the post-transform / pre-render data. No reading-back from
SVG/pixels, no VLM, no geometric error.

The captured trace is a list of (series, x, value) rows that can be diffed,
keyed by (series, x), against the ground-truth table — exactly the interface
fidelity_verifier._safe_match already expects.

Usage (in-process or injected at the top of a scaffold's run()):

    from plot_trace import PlotTracer
    tracer = PlotTracer()
    with tracer.install():
        # ... user/agent plotting code runs, calling ax.bar/plot/... ...
        fig.savefig(...)
    tracer.dump_csv("figure.trace.csv")   # series,x,value
    rows = tracer.rows                      # list[dict]

Design notes:
- We patch the unbound methods on matplotlib.axes.Axes, so EVERY axes (incl.
  twinx right axes, subplots) is covered by one install.
- We record BEFORE calling the original, capturing the literal call arguments;
  then we always call through so rendering is unaffected.
- Series labels come from the `label=` kwarg when present (that's what the
  legend uses), else a per-method running index ("plot#0", "bar#1", ...).
- We coerce pandas Series / numpy arrays / lists / scalars uniformly and keep
  the x categories as strings (matching fidelity_verifier's keying).
- Failure is non-fatal: if a single call can't be parsed we record nothing for
  it and let the real draw proceed. Tracing must never break the figure.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


# ----------------------------------------------------------------------------
# Coercion helpers (no hard pandas/numpy dependency at import time)
# ----------------------------------------------------------------------------


def _to_list(v: Any) -> Optional[List[Any]]:
    """Best-effort convert a plotting argument to a flat python list."""
    if v is None:
        return None
    # pandas Series / Index / numpy array expose .tolist()
    tolist = getattr(v, "tolist", None)
    if callable(tolist):
        try:
            out = tolist()
            return out if isinstance(out, list) else [out]
        except Exception:
            pass
    if isinstance(v, (list, tuple)):
        return list(v)
    # scalar
    if isinstance(v, (int, float, str, bool)):
        return [v]
    # last resort: try iterating
    try:
        return list(v)
    except Exception:
        return None


def _to_float(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return float(int(v))
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        try:
            return float(s)
        except ValueError:
            return None
    # numpy scalar
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------
# Tracer
# ----------------------------------------------------------------------------

# (method name, x-arg index, y-arg index) for the Axes methods we trace.
# For methods where the "value" is the second positional arg this is (0, 1).
_TRACED_SIGNATURES: Dict[str, Tuple[int, int]] = {
    "bar": (0, 1),          # bar(x, height)
    "barh": (1, 0),         # barh(y, width) -> categories are y, value is width
    "plot": (0, 1),         # plot(x, y)  (simplest form; see _parse_plot)
    "scatter": (0, 1),      # scatter(x, y)
    "fill_between": (0, 2),  # fill_between(x, y1=0, y2) -> value is y2 (idx 2)
    "step": (0, 1),
}


class PlotTracer:
    """Monkeypatches matplotlib Axes drawing methods to capture input arrays."""

    def __init__(self) -> None:
        # Final resolved rows: {series, x, value, axis}
        self.rows: List[Dict[str, Any]] = []
        # Raw captured records before tick-based category resolution:
        #   {series, x_raw, x_is_numeric, value, ax}
        self._pending: List[Dict[str, Any]] = []
        self._counters: Dict[str, int] = {}
        self._originals: Dict[str, Callable] = {}
        self._installed = False
        self._resolved = False

    # -- recording -----------------------------------------------------------

    def _next_series(self, method: str, label: Optional[str]) -> str:
        if isinstance(label, str) and label.strip() and not label.startswith("_"):
            return label.strip()
        idx = self._counters.get(method, 0)
        self._counters[method] = idx + 1
        return f"{method}#{idx}"

    def _record_xy(self, method: str, x_arg: Any, y_arg: Any, label: Optional[str], ax: Any = None) -> None:
        xs = _to_list(x_arg)
        ys = _to_list(y_arg)
        if ys is None:
            return
        # plot(y) with no x: matplotlib uses range(len(y))
        if xs is None:
            xs = list(range(len(ys)))
        series = self._next_series(method, label)
        n = min(len(xs), len(ys))
        for i in range(n):
            val = _to_float(ys[i])
            if val is None:
                continue
            xv = xs[i]
            x_num = _to_float(xv)  # numeric x (possibly a grouped-bar offset) or None for true categoricals
            self._pending.append({
                "series": series,
                "x_raw": str(xv),
                "x_num": x_num,
                "value": val,
                "ax": ax,
            })

    def _parse_plot(self, args: Sequence[Any], label: Optional[str], ax: Any = None) -> None:
        """plot has flexible signatures: plot(y), plot(x,y), plot(x,y,fmt),
        plot(x1,y1,fmt1,x2,y2,fmt2,...). Handle the common cases."""
        # strip a trailing/interleaved format string like 'r--'
        positional = [a for a in args if not (isinstance(a, str))]
        if len(positional) == 1:
            self._record_xy("plot", None, positional[0], label, ax)
        elif len(positional) >= 2:
            # take pairs (x,y),(x,y),...
            i = 0
            while i + 1 < len(positional) + 1 and i + 1 <= len(positional) - 1:
                self._record_xy("plot", positional[i], positional[i + 1], label, ax)
                i += 2

    def _make_wrapper(self, method: str, original: Callable, x_idx: int, y_idx: int) -> Callable:
        tracer = self

        def wrapper(ax_self, *args, **kwargs):
            # record first (best-effort), then always call through
            try:
                # Skip decoration / reference artists that are NOT data:
                #  - transform= (axes/figure-fraction coords, e.g. broken-axis marks)
                #  - clip_on=False overlays, and explicit non-legend helper lines
                label = kwargs.get("label")
                is_decoration = (
                    "transform" in kwargs
                    or kwargs.get("clip_on") is False
                    or (isinstance(label, str) and label == "_nolegend_")
                )
                if is_decoration:
                    return original(ax_self, *args, **kwargs)
                if method == "plot":
                    tracer._parse_plot(args, label, ax_self)
                else:
                    x_arg = args[x_idx] if len(args) > x_idx else kwargs.get("x")
                    y_arg = args[y_idx] if len(args) > y_idx else (
                        kwargs.get("height") if method == "bar"
                        else kwargs.get("width") if method == "barh"
                        else kwargs.get("y2") if method == "fill_between"
                        else kwargs.get("y")
                    )
                    tracer._record_xy(method, x_arg, y_arg, label, ax_self)
            except Exception:
                pass  # tracing must never break rendering
            return original(ax_self, *args, **kwargs)

        wrapper.__name__ = getattr(original, "__name__", method)
        return wrapper

    # -- install / restore ---------------------------------------------------

    @contextmanager
    def install(self):
        import matplotlib.axes

        Axes = matplotlib.axes.Axes
        for method, (x_idx, y_idx) in _TRACED_SIGNATURES.items():
            original = getattr(Axes, method, None)
            if original is None:
                continue
            self._originals[method] = original
            setattr(Axes, method, self._make_wrapper(method, original, x_idx, y_idx))
        self._installed = True
        try:
            yield self
        finally:
            for method, original in self._originals.items():
                setattr(Axes, method, original)
            self._originals.clear()
            self._installed = False
            # Resolve categories while the axes are still alive (ticks are lazy;
            # they're reliable now that drawing calls have happened but before
            # the caller closes the figure).
            self.resolve_categories()

    # -- category resolution (tick-based) ------------------------------------

    def resolve_categories(self) -> None:
        """Map captured numeric x (possibly grouped-bar offsets) back to the
        axis's category tick labels, and tag each row with its axis id (so twin
        axes are separated). Idempotent; safe to call once at install exit.

        Strategy: for each axes, read get_xticks()/get_xticklabels(). If the
        tick labels are non-numeric categories (Jan/Feb/...), snap each row's
        numeric x to the NEAREST tick position and adopt that tick's label.
        If labels are numeric or unavailable, keep the raw x.
        """
        if self._resolved:
            return
        # group pending rows by axes object
        ax_axisid: Dict[int, int] = {}
        ax_tickmap: Dict[int, Optional[List[Tuple[float, str]]]] = {}
        next_axis = 0
        for rec in self._pending:
            ax = rec.get("ax")
            key = id(ax) if ax is not None else 0
            if key not in ax_axisid:
                ax_axisid[key] = next_axis
                next_axis += 1
                ax_tickmap[key] = self._tick_label_map(ax)

        for rec in self._pending:
            ax = rec.get("ax")
            key = id(ax) if ax is not None else 0
            ticks = ax_tickmap.get(key)
            x_out = rec["x_raw"]
            if ticks and rec["x_num"] is not None:
                # snap numeric x to nearest tick position, adopt its label
                best_label = None
                best_d = None
                for pos, lab in ticks:
                    d = abs(rec["x_num"] - pos)
                    if best_d is None or d < best_d:
                        best_d = d
                        best_label = lab
                if best_label is not None:
                    x_out = best_label
            self.rows.append({
                "series": rec["series"],
                "x": x_out,
                "value": rec["value"],
                "axis": ax_axisid[key],
            })
        self._resolved = True

    @staticmethod
    def _tick_label_map(ax: Any) -> Optional[List[Tuple[float, str]]]:
        """Return [(tick_pos, label_text), ...] for an axis IF the labels are
        meaningful non-numeric categories; else None (keep raw numeric x)."""
        if ax is None:
            return None
        try:
            positions = list(ax.get_xticks())
            labels = [t.get_text() for t in ax.get_xticklabels()]
        except Exception:
            return None
        pairs: List[Tuple[float, str]] = []
        non_numeric = 0
        for pos, lab in zip(positions, labels):
            lab = (lab or "").strip()
            if not lab:
                continue
            pairs.append((float(pos), lab))
            if _to_float(lab) is None:
                non_numeric += 1
        # Only treat as categorical if most tick labels are non-numeric text.
        if pairs and non_numeric >= max(1, len(pairs) // 2):
            return pairs
        return None

    # -- output --------------------------------------------------------------

    def to_records(self) -> List[Dict[str, Any]]:
        if not self._resolved:
            self.resolve_categories()
        return list(self.rows)

    def dump_csv(self, path: str) -> None:
        import csv

        if not self._resolved:
            self.resolve_categories()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["series", "x", "value", "axis"])
            w.writeheader()
            for r in self.rows:
                w.writerow(r)

    def dump_jsonl(self, path: str) -> None:
        if not self._resolved:
            self.resolve_categories()
        with open(path, "w", encoding="utf-8") as f:
            for r in self.rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ----------------------------------------------------------------------------
# Self-test: prove captured arrays == input arrays (the make-or-break check)
# ----------------------------------------------------------------------------

def _selftest() -> int:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    failures = []

    # Case 1: simple bar — captured values must equal input heights exactly.
    df = pd.DataFrame({"month": ["Jan", "Feb", "Mar"], "sales": [120.0, 130.0, 90.0]})
    tracer = PlotTracer()
    with tracer.install():
        fig, ax = plt.subplots()
        ax.bar(df["month"], df["sales"], label="sales")
        fig.savefig("/tmp/_pt_bar.png")
    plt.close("all")
    got = {(r["x"], r["value"]) for r in tracer.rows}
    want = {("Jan", 120.0), ("Feb", 130.0), ("Mar", 90.0)}
    if got != want:
        failures.append(f"bar: got {got} want {want}")

    # Case 2: multi-line plot — two series, labels preserved, values exact.
    df2 = pd.DataFrame({"x": [1, 2, 3], "a": [10.0, 20.0, 30.0], "t": [15.0, 25.0, 35.0]})
    tracer2 = PlotTracer()
    with tracer2.install():
        fig, ax = plt.subplots()
        ax.plot(df2["x"], df2["a"], label="actual")
        ax.plot(df2["x"], df2["t"], label="target")
        fig.savefig("/tmp/_pt_line.png")
    plt.close("all")
    by_series = {}
    for r in tracer2.rows:
        by_series.setdefault(r["series"], []).append(r["value"])
    if by_series.get("actual") != [10.0, 20.0, 30.0]:
        failures.append(f"plot actual: {by_series.get('actual')}")
    if by_series.get("target") != [15.0, 25.0, 35.0]:
        failures.append(f"plot target: {by_series.get('target')}")

    # Case 3: twin axis (right axis) — must also be captured by one install.
    df3 = pd.DataFrame({"m": ["A", "B"], "sales": [100.0, 200.0], "rate": [0.1, 0.2]})
    tracer3 = PlotTracer()
    with tracer3.install():
        fig, axl = plt.subplots()
        axl.bar(df3["m"], df3["sales"], label="sales")
        axr = axl.twinx()
        axr.plot(df3["m"], df3["rate"], label="rate")
        fig.savefig("/tmp/_pt_twin.png")
    plt.close("all")
    svals = {(r["series"], r["x"], r["value"]) for r in tracer3.rows}
    if ("rate", "A", 0.1) not in svals or ("sales", "B", 200.0) not in svals:
        failures.append(f"twin: {svals}")

    # Case 4: THE money case — a "silent error". Truth says 130k, code draws 90k.
    # The tracer must report 90k (what was drawn), so a diff vs truth flags it.
    truth = {"Feb": 130000.0}
    tracer4 = PlotTracer()
    with tracer4.install():
        fig, ax = plt.subplots()
        ax.bar(["Jan", "Feb"], [120000.0, 90000.0], label="sales")  # Feb is wrong
        fig.savefig("/tmp/_pt_silent.png")
    plt.close("all")
    drawn_feb = next((r["value"] for r in tracer4.rows if r["x"] == "Feb"), None)
    if drawn_feb != 90000.0:
        failures.append(f"silent-error: drawn Feb={drawn_feb}, expected captured 90000")
    else:
        # demonstrate the diff that fidelity_verifier would compute
        diff = abs(drawn_feb - truth["Feb"])
        print(f"[selftest] silent-error captured: drawn Feb={drawn_feb}, truth={truth['Feb']}, |diff|={diff} -> WOULD FLAG wrong_value")

    # Case 5: GROUPED bar with offset x (the real-run alignment gap).
    # Code draws two series at x = arange(n)+0/+0.4, with categorical xticklabels.
    # The tracer must snap the offset x back to the original categories.
    import numpy as np
    cats = ["Q1", "Q2", "Q3"]
    a_vals = [10.0, 20.0, 30.0]
    b_vals = [11.0, 21.0, 31.0]
    tracer5 = PlotTracer()
    with tracer5.install():
        fig, ax = plt.subplots()
        xpos = np.arange(len(cats))
        ax.bar(xpos - 0.2, a_vals, width=0.4, label="A")
        ax.bar(xpos + 0.2, b_vals, width=0.4, label="B")
        ax.set_xticks(xpos)
        ax.set_xticklabels(cats)
        fig.savefig("/tmp/_pt_grouped.png")
    plt.close("all")
    grouped = {(r["series"], r["x"], r["value"]) for r in tracer5.rows}
    want5 = {("A", "Q1", 10.0), ("A", "Q3", 30.0), ("B", "Q1", 11.0), ("B", "Q2", 21.0)}
    missing5 = want5 - grouped
    if missing5:
        failures.append(f"grouped-bar offset->category: missing {missing5} (got {grouped})")
    else:
        print(f"[selftest] grouped-bar: offset x {{-0.2,0.2,...}} correctly snapped to categories Q1/Q2/Q3")

    # Case 6: twinx axis separation — left bar (sales) and right line (rate) must
    # land on DIFFERENT axis ids so a verifier can keep the series apart.
    df6 = pd.DataFrame({"m": ["A", "B"], "sales": [100.0, 200.0], "rate": [0.1, 0.2]})
    tracer6 = PlotTracer()
    with tracer6.install():
        fig, axl = plt.subplots()
        axl.bar(df6["m"], df6["sales"], label="sales")
        axr = axl.twinx()
        axr.plot(df6["m"], df6["rate"], label="rate")
        fig.savefig("/tmp/_pt_twin2.png")
    plt.close("all")
    sales_axis = {r["axis"] for r in tracer6.rows if r["series"] == "sales"}
    rate_axis = {r["axis"] for r in tracer6.rows if r["series"] == "rate"}
    if not sales_axis or not rate_axis or sales_axis == rate_axis:
        failures.append(f"twinx axis separation: sales_axis={sales_axis} rate_axis={rate_axis} (should differ)")
    else:
        print(f"[selftest] twinx: sales on axis {sales_axis}, rate on axis {rate_axis} — separated")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print("  -", f)
        return 1
    print("SELFTEST PASSED: all 6 cases — capture + tick-based category alignment + twinx separation")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
