import matplotlib as mpl
from math import cos, sin, radians

ax.clear()
plot_df = df.dropna(subset=["Browser", "Version", "Data"]).copy()
plot_df["Data"] = plot_df["Data"].astype(float)
browser_order = plot_df["Browser"].drop_duplicates().tolist()
browser_rank = {browser: i for i, browser in enumerate(browser_order)}
plot_df = plot_df.assign(_browser_rank=plot_df["Browser"].map(browser_rank)).sort_values(["_browser_rank"], kind="stable")
browser_totals = plot_df.groupby("Browser", sort=False)["Data"].sum()

cmap = mpl.colormaps["tab20"]
browser_colors = {
    browser: cmap(i / max(1, len(browser_order) - 1) if len(browser_order) > 1 else 0)
    for i, browser in enumerate(browser_order)
}

def blend_with_white(color, amount):
    r, g, b, a = mpl.colors.to_rgba(color)
    return (r + (1 - r) * amount, g + (1 - g) * amount, b + (1 - b) * amount, a)

outer_colors = []
for browser, group in plot_df.groupby("Browser", sort=False):
    n = len(group)
    for j in range(n):
        outer_colors.append(blend_with_white(browser_colors[browser], 0.15 + 0.45 * (j / max(1, n - 1))))

outer_radius, outer_width = 1.0, 0.22
inner_radius, inner_width = 0.74, 0.22

outer_wedges, _ = ax.pie(
    plot_df["Data"],
    radius=outer_radius,
    startangle=90,
    counterclock=False,
    labels=None,
    colors=outer_colors,
    wedgeprops=dict(width=outer_width, edgecolor="white", linewidth=3),
)

inner_wedges, _ = ax.pie(
    browser_totals.values,
    radius=inner_radius,
    startangle=90,
    counterclock=False,
    labels=None,
    colors=[browser_colors[browser] for browser in browser_order],
    wedgeprops=dict(width=inner_width, edgecolor="white", linewidth=4),
)

for wedge, browser in zip(inner_wedges, browser_order):
    angle = (wedge.theta1 + wedge.theta2) / 2
    r = inner_radius - inner_width / 2
    x, y = r * cos(radians(angle)), r * sin(radians(angle))
    rotation = angle - 90
    if 90 < angle < 270:
        rotation += 180
    cr, cg, cb, _ = mpl.colors.to_rgba(browser_colors[browser])
    luminance = 0.2126 * cr + 0.7152 * cg + 0.0722 * cb
    ax.text(
        x,
        y,
        str(browser),
        ha="center",
        va="center",
        rotation=rotation,
        rotation_mode="anchor",
        fontsize=10,
        weight="bold",
        color="white" if luminance < 0.55 else "black",
    )

for wedge, (_, row) in zip(outer_wedges, plot_df.iterrows()):
    angle = (wedge.theta1 + wedge.theta2) / 2
    x, y = cos(radians(angle)), sin(radians(angle))
    ax.annotate(
        str(row["Version"]),
        xy=((outer_radius - outer_width / 2) * x, (outer_radius - outer_width / 2) * y),
        xytext=(1.28 * (1 if x >= 0 else -1), 1.18 * y),
        ha="left" if x >= 0 else "right",
        va="center",
        fontsize=9,
        arrowprops=dict(arrowstyle="-", color="gray", lw=1.0, shrinkA=0, shrinkB=0, connectionstyle="arc3,rad=0.15"),
    )

ax.add_artist(mpl.patches.Circle((0, 0), inner_radius - inner_width - 0.02, color="white"))
ax.set(aspect="equal", title="Browser Market Share")
ax.set_xlim(-1.45, 1.45)
ax.set_ylim(-1.28, 1.28)
ax.set_axis_off()