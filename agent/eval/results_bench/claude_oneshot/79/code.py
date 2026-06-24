import numpy as np
species = df['Species'].astype('category')
cats = list(species.cat.categories)
colors = plt.cm.tab10(np.linspace(0, 1, len(cats)))
for i, sp in enumerate(cats):
    sub = df[df['Species'] == sp]
    ax.scatter([sp] * len(sub), sub['Sepal Width(cm)'], color=colors[i], label=sp)
ax.set_xlabel('Species')
ax.set_ylabel('Sepal Width(cm)')
ax.legend(title='Species')