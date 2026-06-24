import numpy as np
import matplotlib.pyplot as plt

ax.clear()
species_order = list(df['Species'].dropna().unique())
colors = {species: plt.cm.tab10(i) for i, species in enumerate(species_order)}
rng = np.random.default_rng(0)

for i, species in enumerate(species_order):
    subset = df[df['Species'] == species]
    x = np.full(len(subset), i, dtype=float) + rng.normal(0, 0.04, len(subset))
    y = subset['Sepal Width(cm)'].to_numpy()
    if getattr(ax, 'name', '') == '3d':
        ax.scatter(x, y, np.zeros(len(subset)), s=36, color=colors[species], alpha=0.9, label=species)
    else:
        ax.scatter(x, y, s=36, color=colors[species], alpha=0.9, label=species)

ax.set_xticks(range(len(species_order)))
ax.set_xticklabels(species_order)
ax.set_xlabel('Species')
ax.set_ylabel('Sepal Width(cm)')
if getattr(ax, 'name', '') == '3d':
    ax.set_zlabel('')
    ax.set_zticks([])
ax.legend(title='Species')