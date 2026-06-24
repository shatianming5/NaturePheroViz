import numpy as np
from matplotlib import cm, colors

t = df["t"].to_numpy()
energy = df["tot energy / Eh"].to_numpy()

norm = colors.Normalize(vmin=float(np.min(t)), vmax=float(np.max(t)))
cmap = cm.get_cmap("jet")
bar_colors = cmap(norm(t))

width = (np.min(np.diff(np.unique(np.sort(t)))) * 0.8) if len(np.unique(t)) > 1 else 0.8
ax.bar(t, energy, width=width, color=bar_colors, edgecolor="none", alpha=0.8)

ax.set_xlabel("Time / fs")
ax.set_ylabel("Total Energy / Eh")
ax.set_title("AIMD Total Energy vs Time")

sm = cm.ScalarMappable(norm=norm, cmap=cmap)
sm.set_array([])
cbar = ax.figure.colorbar(sm, ax=ax, pad=0.02)
cbar.set_label("Time / fs")