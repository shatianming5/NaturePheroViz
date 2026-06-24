import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import PolyCollection

if not hasattr(ax, "zaxis"):
    fig = ax.figure
    if hasattr(ax, "get_subplotspec"):
        subplotspec = ax.get_subplotspec()
        ax.remove()
        ax = fig.add_subplot(subplotspec, projection="3d")
    else:
        pos = ax.get_position()
        ax.remove()
        ax = fig.add_axes(pos, projection="3d")

time = pd.to_numeric(df["Time(sec)"], errors="coerce").to_numpy()
order = np.argsort(np.nan_to_num(time, nan=np.inf))
time = time[order]

series_cols = list(df.columns[1:])
colors = plt.cm.viridis(np.linspace(0, 1, len(series_cols)))
markers = ["o", "s", "^", "D", "v", "P", "X", "*"]
y_positions = np.arange(len(series_cols), dtype=float) * 2.0

z_min, z_max = 0.0, 0.0
for i, col in enumerate(series_cols):
    z = pd.to_numeric(df[col], errors="coerce").to_numpy()[order]
    mask = np.isfinite(time) & np.isfinite(z)
    x = time[mask]
    z = z[mask]
    if x.size == 0:
        continue

    y = np.full(x.shape, y_positions[i], dtype=float)
    ax.plot(
        x, y, z,
        color=colors[i],
        marker=markers[i % len(markers)],
        linewidth=1.8,
        markersize=4,
        markevery=max(1, len(x) // 12),
        label=str(col)
    )

    verts = [list(zip(np.r_[x[0], x, x[-1]], np.r_[0, z, 0]))]
    poly = PolyCollection(verts, facecolors=["lightgrey"], edgecolors="none", alpha=0.25)
    ax.add_collection3d(poly, zs=y_positions[i], zdir="y")

    z_min = min(z_min, float(np.nanmin(z)))
    z_max = max(z_max, float(np.nanmax(z)))

finite_time = time[np.isfinite(time)]
if finite_time.size:
    ax.set_xlim(float(finite_time.min()), float(finite_time.max()))
if len(y_positions):
    ax.set_ylim(float(y_positions.min()) - 1.0, float(y_positions.max()) + 1.0)
ax.set_zlim(z_min, z_max if z_max > z_min else z_min + 1.0)

if hasattr(ax, "set_box_aspect"):
    ax.set_box_aspect((1, 2, 1))
ax.view_init(elev=15, azim=-69)
ax.set_xlabel("Time (sec)")
ax.set_ylabel("Frequency (Hz)")
ax.set_zlabel("Amplitude (a.u.)")
ax.set_yticks([])