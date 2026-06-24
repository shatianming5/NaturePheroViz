"""
metrics.py — aggregate benchmark results into a "systems × metrics" table (B3).

Scans results/<system>/<task_id>/record.json files and produces:
  1. Main comparison table (CSV + Markdown)
  2. Per-system stats: exec-pass rate, mean data_fidelity, visual_form, pass@k
  3. Optional: per-task breakdown table

Usage:
  cd agent
  python eval/metrics.py --results eval/results_bench
  python eval/metrics.py --results eval/results_bench --pass-k 3 --out eval/results_bench/aggregate
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


def _collect_records(results_root: Path) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Walk results/<system>/<task_id>/record.json and collect all records.

    Returns: {system_name: {task_id: record_dict}}
    """
    all_records: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    if not results_root.exists():
        return dict(all_records)

    for system_dir in sorted(results_root.iterdir()):
        if not system_dir.is_dir():
            continue
        system_name = system_dir.name
        for task_dir in sorted(system_dir.iterdir()):
            if not task_dir.is_dir():
                continue
            rec_path = task_dir / "record.json"
            if not rec_path.exists():
                continue
            try:
                record = json.loads(rec_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            task_id = record.get("task_id", task_dir.name)
            all_records[system_name][task_id] = record

    return dict(all_records)


def _compute_system_stats(
    records: Dict[str, Dict[str, Any]], pass_k: int = 1
) -> Dict[str, Any]:
    """Compute aggregate stats for one system's records."""
    tasks = list(records.values())
    n = len(tasks)
    if n == 0:
        return {"n": 0}

    exec_pass_count = sum(1 for t in tasks if t.get("exec_pass"))
    exec_pass_rate = exec_pass_count / n

    # data_fidelity: only for tasks that passed
    fids = [
        t.get("scores", {}).get("data_fidelity", 0.0)
        for t in tasks
        if t.get("exec_pass")
    ]
    mean_fid = float(np.mean(fids)) if fids else 0.0
    median_fid = float(np.median(fids)) if fids else 0.0

    # visual_form
    vfs = [
        t.get("scores", {}).get("visual_form", 0.0)
        for t in tasks
    ]
    mean_vf = float(np.mean(vfs)) if vfs else 0.0

    # series_cohesion
    scs = [
        t.get("scores", {}).get("series_cohesion", 0.0)
        for t in tasks
    ]
    mean_sc = float(np.mean(scs)) if scs else 0.0

    # rounds_used
    rounds = [
        t.get("rounds_used", 1)
        for t in tasks
        if t.get("exec_pass")
    ]
    mean_rounds = float(np.mean(rounds)) if rounds else 0.0

    # pass@k: fraction of tasks where at least 1 of k runs passes
    # For now, pass@1 = exec_pass_rate (single run per task)
    # In future with multiple runs per task, this would be different
    pass_at_1 = exec_pass_rate
    pass_at_k = pass_at_1  # placeholder; need multiple runs to compute real pass@k

    # fidelity distribution
    fid_bins = {"fid_0_25": 0, "fid_25_50": 0, "fid_50_75": 0, "fid_75_100": 0}
    for f in fids:
        if f < 0.25:
            fid_bins["fid_0_25"] += 1
        elif f < 0.50:
            fid_bins["fid_25_50"] += 1
        elif f < 0.75:
            fid_bins["fid_50_75"] += 1
        else:
            fid_bins["fid_75_100"] += 1

    return {
        "n": n,
        "exec_pass": exec_pass_count,
        "exec_pass_rate": round(exec_pass_rate, 4),
        "mean_data_fidelity": round(mean_fid, 4),
        "median_data_fidelity": round(median_fid, 4),
        "mean_visual_form": round(mean_vf, 4),
        "mean_series_cohesion": round(mean_sc, 4),
        "mean_rounds_used": round(mean_rounds, 2),
        f"pass@{pass_k}": round(pass_at_k, 4),
        "fidelity_distribution": fid_bins,
    }


def _build_main_table(
    all_records: Dict[str, Dict[str, Dict[str, Any]]], pass_k: int = 1
) -> pd.DataFrame:
    """Build the main 'systems × metrics' DataFrame."""
    rows = []
    for system_name in sorted(all_records.keys()):
        stats = _compute_system_stats(all_records[system_name], pass_k)
        if stats.get("n", 0) == 0:
            continue
        row = {"system": system_name, "tasks": stats["n"]}
        row["exec_pass_rate"] = f"{stats['exec_pass']}/{stats['n']} ({stats['exec_pass_rate']:.1%})"
        row["data_fidelity"] = f"{stats['mean_data_fidelity']:.3f}"
        row["visual_form"] = f"{stats['mean_visual_form']:.3f}"
        row["series_cohesion"] = f"{stats['mean_series_cohesion']:.3f}"
        row["rounds"] = f"{stats['mean_rounds_used']:.1f}"
        row[f"pass@{pass_k}"] = f"{stats[f'pass@{pass_k}']:.3f}"
        rows.append(row)
    return pd.DataFrame(rows)


def _build_per_task_table(
    all_records: Dict[str, Dict[str, Dict[str, Any]]]
) -> pd.DataFrame:
    """Build a per-task breakdown across all systems."""
    # Collect all unique task_ids across all systems
    all_task_ids: set[str] = set()
    for system_records in all_records.values():
        all_task_ids.update(system_records.keys())

    rows = []
    for tid in sorted(all_task_ids):
        row = {"task_id": tid}
        for system_name in sorted(all_records.keys()):
            rec = all_records[system_name].get(tid)
            if rec is None:
                row[f"{system_name}_exec"] = "-"
                row[f"{system_name}_fid"] = "-"
            else:
                ep = "PASS" if rec.get("exec_pass") else "FAIL"
                fid = rec.get("scores", {}).get("data_fidelity")
                fid_str = f"{fid:.3f}" if fid is not None else "n/a"
                row[f"{system_name}_exec"] = ep
                row[f"{system_name}_fid"] = fid_str
        rows.append(row)
    return pd.DataFrame(rows)


def _build_markdown_report(
    all_records: Dict[str, Dict[str, Dict[str, Any]]], pass_k: int = 1
) -> str:
    """Build a Markdown report."""
    lines: List[str] = []
    lines.append("# Benchmark Results\n")

    # Main table
    lines.append("## Systems × Metrics\n")
    main_df = _build_main_table(all_records, pass_k)
    if not main_df.empty:
        cols = list(main_df.columns)
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "---|" * len(cols))
        for _, row in main_df.iterrows():
            lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    else:
        lines.append("*(no results found)*")
    lines.append("")

    # Per-system detail
    lines.append("## Per-System Detail\n")
    for system_name in sorted(all_records.keys()):
        stats = _compute_system_stats(all_records[system_name], pass_k)
        if stats.get("n", 0) == 0:
            continue
        lines.append(f"### {system_name}")
        lines.append(f"- Tasks: {stats['n']}")
        lines.append(f"- Exec-pass: {stats['exec_pass']}/{stats['n']} ({stats['exec_pass_rate']:.1%})")
        lines.append(f"- Mean data_fidelity: {stats['mean_data_fidelity']:.3f}")
        lines.append(f"- Median data_fidelity: {stats['median_data_fidelity']:.3f}")
        lines.append(f"- Mean visual_form: {stats['mean_visual_form']:.3f}")
        lines.append(f"- Mean series_cohesion: {stats['mean_series_cohesion']:.3f}")
        lines.append(f"- Mean rounds used: {stats['mean_rounds_used']:.1f}")
        fid_dist = stats.get("fidelity_distribution", {})
        lines.append(f"- Fidelity distribution: [0-.25):{fid_dist.get('fid_0_25',0)} "
                     f"[.25-.50):{fid_dist.get('fid_25_50',0)} "
                     f"[.50-.75):{fid_dist.get('fid_50_75',0)} "
                     f"[.75-1.0]:{fid_dist.get('fid_75_100',0)}")
        lines.append("")

    # Per-task breakdown
    lines.append("## Per-Task Breakdown\n")
    pt_df = _build_per_task_table(all_records)
    if not pt_df.empty:
        cols = list(pt_df.columns)
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "---|" * len(cols))
        for _, row in pt_df.iterrows():
            lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    lines.append("")

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Aggregate benchmark metrics (B3)")
    ap.add_argument("--results", default="eval/results_bench",
                    help="Root directory containing results/<system>/<task_id>/record.json")
    ap.add_argument("--pass-k", type=int, default=1, help="k for pass@k metric")
    ap.add_argument("--out", default=None, help="Output dir for aggregate files")
    args = ap.parse_args(argv)

    results_root = Path(args.results)
    out_dir = Path(args.out) if args.out else results_root / "aggregate"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_records = _collect_records(results_root)
    if not all_records:
        print(f"[warn] No record.json files found under {results_root}/<system>/<task_id>/")
        return 1

    systems = list(all_records.keys())
    total_tasks = sum(len(recs) for recs in all_records.values())
    print(f"[info] Found {len(systems)} systems, {total_tasks} task records across all systems")

    # Main table as CSV
    main_df = _build_main_table(all_records, args.pass_k)
    main_csv = out_dir / "main_table.csv"
    main_df.to_csv(main_csv, index=False)
    print(f"[saved] {main_csv}")

    # Per-task table as CSV
    pt_df = _build_per_task_table(all_records)
    pt_csv = out_dir / "per_task.csv"
    pt_df.to_csv(pt_csv, index=False)
    print(f"[saved] {pt_csv}")

    # Markdown report
    report = _build_markdown_report(all_records, args.pass_k)
    report_path = out_dir / "report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"[saved] {report_path}")

    # Print main table to console
    print("\n" + report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
