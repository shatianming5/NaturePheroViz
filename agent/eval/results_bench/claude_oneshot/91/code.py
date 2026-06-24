import numpy as np
from matplotlib.collections import PolyCollection

x = df['Time(sec)'].values
freq_cols = [c for c in df.columns if c != 'Time(sec)']
n = len(freq_cols)
colors = plt.cm.viridis(np.linspace(0, 1, n))
markers = ['o', 's', '^', 'D', 'v', 'P', '*', 'X']
verts = []
for i, col in enumerate(freq_cols):
    z = df[col].values
    y = i
    ax.plot(x, np.full_like(x, y, dtype=float), z, color=colors[i], marker=markers[i % len(markers)], markersize=4, label=str(col))
    poly = list(zip(x, z))
    poly = [(x[0], 0)] + poly + [(x[-1], 0)]
    verts.append(poly)
poly_collection = PolyCollection(verts, facecolors='lightgrey', alpha=0.5)
poly_collection.set_sort_zpos(0)
ax.add_collection3d(poly_collection, zs=range(n), zdir='y')
ax.view_init(elev=15, azim=-69)
try:
    ax.set_box_aspect((1, 2, 1))
except Exception:
    pass
ax.set_yticks([])
ax.set_xlabel('Time (sec)')
ax.set_ylabel('Frequency (Hz)')
ax.set_zlabel('Amplitude (a.u.)')
