import seaborn as sns
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter
from matplotlib.transforms import blended_transform_factory

# solution plan
# i. Clean the Women's millions of dollars column and compute min, Q1, median, Q3, max, and mean.
# ii. Create a shared-x composite figure with an axis-free horizontal box plot on top and a histogram below.
# iii. Annotate key statistics on the box plot, add legend-ready reference lines, and draw continuous red dashed quartile guides across both panels.
def plot(data: pd.DataFrame):

    sns.set_theme(style="whitegrid")

    values = pd.to_numeric(data["Woman_s_millions_of_dollars"], errors="coerce").dropna()

    fig = )
    gs = fig.add_gridspec(2, 1, height_ratios=[1.1, 4], hspace=0.0)
    ax_box = fig.add_subplot(gs[0])
    ax_hist = fig.add_subplot(gs[1], sharex=ax_box)

    if values.empty:
        ax_hist.text(0.5, 0.5, "No valid data available", ha="center", va="center", transform=ax_hist.transAxes)
        ax_box.axis("off")
        ax_hist.axis("off")
    else:
        min_val = values.min()
        q1 = values.quantile(0.25)
        median = values.quantile(0.50)
        q3 = values.quantile(0.75)
        max_val = values.max()
        mean_val = values.mean()

        data_range = max_val - min_val
        pad = data_range * 0.05 if data_range > 0 else max(abs(min_val) * 0.05, 1.0)
        x_min, x_max = min_val - pad, max_val + pad

        sns.boxplot(
            x=values,
            ax=ax_box,
            orient="h",
            color="#8ecae6",
            width=0.35,
            linewidth=1.3,
            fliersize=3
        )

        bins = 18 if values.nunique() >= 18 else max(5, int(values.nunique()))
        sns.histplot(
            values,
            bins=bins,
            ax=ax_hist,
            color="#4c78a8",
            edgecolor="white",
            alpha=0.85
        )

        ax_hist.axvline(mean_val, color="#2a9d8f", linestyle="-", linewidth=2, zorder=4, label=f"Mean: {mean_val:.2f}")
        ax_hist.axvline(median, color="#6a4c93", linestyle="-.", linewidth=2, zorder=4, label=f"Median: {median:.2f}")

        ax_box.set_xlim(x_min, x_max)
        ax_hist.set_xlim(x_min, x_max)

        trans = blended_transform_factory(ax_box.transData, ax_box.transAxes)
        stat_labels = [
            (min_val, "Min", 0.90),
            (q1, "Q1", 0.72),
            (median, "Median", 0.54),
            (q3, "Q3", 0.72),
            (max_val, "Max", 0.90),
        ]
        for x_val, name, y_pos in stat_labels:
            ax_box.text(
                x_val,
                y_pos,
                f"{name}\n{x_val:.2f}",
                transform=trans,
                ha="center",
                va="bottom",
                fontsize=9,
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="#999999", alpha=0.95),
                clip_on=False
            )

        for patch in ax_hist.patches:
            height = patch.get_height()
            if height > 0:
                ax_hist.text(
                    patch.get_x() + patch.get_width() / 2,
                    height,
                    f"{int(height)}",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color="#1f1f1f"
                )

        ax_box.set_xlabel("")
        ax_box.set_ylabel("")
        ax_box.set_yticks([])
        ax_box.tick_params(axis="x", bottom=False, labelbottom=False)
        ax_box.grid(False)
        for spine in ax_box.spines.values():
            spine.set_visible(False)

        ax_hist.set_xlabel("Women's millions of dollars")
        ax_hist.set_ylabel("Frequency")
        ax_hist.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{x:,.0f}"))
        ax_hist.tick_params(axis="x", rotation=0)
        ax_hist.grid(axis="y", alpha=0.3)

        fig.canvas.draw()
        y0 = ax_hist.get_position().y0
        y1 = ax_box.get_position().y1
        for x_val in [q1, median, q3]:
            fig_x = fig.transFigure.inverted().transform(ax_hist.transData.transform((x_val, 0)))[0]
            fig.add_artist(
                Line2D(
                    [fig_x, fig_x],
                    [y0, y1],
                    transform=fig.transFigure,
                    color="red",
                    linestyle="--",
                    linewidth=1.5,
                    zorder=3
                )
            )

        legend_handles = [
            Patch(facecolor="#4c78a8", edgecolor="white", label="Histogram"),
            Line2D([0], [0], color="red", linestyle="--", linewidth=1.5, label=f"Quartile guides: Q1={q1:.2f}, Q2={median:.2f}, Q3={q3:.2f}"),
            Line2D([0], [0], color="#2a9d8f", linestyle="-", linewidth=2, label=f"Mean: {mean_val:.2f}"),
            Line2D([0], [0], color="#6a4c93", linestyle="-.", linewidth=2, label=f"Median: {median:.2f}")
        ]
        ax_hist.legend(handles=legend_handles, title="Legend", loc="upper right", frameon=True)

    plt.title("Write a code to load 'data.csv' and visualize the \"Women's millions of dollars\" column with a composite graph: an axis-free box plot above and a histogram below. Label key statistics on the box plot and detail the frequency distribution in the histogram. Highlight quartiles with continuous red dashed lines across both sections, ensuring no breaks.", wrap=True)
    return plt;

chart = plot(data)