"""
make_figures.py — generate all four paper figures from B3_main_table_v2.md data.
Run from repo root:  python deliverables/figures/make_figures.py
Outputs: deliverables/figures/fig{1-4}_{name}.{pdf,png}
"""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker

# ── style ──────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    "font.family":        "serif",
    "font.serif":         ["Times New Roman", "DejaVu Serif", "Palatino", "serif"],
    "font.size":          8,
    "axes.titlesize":     9,
    "axes.titleweight":   "bold",
    "axes.labelsize":     8,
    "xtick.labelsize":    7,
    "ytick.labelsize":    7,
    "legend.fontsize":    7,
    "legend.frameon":     False,
    "axes.spines.top":    False,
    "axes.spines.right":  False,
    "axes.grid":          False,
    "figure.dpi":         300,
    "savefig.dpi":        300,
    "savefig.bbox":       "tight",
    "savefig.pad_inches": 0.05,
})

# Okabe–Ito colorblind-safe palette
C = {
    "blue":        "#0072B2",
    "vermillion":  "#D55E00",
    "green":       "#009E73",
    "sky":         "#56B4E9",
    "orange":      "#E69F00",
    "purple":      "#CC79A7",
    "yellow":      "#F0E442",
    "black":       "#000000",
    "gray":        "#999999",
}

OUT = Path(__file__).parent
W_COL = 3.5   # double-column width (inches)


def save(fig, stem: str) -> None:
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"{stem}.{ext}")
    print(f"  saved {stem}.pdf / .png")


# ══════════════════════════════════════════════════════════════════════════════
# Figure 1 — Silent Error Rate grouped bar chart
# ══════════════════════════════════════════════════════════════════════════════
def fig1_silent_rate():
    # values (%) and 95% Wilson CI asymmetric errors [lo_err, hi_err]
    data = {
        "Synthetic\n(48-grid, n=96)": {
            "Ambiguous": (46.0, 10.0, 10.0),   # val, err_lo, err_hi
            "Clarified":  (12.0,  5.0,  9.0),
        },
        "Real Nature data\n(841 tasks, 71 papers)": {
            "Ambiguous": (77.0,  2.0,  2.0),
            "Clarified":  (10.0,  1.0,  2.0),
        },
    }
    groups   = list(data.keys())
    conds    = ["Ambiguous", "Clarified"]
    colors   = [C["vermillion"], C["sky"]]
    n_groups = len(groups)
    n_bars   = len(conds)
    width    = 0.3
    gap      = 0.08
    x_group  = np.arange(n_groups) * 1.2   # group spacing

    fig, ax = plt.subplots(figsize=(W_COL, W_COL * 0.72))

    for ci, (cond, col) in enumerate(zip(conds, colors)):
        offset = (ci - (n_bars - 1) / 2) * (width + gap)
        vals  = [data[g][cond][0] for g in groups]
        lo    = [data[g][cond][1] for g in groups]
        hi    = [data[g][cond][2] for g in groups]
        xpos  = x_group + offset
        bars  = ax.bar(xpos, vals, width, color=col, alpha=0.88,
                       label=cond, zorder=3)
        ax.errorbar(xpos, vals, yerr=[lo, hi],
                    fmt="none", color="black", capsize=3, lw=1.0, zorder=4)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v + hi[list(vals).index(v)] + 1.5,
                    f"{v:.0f}%", ha="center", va="bottom", fontsize=6.5)

    ax.set_xticks(x_group)
    ax.set_xticklabels(groups, ha="center")
    ax.set_ylabel("Silent Error Rate (%)")
    ax.set_ylim(0, 98)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%g%%"))
    ax.set_title("Fig. 1 — Silent Error Rate: Ambiguous vs. Clarified Prompts")
    ax.legend(loc="upper right", ncol=1)
    # annotation
    ax.text(0.02, 0.97,
            "Error bars: 95% Wilson CI",
            transform=ax.transAxes, fontsize=6, va="top", color=C["gray"],
            style="italic")
    fig.tight_layout()
    save(fig, "fig1_silent_rate")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
# Figure 2 — Detector Recall vs FP scatter
# ══════════════════════════════════════════════════════════════════════════════
def fig2_detector_scatter():
    detectors = [
        # name,              FP,    Recall, marker, color,       zorder
        ("Ours\n(oracle)",   0.000, 1.000, "★",    C["blue"],      5),
        ("self-check",       0.402, 0.614, "o",    C["orange"],    4),
        ("exec-pass /\nvalidity /\nconsistency",
                             0.000, 0.000, "s",    C["gray"],      3),
    ]

    fig, ax = plt.subplots(figsize=(W_COL, W_COL * 0.82))

    for name, fp, rec, marker, col, zo in detectors:
        ms = 12 if marker == "★" else 7
        ax.scatter(fp, rec, s=ms**2 if marker == "★" else ms**2,
                   marker="*" if marker == "★" else marker,
                   color=col, zorder=zo, linewidths=0.5,
                   edgecolors="white" if col != C["gray"] else "black")

    # annotations with offset to avoid overlap
    offsets = {
        "Ours\n(oracle)":      (-0.045,  0.06),
        "self-check":          ( 0.015,  0.05),
        "exec-pass /\nvalidity /\nconsistency": (0.015, -0.09),
    }
    for name, fp, rec, *_ in detectors:
        dx, dy = offsets[name]
        ax.annotate(name, xy=(fp, rec),
                    xytext=(fp + dx, rec + dy),
                    fontsize=6.5, ha="left",
                    arrowprops=dict(arrowstyle="-", color=C["gray"],
                                   lw=0.6, shrinkB=3) if (dx != 0 or dy != 0) else None)

    # ideal corner annotation
    ax.annotate("Ideal", xy=(0, 1), xytext=(0.05, 0.93),
                fontsize=6, color=C["gray"], style="italic",
                arrowprops=dict(arrowstyle="->", color=C["gray"], lw=0.6))

    ax.set_xlim(-0.05, 0.55)
    ax.set_ylim(-0.12, 1.18)
    ax.set_xlabel("False-Positive Rate (FP / correct results)")
    ax.set_ylabel("Recall (flags / silent errors)")
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
    ax.set_title("Fig. 2 — Detector Comparison: Recall vs. False-Positive Rate")
    # add recall=0 / FP=0 axis reference lines lightly
    ax.axhline(0, color=C["gray"], lw=0.5, ls="--", alpha=0.4)
    ax.axvline(0, color=C["gray"], lw=0.5, ls="--", alpha=0.4)
    fig.tight_layout()
    save(fig, "fig2_detector_scatter")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
# Figure 3 — Qwen scale trend + GPT-4o reference line
# ══════════════════════════════════════════════════════════════════════════════
def fig3_scale_trend():
    sizes   = [7, 14, 32]       # B params
    silent  = [65.0, 54.0, 44.0]  # ambiguous silent rate %
    gpt4o_ref = 46.0            # combined calibration baseline (gpt-4o + claude)

    fig, ax = plt.subplots(figsize=(W_COL, W_COL * 0.70))

    ax.plot(sizes, silent, "o-", color=C["blue"], lw=1.8, ms=6,
            label="Qwen2.5-Coder (open)", zorder=4)
    for x, y in zip(sizes, silent):
        ax.text(x, y + 2.2, f"{y:.0f}%", ha="center", fontsize=6.5, color=C["blue"])

    ax.axhline(gpt4o_ref, color=C["vermillion"], lw=1.4, ls="--",
               label=f"Closed-model baseline\n(GPT-4o + Claude-Sonnet, {gpt4o_ref:.0f}%)",
               zorder=3)
    ax.text(32.4, gpt4o_ref + 0.8, f"{gpt4o_ref:.0f}%",
            fontsize=6.5, color=C["vermillion"], va="bottom")

    ax.set_xticks(sizes)
    ax.set_xticklabels(["7B", "14B", "32B"])
    ax.set_xlabel("Model Size (parameters)")
    ax.set_ylabel("Ambiguous Silent Error Rate (%)")
    ax.set_ylim(30, 80)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%g%%"))
    ax.set_title("Fig. 3 — Silent Error Rate vs. Open-Model Scale")
    ax.legend(loc="upper right", fontsize=6.5)
    fig.tight_layout()
    save(fig, "fig3_scale_trend")
    plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
# Figure 4 — Ablation bar chart
# ══════════════════════════════════════════════════════════════════════════════
def fig4_ablation():
    configs = ["Full\n(all on)", "−Verifier", "−Best-of-N", "−Pheromone"]
    scores  = [0.9145, 0.9038, 0.9145, 0.9145]
    fids    = [0.7778, 0.7500, 0.7778, 0.7778]

    x     = np.arange(len(configs))
    width = 0.32
    gap   = 0.04

    fig, ax = plt.subplots(figsize=(W_COL, W_COL * 0.72))

    bars_s = ax.bar(x - (width + gap) / 2, scores, width,
                    color=C["blue"], alpha=0.88, label="Overall Score", zorder=3)
    bars_f = ax.bar(x + (width + gap) / 2, fids,   width,
                    color=C["orange"], alpha=0.88, label="Data Fidelity", zorder=3)

    for bar in bars_s:
        v = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.003,
                f"{v:.3f}", ha="center", va="bottom", fontsize=6)
    for bar in bars_f:
        v = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.003,
                f"{v:.3f}", ha="center", va="bottom", fontsize=6)

    ax.set_xticks(x)
    ax.set_xticklabels(configs)
    ax.set_ylabel("Score (0–1)")
    ax.set_ylim(0.68, 0.97)
    # broken-axis indicator
    ax.set_yticks([0.70, 0.75, 0.80, 0.85, 0.90, 0.95])
    ax.annotate("y-axis\ntruncated\nat 0.68",
                xy=(0, 0.685), xytext=(0.52, 0.045),
                textcoords="axes fraction", fontsize=5.5,
                color=C["gray"], style="italic",
                arrowprops=dict(arrowstyle="-", lw=0.4, color=C["gray"]))
    ax.set_title("Fig. 4 — Chart-Gen Pipeline Ablation")
    ax.legend(loc="lower right")

    # full-system reference line
    ax.axhline(scores[0], color=C["blue"], lw=0.7, ls=":", alpha=0.5)
    ax.axhline(fids[0],   color=C["orange"], lw=0.7, ls=":", alpha=0.5)

    fig.tight_layout()
    save(fig, "fig4_ablation")
    plt.close(fig)


# ── run all ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Generating paper figures...")
    fig1_silent_rate()
    fig2_detector_scatter()
    fig3_scale_trend()
    fig4_ablation()
    print("Done — check deliverables/figures/")
