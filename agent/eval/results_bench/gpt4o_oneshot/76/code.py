from matplotlib.lines import Line2D

fig = ax.figure
for other_ax in fig.axes[:]:
    if other_ax is not ax:
        fig.delaxes(other_ax)
for artist in list(fig.artists):
    artist.remove()
ax.clear()

col = next((c for c in ["Women's millions of dollars", "Woman's millions of dollars"] if c in df.columns), None)
if col is None:
    raise KeyError("Could not find a women's millions of dollars column in df.")

values = df[col].dropna().astype(float)
if values.empty:
    raise ValueError("The selected column has no numeric data to plot.")

q1 = values.quantile(0.25)
median = values.quantile(0.5)
q3 = values.quantile(0.75)
vmin = values.min()
vmax = values.max()

pos = ax.get_position()
hist_h = pos.height * 0.68
gap_h = pos.height * 0.08
box_h = pos.height * 0.22
ax.set_position([pos.x0, pos.y0, pos.width, hist_h])
box_ax = fig.add_axes([pos.x0, pos.y0 + hist_h + gap_h, pos.width, box_h], sharex=ax)

xpad = (vmax - vmin) * 0.05 if vmax > vmin else 1.0
ax.set_xlim(vmin - xpad, vmax + xpad)

box_ax.boxplot(
    values,
    vert=False,
    widths=0.55,
    whis=(0, 100),
    showfliers=False,
    patch_artist=True,
    boxprops=dict(facecolor="#d9e6f2", edgecolor="black"),
    medianprops=dict(color="black", linewidth=1.5),
    whiskerprops=dict(color="black"),
    capprops=dict(color="black"),
)
box_ax.set_ylim(0.55, 1.38)
box_ax.axis("off")

for label, x, y in [
    ("Min", vmin, 0.78),
    ("Q1", q1, 1.28),
    ("Median", median, 1.12),
    ("Q3", q3, 1.28),
    ("Max", vmax, 0.78),
]:
    box_ax.text(x, y, f"{label}\n{x:.2f}", ha="center", va="center", fontsize=9)

counts, edges, _ = ax.hist(values, bins="auto", color="#7aa6c2", edgecolor="black", alpha=0.85)
for count, left, right in zip(counts, edges[:-1], edges[1:]):
    if count > 0:
        ax.text((left + right) / 2, count, f"{int(count)}", ha="center", va="bottom", fontsize=9)

ax.set_xlabel(col)
ax.set_ylabel("Frequency")
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.grid(axis="y", linestyle=":", alpha=0.35)
ax.set_ylim(0, max(counts) * 1.18 if len(counts) and max(counts) > 0 else 1)

fig.canvas.draw()
for x in (q1, median, q3):
    x_fig = fig.transFigure.inverted().transform(ax.transData.transform((x, 0)))[0]
    fig.add_artist(
        Line2D(
            [x_fig, x_fig],
            [ax.get_position().y0, box_ax.get_position().y1],
            transform=fig.transFigure,
            color="red",
            linestyle="--",
            linewidth=1.25,
            zorder=10,
        )
    )