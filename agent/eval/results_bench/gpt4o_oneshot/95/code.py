import numpy as np
import pandas as pd

plot_df = df.copy()
plot_df["Date"] = pd.to_datetime(plot_df["Date"])
plot_df["Year"] = plot_df["Year"].astype(int)
plot_df = plot_df.sort_values("Date")

fig = ax.figure
if getattr(ax, "name", "") != "polar":
    pos = ax.get_position()
    ax.remove()
    ax = fig.add_axes(pos, projection="polar")
else:
    ax.clear()

month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
sector_width = 2 * np.pi / 12
month_centers = (np.arange(12) + 0.5) * sector_width

years = np.sort(plot_df["Year"].unique())
spread = sector_width * 0.45
denom = max(len(years) - 1, 1)
year_to_offset = {
    year: (i - (len(years) - 1) / 2) * (spread / denom)
    for i, year in enumerate(years)
}

plot_df["theta"] = (plot_df["Date"].dt.month - 1) * sector_width + sector_width / 2
plot_df["theta"] += plot_df["Year"].map(year_to_offset)

rmin = plot_df["Temperature"].min()
rmax = plot_df["Temperature"].max()
pad = (rmax - rmin) * 0.1 if rmax > rmin else 1

for angle in np.arange(12) * sector_width:
    ax.plot([angle, angle], [rmin - pad * 0.2, rmax + pad], color="0.88", lw=0.8, zorder=0)

ax.scatter(
    plot_df["theta"],
    plot_df["Temperature"],
    s=38,
    color="0.5",
    alpha=0.75,
    label="2004-2015",
    zorder=2,
)

plot_2015 = plot_df[plot_df["Year"] == 2015].sort_values("Date")
if not plot_2015.empty:
    ax.plot(
        plot_2015["theta"],
        plot_2015["Temperature"],
        color="blue",
        lw=2.2,
        label="2015",
        zorder=3,
    )

ax.set_theta_offset(np.pi / 2)
ax.set_theta_direction(-1)
ax.set_xticks(month_centers)
ax.set_xticklabels(month_labels)
ax.set_ylim(rmin - pad * 0.2, rmax + pad)
ax.grid(alpha=0.3)
ax.set_title("Monthly Highest Temperature in Amherst (2004-2015).")
ax.legend(loc="center left", bbox_to_anchor=(1.05, 0.5))