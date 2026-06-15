from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .single_chain_runner import run_chain


DEFAULT_CASES: List[Dict[str, Any]] = [
    {"name": "actual_target_line", "excel_path": "data/actual_target_plan.csv", "user_goal": "计划与实际趋势", "chart_family": "line"},
    {"name": "product_scatter", "excel_path": "data/product_scatter.csv", "user_goal": "区域品类分布", "chart_family": "scatter"},
    {"name": "gene_expression_line", "excel_path": "data/gene_expression.csv", "user_goal": "表达量变化趋势", "chart_family": "line"},
]

DEFAULT_CONFIGS: List[Dict[str, Any]] = [
    {"name": "full", "use_verifier": True, "use_best_of_n": True, "use_pheromone": True},
    {"name": "no_verifier", "use_verifier": False, "use_best_of_n": True, "use_pheromone": True},
    {"name": "no_bestof", "use_verifier": True, "use_best_of_n": False, "use_pheromone": True},
    {"name": "no_pheromone", "use_verifier": True, "use_best_of_n": True, "use_pheromone": False},
]


def _resolve_cases(cases: Optional[Iterable[Dict[str, Any]]], root: Path) -> List[Dict[str, Any]]:
    resolved: List[Dict[str, Any]] = []
    for case in list(cases) if cases is not None else list(DEFAULT_CASES):
        item = dict(case)
        excel_path = Path(str(item["excel_path"]))
        if not excel_path.is_absolute():
            excel_path = root / excel_path
        item["excel_path"] = str(excel_path)
        resolved.append(item)
    return resolved


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_ablation_suite(
    output_dir: str | Path | None = None,
    *,
    rounds: int = 2,
    cases: Optional[Iterable[Dict[str, Any]]] = None,
    configs: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    out_dir = Path(output_dir) if output_dir is not None else root / "runs" / f"ablation_suite_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    case_list = _resolve_cases(cases, root)
    config_list = [dict(item) for item in (list(configs) if configs is not None else list(DEFAULT_CONFIGS))]

    rows: List[Dict[str, Any]] = []
    for case in case_list:
        for config in config_list:
            error_text = ""
            try:
                result = run_chain(
                    case["excel_path"],
                    case["user_goal"],
                    case["chart_family"],
                    rounds=rounds,
                    use_verifier=bool(config.get("use_verifier", True)),
                    use_best_of_n=bool(config.get("use_best_of_n", True)),
                    use_pheromone=bool(config.get("use_pheromone", True)),
                )
                scores = result.get("scores") or {}
                ok = True
            except Exception as exc:
                result = {}
                scores = {}
                ok = False
                error_text = str(exc)
            rows.append(
                {
                    "case": case["name"],
                    "config": config["name"],
                    "excel_path": case["excel_path"],
                    "chart_family": case["chart_family"],
                    "ok": ok,
                    "error": error_text,
                    "rounds_used": int(result.get("round", 0) or 0),
                    "selected_index": int(result.get("selected_index", 1) or 1),
                    "overall_score": float(scores.get("overall_score", 0.0) or 0.0),
                    "visual_form": float(scores.get("visual_form", 0.0) or 0.0),
                    "data_fidelity": float(scores.get("data_fidelity", 0.0) or 0.0),
                    "series_cohesion": float(scores.get("series_cohesion", 0.0) or 0.0),
                    "stop_reason": str(result.get("stop_reason", "")),
                    "use_verifier": bool(config.get("use_verifier", True)),
                    "use_best_of_n": bool(config.get("use_best_of_n", True)),
                    "use_pheromone": bool(config.get("use_pheromone", True)),
                    "png_path": str(result.get("png_path", "")),
                }
            )

    aggregate_rows: List[Dict[str, Any]] = []
    for config in config_list:
        name = config["name"]
        subset = [row for row in rows if row["config"] == name]
        ok_subset = [row for row in subset if row["ok"]]
        if not subset:
            continue
        aggregate_rows.append(
            {
                "config": name,
                "cases": len(subset),
                "ok_cases": len(ok_subset),
                "avg_overall_score": (sum(row["overall_score"] for row in ok_subset) / len(ok_subset)) if ok_subset else 0.0,
                "avg_visual_form": (sum(row["visual_form"] for row in ok_subset) / len(ok_subset)) if ok_subset else 0.0,
                "avg_data_fidelity": (sum(row["data_fidelity"] for row in ok_subset) / len(ok_subset)) if ok_subset else 0.0,
                "avg_series_cohesion": (sum(row["series_cohesion"] for row in ok_subset) / len(ok_subset)) if ok_subset else 0.0,
                "avg_rounds_used": (sum(row["rounds_used"] for row in ok_subset) / len(ok_subset)) if ok_subset else 0.0,
            }
        )

    summary = {
        "output_dir": str(out_dir),
        "rounds": rounds,
        "cases": case_list,
        "configs": config_list,
        "runs": rows,
        "aggregates": aggregate_rows,
    }
    (out_dir / "ablation_runs.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(out_dir / "ablation_runs.csv", rows)
    _write_csv(out_dir / "ablation_aggregates.csv", aggregate_rows)
    return summary
