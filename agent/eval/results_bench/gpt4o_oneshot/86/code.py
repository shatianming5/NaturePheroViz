import numpy as np
from matplotlib import colors as mcolors
from matplotlib.patches import Patch

ax.clear()
df_plot = df.copy()
years = [str(c) for c in df_plot.columns[1:]]
versions = df_plot['Version'].tolist()
for year in years:
    df_plot[year] = df_plot[year].astype(float).fillna(0.0)

base_colors = {
    'WinXP': '#d95f02',
    'Win7': '#1f77b4',
    'Win8.1': '#2ca02c',
    'Win10': '#9467bd',
}
fallback = ['#d95f02', '#1f77b4', '#2ca02c', '#9467bd']
for i, version in enumerate(versions):
    base_colors.setdefault(version, fallback[i % len(fallback)])

def tint(color, strength):
    rgb = np.array(mcolors.to_rgb(color))
    return tuple(1 - (1 - rgb) * strength)

shade_levels = np.linspace(0.45, 1.0, len(years))
ring_colors = {
    version: [tint(base_colors[version], s) for s in shade_levels]
    for version in versions
}

ax.set_aspect('equal')
hole_radius = 0.48
ring_width = 0.18
gap = 0.015
step = ring_width + gap

for i, year in enumerate(years):
    values = df_plot[year].to_numpy(dtype=float)
    other = max(0.0, 100.0 - values.sum())
    sizes = np.r_[other, values]
    colors = ['white'] + [ring_colors[version][i] for version in versions]
    startangle = 90 + other * 1.8
    wedges, _ = ax.pie(
        sizes,
        radius=hole_radius + ring_width + i * step,
        startangle=startangle,
        counterclock=False,
        colors=colors,
        wedgeprops=dict(width=ring_width, edgecolor='white', linewidth=1),
    )

    mid_r = hole_radius + i * step + ring_width / 2
    for j, wedge in enumerate(wedges):
        theta = np.deg2rad((wedge.theta1 + wedge.theta2) / 2)
        x = mid_r * np.cos(theta)
        y = mid_r * np.sin(theta)
        if j == 0:
            ax.text(x, y, year, ha='center', va='center', fontsize=9, weight='bold', color='black')
        else:
            val = sizes[j]
            if val > 0:
                label = f'{val:.1f}%' if abs(val - round(val)) > 1e-6 else f'{int(round(val))}%'
                ax.text(x, y, label, ha='center', va='center', fontsize=7 if val < 4 else 8, color='black')

legend_handles = [Patch(facecolor=ring_colors[version][-1], edgecolor='none', label=version) for version in versions]
ax.legend(
    handles=legend_handles,
    loc='center',
    bbox_to_anchor=(0.5, 0.5),
    frameon=False,
    fontsize=9,
)

ax.set_title('Desktop Windows Version Market Share Worldwide', pad=20)
outer_r = hole_radius + ring_width + (len(years) - 1) * step
ax.set_xlim(-outer_r - 0.25, outer_r + 0.25)
ax.set_ylim(-outer_r - 0.25, outer_r + 0.25)

inset = ax.inset_axes([0.73, 0.05, 0.24, 0.22])
bar_colors = [ring_colors[version][-1] for version in versions]
bars = inset.bar(df_plot['Version'], df_plot['2019'], color=bar_colors, edgecolor='white', linewidth=0.8)
inset.set_title('2019', fontsize=9)
inset.set_ylabel('%', fontsize=8)
inset.tick_params(axis='x', labelrotation=35, labelsize=7)
inset.tick_params(axis='y', labelsize=7)
inset.spines['top'].set_visible(False)
inset.spines['right'].set_visible(False)
for bar, val in zip(bars, df_plot['2019']):
    inset.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f'{float(val):.1f}%', ha='center', va='bottom', fontsize=6)
