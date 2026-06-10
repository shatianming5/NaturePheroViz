from pathlib import Path
import tempfile

import matplotlib.pyplot as plt
import importlib
import pandas as pd
import pytest

from app.services.code_assembler import assemble_with_slots
from app.services import fidelity_verifier as fv
from app.services.fidelity_verifier import verify_fidelity
from app.services.judge import judge
from app.services.spec_deriver import derive_spec
from app.services.spec_validator import validate_spec

judge_module = importlib.import_module("app.services.judge")


def test_spec_roundtrip():
    profile = {"columns": {"日期": "datetime", "销量": "numeric"}}
    intent = {
        "chart_family": "line",
        "x": "日期",
        "y": "销量",
        "aesthetics": {"palette": "ColorBlindSafe"},
    }
    spec = validate_spec(derive_spec(intent, profile))
    assert "overlays" in spec
    assert spec["overlays"][0]["mark"] == "line"


def test_assembler_empty_slots_ok():
    py_code = assemble_with_slots({})
    assert "def run(" in py_code


def _write_bar_figure(svg_path: Path, data: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=100)
    ax.bar(data["x"], data["value"])
    fig.tight_layout()
    fig.savefig(svg_path, dpi=100)
    fig.savefig(svg_path.with_suffix(".svg"), format="svg")
    plt.close(fig)


def _write_line_figure(svg_path: Path, data: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=100)
    ax.plot(data["x"], data["value"], marker="o")
    fig.tight_layout()
    fig.savefig(svg_path, dpi=100)
    fig.savefig(svg_path.with_suffix(".svg"), format="svg")
    plt.close(fig)


def test_verify_fidelity_wrong_value_for_series_b():
    gt = pd.DataFrame(
        {
            "series": ["B"],
            "x": ["Feb"],
            "value": [130000.0],
        }
    )
    spec = {
        "overlays": [
            {
                "id": "bar",
                "x": "x",
                "y": "value",
                "group": "series",
            }
        ]
    }
    with tempfile.TemporaryDirectory() as td:
        svg_path = Path(td) / "figure.png"
        _write_bar_figure(svg_path, pd.DataFrame({"x": ["Feb"], "value": [90000.0]}))
        result = verify_fidelity(
            svg_path=str(svg_path.with_suffix(".svg")),
            ground_truth_table=gt,
            spec=spec,
            png_path=str(svg_path),
        )

    assert result["data_fidelity"] < 0.4
    mismatches = result["mismatches"]
    assert len(mismatches) == 1
    mismatch = mismatches[0]
    assert mismatch["type"] == "wrong_value"
    assert mismatch["series"] == "B"
    assert mismatch["x"] == "Feb"
    assert mismatch["gt"] == 130000.0


def test_verify_fidelity_line_chart_roundtrip(tmp_path):
    gt = pd.DataFrame(
        {
            "x": ["Jan", "Feb", "Mar"],
            "value": [120.0, 135.0, 150.0],
        }
    )
    spec = {
        "overlays": [
            {
                "id": "line",
                "mark": "line",
                "x": "x",
                "y": "value",
            }
        ]
    }
    png_path = tmp_path / "line.png"
    _write_line_figure(png_path, gt)

    result = verify_fidelity(
        svg_path=str(png_path.with_suffix(".svg")),
        ground_truth_table=gt,
        spec=spec,
        png_path=str(png_path),
    )

    assert result["data_fidelity"] >= 0.99
    assert result["mismatches"] == []


def test_verify_fidelity_wide_multi_line_roundtrip(tmp_path):
    gt = pd.DataFrame(
        {
            "month": ["Jan", "Feb", "Mar"],
            "actual": [120.0, 135.0, 150.0],
            "target": [130.0, 140.0, 155.0],
        }
    )
    spec = {
        "overlays": [
            {"id": "line", "mark": "line", "x": "month", "y": "actual"},
            {"id": "line_1", "mark": "line", "x": "month", "y": "target"},
        ]
    }
    png_path = tmp_path / "wide_line.png"
    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=100)
    ax.plot(gt["month"], gt["actual"], marker="o", label="actual")
    ax.plot(gt["month"], gt["target"], marker="o", label="target")
    fig.tight_layout()
    fig.savefig(png_path, dpi=100)
    fig.savefig(png_path.with_suffix(".svg"), format="svg")
    plt.close(fig)

    result = verify_fidelity(
        svg_path=str(png_path.with_suffix(".svg")),
        ground_truth_table=gt,
        spec=spec,
        png_path=str(png_path),
    )

    assert result["data_fidelity"] >= 0.99
    assert result["mismatches"] == []


def test_judge_uses_fidelity_verifier(tmp_path):
    gt = pd.DataFrame(
        {
            "series": ["B"],
            "x": ["Feb"],
            "value": [130000.0],
        }
    )
    spec = {
        "overlays": [
            {
                "id": "bar",
                "x": "x",
                "y": "value",
                "group": "series",
            }
        ]
    }
    png_path = tmp_path / "figure.png"
    _write_bar_figure(png_path, pd.DataFrame({"x": ["Feb"], "value": [90000.0]}))

    result = judge(
        png_path=str(png_path),
        exec_log="",
        df=gt,
        spec=spec,
    )

    assert result["data_fidelity"] < 0.4
    assert result["fidelity_detail"]["mismatches"]


def test_judge_returns_series_cohesion_for_multi_series(tmp_path):
    gt = pd.DataFrame(
        {
            "month": ["Jan", "Feb"],
            "actual": [120.0, 135.0],
            "target": [130.0, 140.0],
        }
    )
    spec = {
        "layout": {"legend": {"loc": "none"}},
        "overlays": [
            {"id": "line", "mark": "line", "x": "month", "y": "actual", "style": {"color": "#1f77b4"}},
            {"id": "line_1", "mark": "line", "x": "month", "y": "target", "style": {"color": "#1f77b4"}},
        ],
    }
    png_path = tmp_path / "multi_line.png"
    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=100)
    ax.plot(gt["month"], gt["actual"], marker="o", label="actual")
    ax.plot(gt["month"], gt["target"], marker="o", label="target")
    fig.tight_layout()
    fig.savefig(png_path, dpi=100)
    fig.savefig(png_path.with_suffix(".svg"), format="svg")
    plt.close(fig)

    result = judge(
        png_path=str(png_path),
        exec_log="",
        df=gt,
        spec=spec,
    )

    assert "series_cohesion" in result
    assert result["series_cohesion"] < 1.0
    keys = {item["key"] for item in result["diagnostics"]}
    assert "legend.missing.multi" in keys


def test_judge_series_cohesion_ratio_axis_mismatch(tmp_path):
    gt = pd.DataFrame(
        {
            "month": ["Jan", "Feb"],
            "sales": [100.0, 120.0],
            "share_ratio": [0.2, 0.25],
        }
    )
    spec = {
        "layout": {"legend": {"loc": "best"}},
        "overlays": [
            {"id": "line", "mark": "line", "x": "month", "y": "sales", "yaxis": "left", "style": {"color": "#1f77b4"}},
            {"id": "line_1", "mark": "line", "x": "month", "y": "share_ratio", "yaxis": "left", "style": {"color": "#ff7f0e", "linestyle": "--"}},
        ],
    }
    png_path = tmp_path / "ratio_line.png"
    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=100)
    ax.plot(gt["month"], gt["sales"], marker="o", label="sales")
    ax.plot(gt["month"], gt["share_ratio"], marker="o", label="share_ratio")
    fig.tight_layout()
    fig.savefig(png_path, dpi=100)
    fig.savefig(png_path.with_suffix(".svg"), format="svg")
    plt.close(fig)

    result = judge(
        png_path=str(png_path),
        exec_log="",
        df=gt,
        spec=spec,
    )

    assert result["series_cohesion"] < 1.0
    keys = {item["key"] for item in result["diagnostics"]}
    assert "ratio.axis.mismatch" in keys


def test_judge_series_cohesion_rendered_palette_conflict(tmp_path):
    gt = pd.DataFrame(
        {
            "month": ["Jan", "Feb", "Mar"],
            "actual": [120.0, 135.0, 150.0],
            "target": [130.0, 140.0, 155.0],
        }
    )
    spec = {
        "layout": {"legend": {"loc": "best"}},
        "overlays": [
            {"id": "line", "mark": "line", "x": "month", "y": "actual"},
            {"id": "line_1", "mark": "line", "x": "month", "y": "target"},
        ],
    }
    png_path = tmp_path / "palette_conflict.png"
    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=100)
    ax.plot(gt["month"], gt["actual"], color="#1f77b4", marker="o", label="actual")
    ax.plot(gt["month"], gt["target"], color="#1f77b4", marker="o", label="target")
    ax.legend()
    fig.tight_layout()
    fig.savefig(png_path, dpi=100)
    fig.savefig(png_path.with_suffix(".svg"), format="svg")
    plt.close(fig)

    result = judge(
        png_path=str(png_path),
        exec_log="",
        df=gt,
        spec=spec,
    )

    assert result["series_cohesion"] < 1.0
    keys = {item["key"] for item in result["diagnostics"]}
    assert "series.style.conflict" in keys


def test_judge_series_cohesion_rendered_x_order_mismatch(tmp_path):
    gt = pd.DataFrame(
        {
            "month": ["Jan", "Feb", "Mar"],
            "value": [1.0, 2.0, 3.0],
            "value2": [1.5, 2.5, 3.5],
        }
    )
    spec = {
        "layout": {"legend": {"loc": "best"}},
        "overlays": [
            {"id": "line", "mark": "line", "x": "month", "y": "value"},
            {"id": "line_1", "mark": "line", "x": "month", "y": "value2"},
        ],
    }
    png_path = tmp_path / "x_order_mismatch.png"
    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=100)
    rendered_order = ["Mar", "Jan", "Feb"]
    lookup_1 = dict(zip(gt["month"], gt["value"]))
    lookup_2 = dict(zip(gt["month"], gt["value2"]))
    ax.plot(rendered_order, [lookup_1[k] for k in rendered_order], marker="o", label="value")
    ax.plot(rendered_order, [lookup_2[k] for k in rendered_order], marker="o", label="value2")
    ax.legend()
    fig.tight_layout()
    fig.savefig(png_path, dpi=100)
    fig.savefig(png_path.with_suffix(".svg"), format="svg")
    plt.close(fig)

    result = judge(
        png_path=str(png_path),
        exec_log="",
        df=gt,
        spec=spec,
    )

    assert result["series_cohesion"] < 1.0
    keys = {item["key"] for item in result["diagnostics"]}
    assert "x.inconsistent" in keys


def test_judge_series_cohesion_distinct_series_with_grid_not_penalized(tmp_path):
    gt = pd.DataFrame(
        {
            "month": ["Jan", "Feb", "Mar"],
            "actual": [120.0, 135.0, 150.0],
            "target": [130.0, 140.0, 155.0],
        }
    )
    spec = {
        "layout": {"legend": {"loc": "best"}, "grid": {"y": True}},
        "overlays": [
            {"id": "line", "mark": "line", "x": "month", "y": "actual", "yaxis": "left"},
            {"id": "line_1", "mark": "line", "x": "month", "y": "target", "yaxis": "left"},
        ],
    }
    png_path = tmp_path / "distinct_with_grid.png"
    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=100)
    ax.plot(gt["month"], gt["actual"], color="#1f77b4", marker="o", label="actual")
    ax.plot(gt["month"], gt["target"], color="#ff7f0e", marker="s", linestyle="--", label="target")
    ax.grid(True, axis="y", which="major", alpha=0.3, linestyle="-")
    ax.grid(True, axis="y", which="minor", alpha=0.12, linestyle="--")
    ax.minorticks_on()
    ax.legend()
    fig.tight_layout()
    fig.savefig(png_path, dpi=100)
    fig.savefig(png_path.with_suffix(".svg"), format="svg")
    plt.close(fig)

    result = judge(
        png_path=str(png_path),
        exec_log="",
        df=gt,
        spec=spec,
    )

    keys = {item["key"] for item in result["diagnostics"]}
    assert "series.style.conflict" not in keys
    assert "legend.missing.multi" not in keys
    assert result["series_cohesion"] == pytest.approx(1.0)


def test_judge_series_cohesion_dual_axis_correct_no_ratio_mismatch(tmp_path):
    gt = pd.DataFrame(
        {
            "month": ["Jan", "Feb", "Mar"],
            "sales": [100.0, 120.0, 140.0],
            "share_ratio": [0.2, 0.25, 0.3],
        }
    )
    spec = {
        "layout": {"legend": {"loc": "best"}},
        "overlays": [
            {"id": "line", "mark": "line", "x": "month", "y": "sales", "yaxis": "left"},
            {"id": "line_1", "mark": "line", "x": "month", "y": "share_ratio", "yaxis": "right"},
        ],
    }
    png_path = tmp_path / "dual_axis_correct.png"
    fig, ax_left = plt.subplots(figsize=(6.4, 4.8), dpi=100)
    ax_right = ax_left.twinx()
    line1 = ax_left.plot(gt["month"], gt["sales"], color="#1f77b4", marker="o", label="sales")[0]
    line2 = ax_right.plot(gt["month"], gt["share_ratio"], color="#ff7f0e", marker="s", linestyle="--", label="share_ratio")[0]
    ax_right.set_ylim(0, 0.35)
    ax_right.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax_left.legend([line1, line2], ["sales", "share_ratio"])
    fig.tight_layout()
    fig.savefig(png_path, dpi=100)
    fig.savefig(png_path.with_suffix(".svg"), format="svg")
    plt.close(fig)

    result = judge(
        png_path=str(png_path),
        exec_log="",
        df=gt,
        spec=spec,
    )

    keys = {item["key"] for item in result["diagnostics"]}
    assert "ratio.axis.mismatch" not in keys


def test_judge_series_cohesion_bar_palette_conflict(tmp_path):
    gt = pd.DataFrame(
        {
            "month": ["Jan", "Jan", "Feb", "Feb"],
            "series": ["A", "B", "A", "B"],
            "value": [10.0, 20.0, 15.0, 25.0],
        }
    )
    spec = {
        "layout": {"legend": {"loc": "best"}},
        "overlays": [
            {"id": "bar", "mark": "bar", "x": "month", "y": "value", "group": "series", "yaxis": "left"},
        ],
    }
    png_path = tmp_path / "bar_palette_conflict.png"
    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=100)
    months = ["Jan", "Feb"]
    a_vals = [10.0, 15.0]
    b_vals = [20.0, 25.0]
    x = range(len(months))
    ax.bar([i - 0.2 for i in x], a_vals, width=0.4, color="#1f77b4", label="A")
    ax.bar([i + 0.2 for i in x], b_vals, width=0.4, color="#1f77b4", label="B")
    ax.set_xticks(list(x))
    ax.set_xticklabels(months)
    ax.legend()
    fig.tight_layout()
    fig.savefig(png_path, dpi=100)
    fig.savefig(png_path.with_suffix(".svg"), format="svg")
    plt.close(fig)

    result = judge(
        png_path=str(png_path),
        exec_log="",
        df=gt,
        spec=spec,
    )

    assert result["series_cohesion"] < 1.0
    keys = {item["key"] for item in result["diagnostics"]}
    assert "series.style.conflict" in keys


def test_judge_overall_score_uses_configured_weights(tmp_path):
    gt = pd.DataFrame(
        {
            "month": ["Jan", "Feb"],
            "actual": [120.0, 135.0],
            "target": [130.0, 140.0],
        }
    )
    spec = {
        "layout": {"legend": {"loc": "none"}},
        "overlays": [
            {"id": "line", "mark": "line", "x": "month", "y": "actual", "style": {"color": "#1f77b4"}},
            {"id": "line_1", "mark": "line", "x": "month", "y": "target", "style": {"color": "#1f77b4"}},
        ],
    }
    png_path = tmp_path / "weighted_score_line.png"
    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=100)
    ax.plot(gt["month"], gt["actual"], marker="o", label="actual")
    ax.plot(gt["month"], gt["target"], marker="o", label="target")
    fig.tight_layout()
    fig.savefig(png_path, dpi=100)
    fig.savefig(png_path.with_suffix(".svg"), format="svg")
    plt.close(fig)

    result = judge(
        png_path=str(png_path),
        exec_log="",
        df=gt,
        spec=spec,
    )

    weights = judge_module.RULES["weights"]
    expected = (
        weights["visual_form"] * result["visual_form"]
        + weights["data_fidelity"] * result["data_fidelity"]
        + weights["series_cohesion"] * result["series_cohesion"]
    ) / (weights["visual_form"] + weights["data_fidelity"] + weights["series_cohesion"])

    assert "overall_score" in result
    assert result["overall_score"] == pytest.approx(expected)


def test_verify_fidelity_uses_vlm_table_fallback_when_svg_fails(tmp_path, monkeypatch):
    gt = pd.DataFrame(
        {
            "series": ["B"],
            "x": ["Feb"],
            "value": [130000.0],
        }
    )
    spec = {
        "overlays": [
            {
                "id": "bar",
                "x": "x",
                "y": "value",
                "group": "series",
            }
        ]
    }
    png_path = tmp_path / "figure.png"
    _write_bar_figure(png_path, pd.DataFrame({"x": ["Feb"], "value": [90000.0]}))

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"rows":[{"series":"B","x":"Feb","value":90000}]}'
                        }
                    }
                ]
            }

    def fake_post(url, headers, json, timeout):
        assert url == "https://vlm.test/chat/completions"
        assert json["messages"][1]["content"][1]["type"] == "input_image"
        return FakeResponse()

    monkeypatch.setenv("LLM_API_BASE", "https://vlm.test")
    monkeypatch.setenv("VLM_API_KEY", "test-key")
    monkeypatch.setenv("VLM_MODEL", "test-vlm")
    monkeypatch.setattr(fv.requests, "post", fake_post)

    result = verify_fidelity(
        svg_path=str(tmp_path / "missing.svg"),
        ground_truth_table=gt,
        spec=spec,
        png_path=str(png_path),
    )

    assert result["data_fidelity"] < 0.4
    assert result["pred_table"].to_dict(orient="records") == [
        {"series": "B", "x": "Feb", "value": 90000}
    ]
    assert result["mismatches"] == [
        {"type": "wrong_value", "series": "B", "x": "Feb", "gt": 130000.0, "pred": 90000.0}
    ]


def test_verify_fidelity_prefers_chart2table_env_over_shared_vlm(tmp_path, monkeypatch):
    gt = pd.DataFrame({"x": ["Feb"], "value": [100.0]})
    spec = {"overlays": [{"id": "line", "mark": "line", "x": "x", "y": "value"}]}
    png_path = tmp_path / "figure.png"
    _write_line_figure(png_path, gt)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"rows":[{"x":"Feb","value":100}]}'}}]}

    def fake_post(url, headers, json, timeout):
        assert url == "http://local-chart/chat/completions"
        assert "onechart" in json["messages"][0]["content"][0]["text"].lower()
        return FakeResponse()

    monkeypatch.setenv("LLM_API_BASE", "https://shared-vlm.test")
    monkeypatch.setenv("VLM_API_KEY", "shared-key")
    monkeypatch.setenv("VLM_MODEL", "shared-vlm")
    monkeypatch.setenv("ONECHART_API_BASE", "http://local-chart")
    monkeypatch.setenv("ONECHART_API_KEY", "local-key")
    monkeypatch.setenv("ONECHART_MODEL", "onechart-0.2b")
    monkeypatch.setattr(fv.requests, "post", fake_post)

    result = verify_fidelity(
        svg_path=str(tmp_path / "missing.svg"),
        ground_truth_table=gt,
        spec=spec,
        png_path=str(png_path),
    )

    assert result["data_fidelity"] >= 0.99
    assert result["mismatches"] == []


def test_verify_fidelity_uses_csv_fallback_with_real_matching(tmp_path):
    gt = pd.DataFrame(
        {
            "series": ["A", "B"],
            "x": ["Jan", "Jan"],
            "value": [10.0, 30.0],
        }
    )
    spec = {
        "overlays": [
            {
                "id": "bar",
                "mark": "bar",
                "x": "x",
                "y": "value",
                "group": "series",
            }
        ]
    }
    png_path = tmp_path / "figure.png"
    png_path.write_bytes(b"fake")
    pd.DataFrame(
        {
            "series": ["A", "B"],
            "x": ["Jan", "Jan"],
            "value": [10.0, 20.0],
        }
    ).to_csv(png_path.with_suffix(".csv"), index=False)

    result = verify_fidelity(
        svg_path=str(tmp_path / "missing.svg"),
        ground_truth_table=gt,
        spec=spec,
        png_path=str(png_path),
    )

    assert result["data_fidelity"] < 1.0
    assert result["pred_table"].to_dict(orient="records") == [
        {"series": "A", "x": "Jan", "value": 10.0},
        {"series": "B", "x": "Jan", "value": 20.0},
    ]
    assert result["mismatches"] == [
        {"type": "wrong_value", "series": "B", "x": "Jan", "gt": 30.0, "pred": 20.0}
    ]


def test_verify_fidelity_prefers_csv_when_svg_parse_is_worse(tmp_path):
    gt = pd.DataFrame(
        {
            "series": ["A"],
            "x": ["Jan"],
            "value": [30.0],
        }
    )
    spec = {
        "overlays": [
            {
                "id": "bar",
                "mark": "bar",
                "x": "x",
                "y": "value",
                "group": "series",
            }
        ]
    }
    png_path = tmp_path / "figure.png"
    _write_bar_figure(png_path, pd.DataFrame({"x": ["Jan"], "value": [10.0]}))
    pd.DataFrame({"series": ["A"], "x": ["Jan"], "value": [30.0]}).to_csv(
        png_path.with_suffix(".csv"), index=False
    )

    result = verify_fidelity(
        svg_path=str(png_path.with_suffix(".svg")),
        ground_truth_table=gt,
        spec=spec,
        png_path=str(png_path),
    )

    assert result["data_fidelity"] >= 0.99
    assert result["pred_table"].to_dict(orient="records") == [
        {"series": "A", "x": "Jan", "value": 30.0}
    ]


def test_verify_fidelity_wide_csv_fallback_roundtrip(tmp_path):
    gt = pd.DataFrame(
        {
            "month": ["Jan", "Feb"],
            "actual": [120.0, 135.0],
            "target": [130.0, 140.0],
        }
    )
    spec = {
        "overlays": [
            {"id": "line", "mark": "line", "x": "month", "y": "actual"},
            {"id": "line_1", "mark": "line", "x": "month", "y": "target"},
        ]
    }
    png_path = tmp_path / "figure.png"
    png_path.write_bytes(b"fake")
    gt.to_csv(png_path.with_suffix(".csv"), index=False)

    result = verify_fidelity(
        svg_path=str(tmp_path / "missing.svg"),
        ground_truth_table=gt,
        spec=spec,
        png_path=str(png_path),
    )

    assert result["data_fidelity"] >= 0.99
    assert len(result["pred_table"]) == 4
