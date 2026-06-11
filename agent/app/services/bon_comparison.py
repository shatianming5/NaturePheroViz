from __future__ import annotations

import csv
import json
import os
import re
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import matplotlib.pyplot as plt
import pandas as pd

from . import single_chain_runner as scr


HARD_CASE_NAME = "two_series_line_round2_repair"


def _hard_case_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month": ["Jan", "Feb", "Mar", "Apr"],
            "actual": [120.0, 135.0, 150.0, 165.0],
            "target": [130.0, 140.0, 155.0, 170.0],
        }
    )


def _hard_case_spec() -> Dict[str, Any]:
    return {
        "layout": {
            "legend": {"loc": "best", "ncol": 1, "frame": False},
            "grid": {"x": False, "y": True, "minor": False},
            "titles": {"top": "Actual vs Target"},
            "title_align": "left",
        },
        "scales": {
            "x": {"kind": "categorical", "range": None, "breaks": None},
            "y_left": {"kind": "linear", "range": [None, None], "breaks": None},
            "y_right": {"kind": "linear", "range": [None, None], "breaks": None},
        },
        "theme": {
            "font": "Arial",
            "fontsize": 9,
            "axis_linewidth": 1.0,
            "tick_len": 3.0,
            "tick_width": 0.8,
            "palette_global": "tab10",
            "line_width": 1.5,
            "marker_size": 36,
        },
        "flags": {
            "inherit_palette": True,
            "legend_outside": "auto",
            "safe_log_y": True,
            "max_overlays": 3,
            "tick_density": "normal",
        },
        "overlays": [
            {"id": "line", "mark": "line", "variant": "main", "x": "month", "y": "actual", "group": None, "yaxis": "left"},
            {"id": "line_1", "mark": "line", "variant": "main", "x": "month", "y": "target", "group": None, "yaxis": "left"},
        ],
    }


def _render_variant(out_png: Path, df: pd.DataFrame, variant: str) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=100)
    ax.grid(axis="y", alpha=0.25)
    ax.set_title("Actual vs Target", loc="left")

    months = df["month"]
    actual = df["actual"]
    target = df["target"]

    if variant == "baseline_low":
        ax.plot(months, actual, color="#1f77b4", marker="o", linewidth=1.8)
        ax.plot(months, target * 0.65, color="#1f77b4", marker="o", linewidth=1.8)
    elif variant == "candidate2_mid":
        ax.plot(months, actual, color="#1f77b4", marker="o", linewidth=1.8)
        ax.plot(months, target, color="#1f77b4", marker="o", linewidth=1.8)
    elif variant == "candidate3_high":
        ax.plot(months, actual, color="#1f77b4", marker="o", linewidth=1.8, label="actual")
        ax.plot(months, target, color="#444444", linestyle="--", marker="o", linewidth=1.6, label="target")
        ax.legend(frameon=False, loc="best")
    else:
        raise ValueError(f"unknown hard-case variant: {variant}")

    fig.tight_layout()
    fig.savefig(out_png, dpi=100)
    fig.savefig(out_png.with_suffix(".svg"), format="svg")
    plt.close(fig)


def _variant_for(out_png: str) -> str:
    match = re.search(r"figure_round_(\d+)_cand_(\d+)\.png$", out_png.replace("\\", "/"))
    if not match:
        return "baseline_low"
    round_idx = int(match.group(1))
    candidate_idx = int(match.group(2))
    if round_idx <= 1:
        return "baseline_low"
    if candidate_idx == 1:
        return "baseline_low"
    if candidate_idx == 2:
        return "candidate2_mid"
    return "candidate3_high"


def _fake_derive_spec(intent: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    return _hard_case_spec()


def _fake_llm_generate_slots(stage: str, payload: Dict[str, Any], temperature: float | None = None) -> Dict[str, Any]:
    return {
        "slots": {},
        "notes": "",
        "prompt": f"hard-case-{stage}",
        "response": {"stage": stage, "temperature": temperature},
    }


def _fake_execute_script(py_code: str, df: pd.DataFrame, intent: Dict[str, Any], ctx: Dict[str, Any], out_png: str, timeout_s: int = 15) -> Dict[str, Any]:
    out_path = Path(out_png)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    variant = _variant_for(out_png)
    _render_variant(out_path, df, variant)
    new_ctx = dict(ctx)
    new_ctx["spec"] = dict(ctx.get("spec") or _hard_case_spec())
    return {"ok": True, "png_path": str(out_path), "stderr": f"variant={variant}", "ctx": new_ctx}


def _run_dir_from_result(result: Dict[str, Any]) -> Path:
    candidates = result.get("candidates") or []
    if not candidates:
        raise ValueError("run_chain result does not contain candidates")
    code_path = candidates[0].get("code_path")
    if not code_path:
        raise ValueError("run_chain result does not contain code_path")
    return Path(code_path).resolve().parent


def _load_iteration(run_dir: Path, round_idx: int) -> Dict[str, Any]:
    path = run_dir / f"iteration_{round_idx}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _summarize_run(best_of_n: int, result: Dict[str, Any]) -> Dict[str, Any]:
    run_dir = _run_dir_from_result(result)
    round_idx = int(result.get("round", 0) or 0)
    iteration_1 = _load_iteration(run_dir, 1)
    iteration_final = _load_iteration(run_dir, round_idx)
    return {
        "best_of_n": best_of_n,
        "run_dir": str(run_dir),
        "rounds_used": round_idx,
        "selected_index": int(result.get("selected_index", 1) or 1),
        "round1_score": float(((iteration_1.get("scores") or {}).get("overall_score", 0.0) or 0.0)),
        "final_scores": result.get("scores", {}),
        "round2_candidates": [
            {
                "candidate_index": item.get("candidate_index"),
                "temperature": item.get("temperature"),
                "exec_pass": item.get("exec_pass"),
                "overall_score": float(((item.get("scores") or {}).get("overall_score", 0.0) or 0.0)),
                "data_fidelity": float(((item.get("scores") or {}).get("data_fidelity", 0.0) or 0.0)),
                "series_cohesion": float(((item.get("scores") or {}).get("series_cohesion", 0.0) or 0.0)),
                "diagnostics": len(item.get("diagnostics") or []),
            }
            for item in (iteration_final.get("candidates") or [])
        ],
        "iteration_paths": [str(run_dir / f"iteration_{idx}.json") for idx in range(1, round_idx + 1)],
    }


def _write_csv(summary: Dict[str, Any], csv_path: Path) -> None:
    rows: List[Dict[str, Any]] = []
    for key in ("n1", "n3"):
        run = summary[key]
        rows.append(
            {
                "label": key,
                "best_of_n": run["best_of_n"],
                "rounds_used": run["rounds_used"],
                "selected_index": run["selected_index"],
                "round1_score": run["round1_score"],
                "final_overall_score": (run.get("final_scores") or {}).get("overall_score", 0.0),
            }
        )
        for candidate in run.get("round2_candidates", []):
            rows.append(
                {
                    "label": f"{key}_cand_{candidate['candidate_index']}",
                    "best_of_n": run["best_of_n"],
                    "rounds_used": run["rounds_used"],
                    "selected_index": run["selected_index"],
                    "round1_score": run["round1_score"],
                    "final_overall_score": candidate["overall_score"],
                }
            )
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "label",
                "best_of_n",
                "rounds_used",
                "selected_index",
                "round1_score",
                "final_overall_score",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def run_best_of_n_hard_case_compare(output_dir: str | Path | None = None) -> Dict[str, Any]:
    root = Path(output_dir) if output_dir is not None else Path(__file__).resolve().parents[2] / "runs" / f"bon_compare_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    root.mkdir(parents=True, exist_ok=True)
    runs_root = root / "chain_runs"
    data_path = root / "hard_case_input.csv"
    _hard_case_df().to_csv(data_path, index=False)

    default_slots = {
        "L1": {"slots": {}, "notes": ""},
        "L2": {"slots": {}, "notes": ""},
        "L3": {"slots": {}, "notes": ""},
        "L4": {"slots": {}, "notes": ""},
    }

    def run_once(best_of_n: int, run_name: str) -> Dict[str, Any]:
        with ExitStack() as stack:
            stack.enter_context(patch.object(scr, "derive_spec", _fake_derive_spec))
            stack.enter_context(patch.object(scr, "validate_spec", lambda spec: spec))
            stack.enter_context(patch.object(scr, "_llm_generate_slots", _fake_llm_generate_slots))
            stack.enter_context(patch.object(scr, "execute_script", _fake_execute_script))
            stack.enter_context(patch.object(scr, "DEFAULT_STAGE_SLOTS_V2", default_slots))
            stack.enter_context(patch.object(scr, "RUNS_DIR", runs_root))
            stack.enter_context(patch.object(scr.time, "strftime", return_value=run_name))
            stack.enter_context(patch.dict(os.environ, {"BEST_OF_N": str(best_of_n)}, clear=False))
            return scr.run_chain(str(data_path), "repair actual-vs-target chart", "line", rounds=2)

    n1_result = run_once(1, "20260611T230001_n1")
    n3_result = run_once(3, "20260611T230002_n3")

    summary = {
        "case": HARD_CASE_NAME,
        "input_csv": str(data_path),
        "n1": _summarize_run(1, n1_result),
        "n3": _summarize_run(3, n3_result),
    }
    summary["comparison"] = {
        "overall_gain": float((summary["n3"]["final_scores"] or {}).get("overall_score", 0.0))
        - float((summary["n1"]["final_scores"] or {}).get("overall_score", 0.0)),
        "bon_beats_single": float((summary["n3"]["final_scores"] or {}).get("overall_score", 0.0))
        > float((summary["n1"]["final_scores"] or {}).get("overall_score", 0.0)),
        "n3_selected_nontrivial_candidate": int(summary["n3"]["selected_index"]) > 1,
    }

    summary_path = root / "bon_hard_case_compare.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(summary, root / "bon_hard_case_compare.csv")
    return summary
