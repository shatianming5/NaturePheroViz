from __future__ import annotations

from typing import Any, Dict, List


def format_pheromone_summary(summary: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    total = int(summary.get("total", 0) or 0)
    by_type = summary.get("by_type") or {}
    lines.append(f"Pheromone: total={total}")
    if isinstance(by_type, dict):
        detail = ", ".join(f"{k}={int(v or 0)}" for k, v in sorted(by_type.items()))
        if detail:
            lines.append(f"Pheromone by type: {detail}")
    return lines


def compose_feedback(
    round_idx: int,
    last_scores: Dict[str, float],
    diagnostics: List[Dict[str, Any]],
    layer_guards: Dict[str, str],
) -> str:
    top = diagnostics[:5]
    lines: List[str] = []
    lines.append(f"[ROUND {round_idx}] Goal: {{goal}}  Chart: {{chart_family}}")
    lines.append(
        "Prev J: Overall={:.2f}  VisualForm={:.2f}  DataFidelity={:.2f}  SeriesCohesion={:.2f}".format(
            last_scores.get("overall_score", 0.0),
            last_scores.get("visual_form", 0.0),
            last_scores.get("data_fidelity", 0.0),
            last_scores.get("series_cohesion", 0.0),
        )
    )
    lines.append("Diagnostics (top-5):")
    for diag in top:
        lines.append(
            f" - {diag['key']} (sev={diag.get('sev', 1)}) -> slot {diag.get('slot', '?')} {diag.get('hint', '')}"
        )
    lines.append("Layer guards:")
    for layer, guard in layer_guards.items():
        lines.append(f"- {layer} {guard}")
    lines.append(
        "Return JSON ONLY:\n{\n  \"slots\": { \"<slot.key>\": \"<FUNCTION BODY ONLY>\" , ... },\n  \"notes\": \"<design intent / risks>\"\n}"
    )
    return "\n".join(lines)
