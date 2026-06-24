import numpy as np
import matplotlib.colors as mcolors
import matplotlib.cm as cm
from matplotlib.patches import Wedge

d = df[['country', 'continent', 'lifeExp', 'pop']].dropna()

wmean = np.average(d['lifeExp'], weights=d['pop'])
vmin, vmax = d['lifeExp'].min(), d['lifeExp'].max()
norm = mcolors.TwoSlopeNorm(vmin=vmin, vcenter=wmean, vmax=vmax)
cmap = cm.get_cmap('RdBu')

total_pop = d['pop'].sum()
start = 0.0
for cont, g in d.groupby('continent'):
    cont_pop = g['pop'].sum()
    cont_extent = cont_pop / total_pop * 360.0
    cont_start = start
    cstart = start
    for _, row in g.iterrows():
        extent = row['pop'] / total_pop * 360.0
        color = cmap(norm(row['lifeExp']))
        ax.add_patch(Wedge((0, 0), 1.0, cstart, cstart + extent, width=0.5,
                           facecolor=color, edgecolor='white', linewidth=0.3))
        cstart += extent
    ax.add_patch(Wedge((0, 0), 0.5, cont_start, cont_start + cont_extent, width=0.5,
                       facecolor='lightgray', edgecolor='white', linewidth=0.5))
    mid = np.deg2rad(cont_start + cont_extent / 2.0)
    ax.text(0.25 * np.cos(mid), 0.25 * np.sin(mid), str(cont),
            ha='center', va='center', fontsize=8)
    start += cont_extent

ax.set_xlim(-1.1, 1.1)
ax.set_ylim(-1.1, 1.1)
ax.set_aspect('equal')
ax.axis('off')

sm = cm.ScalarMappable(norm=norm, cmap=cmap)
sm.set_array([])
ax.figure.colorbar(sm, ax=ax, label='lifeExp')
