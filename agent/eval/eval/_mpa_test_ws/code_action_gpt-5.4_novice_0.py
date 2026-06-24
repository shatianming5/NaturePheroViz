import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator, FuncFormatter

CSV_FILE = "data.csv"
OUTPUT_FILE = "test.png"
TARGET_COLUMN = "Women's millions of dollars"

def normalize_name(name):
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())

df = pd.read_csv(CSV_FILE)

if TARGET_COLUMN in df.columns:
    column = TARGET_COLUMN
else:
    target_norm = normalize_name(TARGET_COLUMN)
    matches = [c for c in df.columns if normalize_name(c) == target_norm]
    if not matches:
        matches = [
            c for c in df.columns
            if "women" in normalize_name(c) and "millionsofdollars" in normalize_name(c)
        ]
    if not matches:
        raise KeyError(f"Column '{TARGET_COLUMN}' not found in {list(df.columns)}")
    column = matches[0]

values = (
    df[column]
    .astype(str)
    .str.replace(r"[^0-9.\-]", "", regex=True)
    .replace("", np.nan)
)
values = pd.to_numeric(values, errors="coerce").dropna()

if values.empty:
    raise ValueError(f"No numeric data available in column '{column}'.")

q1, median, q3 = values.quantile([0.25, 0.50, 0.75])
vmin, vmax, mean = values.min(), values.max(), values.mean()
n = len(values)

if n == 1 or np.isclose(vmin, vmax):
    bins = np.array([vmin - 0.5, vmax + 0.5])
else:
    num_bins = int(np.clip(np.ceil(np.sqrt(n)), 5, 10))
    bins = np.linspace(vmin, vmax, num_bins + 1)

span = vmax - vmin
pad = span * 0.08 if span > 0 else max(abs(vmax) * 0.1, 1.0)
xmin, xmax = vmin - pad, vmax + pad

fig = plt.figure(figsize=(12, 7))
gs = fig.add_gridspec(2, 1, height_ratios=[1.1, 3.2], hspace=0.03)
ax_box = fig.add_subplot(gs[0])
ax_hist = fig.add_subplot(gs[1], sharex=ax_box)
fig.subplots_adjust(left=0.08, right=0.78, top=0.93, bottom=0.1)

ax_box.boxplot(
    values,
    vert=False,
    widths=0.55,
    whis=(0, 100),
    showmeans=True,
    patch_artist=True,
    boxprops=dict(facecolor="#d7ebf3", edgecolor="black", linewidth=1.4),
    medianprops=dict(color="black", linewidth=2.0),
    whiskerprops=dict(color="black", linewidth=1.4),
    capprops=dict(color="black", linewidth=1.4),
    meanprops=dict(marker="D", markerfacecolor="#1f77b4", markeredgecolor="black", markersize=7),
)

ax_box.set_xlim(xmin, xmax)
ax_box.set_ylim(0.55, 1.45)
ax_box.set_yticks([])
ax_box.tick_params(axis="x", which="both", bottom=False, top=False, labelbottom=False)
for spine in ax_box.spines.values():
    spine.set_visible(False)

stat_labels = [
    ("Min", vmin, -28, "black"),
    ("Q1", q1, 18, "red"),
    ("Median", median, -28, "red"),
    ("Q3", q3, 18, "red"),
    ("Max", vmax, -28, "black"),
    ("Mean", mean, 18, "#1f77b4"),
]

for label, x, dy, color in stat_labels:
    ax_box.annotate(
        f"{label}\n{x:,.2f}",
        xy=(x, 1),
        xytext=(0, dy),
        textcoords="offset points",
        ha="center",
        va="bottom" if dy > 0 else "top",
        fontsize=9,
        color=color,
        bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor=color, alpha=0.95),
        clip_on=False,
        zorder=12,
    )

counts, edges, patches = ax_hist.hist(
    values,
    bins=bins,
    color="#8fbcd4",
    edgecolor="black",
    alpha=0.9
)

ax_hist.set_xlim(xmin, xmax)
ax_hist.set_xlabel(column)
ax_hist.set_ylabel("Frequency")
ax_hist.yaxis.set_major_locator(MaxNLocator(integer=True))
ax_hist.grid(axis="y", linestyle=":", alpha=0.35)
ax_hist.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x:,.2f}"))

max_count = counts.max() if len(counts) else 0
for count, left, right in zip(counts, edges[:-1], edges[1:]):
    if count > 0:
        center = (left + right) / 2
        ax_hist.text(
            center,
            count + max(max_count * 0.02, 0.05),
            f"{int(count)}",
            ha="center",
            va="bottom",
            fontsize=9
        )

dist_lines = [
    f"{edges[i]:,.2f} to {edges[i + 1]:,.2f}: {int(counts[i])}"
    for i in range(len(counts))
]
ax_hist.text(
    1.01,
    0.98,
    "Frequency distribution\n" + "\n".join(dist_lines),
    transform=ax_hist.transAxes,
    ha="left",
    va="top",
    fontsize=8.5,
    bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor="#888888", alpha=0.95)
)

fig.suptitle("Women's millions of dollars", fontsize=14, y=0.965)

fig.canvas.draw()
y0_fig = ax_hist.get_position().y0
y1_fig = ax_box.get_position().y1

for x in (q1, median, q3):
    x_disp = ax_hist.transData.transform((x, 0))[0]
    x_fig = fig.transFigure.inverted().transform((x_disp, 0))[0]
    fig.add_artist(
        Line2D(
            [x_fig, x_fig],
            [y0_fig, y1_fig],
            transform=fig.transFigure,
            color="red",
            linestyle="--",
            linewidth=1.4,
            zorder=10,
        )
    )

plt.savefig(OUTPUT_FILE, dpi=300, bbox_inches="tight")
plt.close(fig)