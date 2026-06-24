import numpy as np
import matplotlib.pyplot as plt

plot_df = df[['No.', 'IL (25°C)', 'toluene (25°C)', 'n-heptane (25°C)']].dropna().copy()
comp_cols = ['IL (25°C)', 'toluene (25°C)', 'n-heptane (25°C)']
plot_df[comp_cols] = plot_df[comp_cols].div(plot_df[comp_cols].sum(axis=1), axis=0)

groups = list(plot_df['No.'].drop_duplicates())
cmap = plt.get_cmap('tab20', max(len(groups), 1))
colors = {g: cmap(i) for i, g in enumerate(groups)}

fig = ax.figure
fig.clf()
ax_eq, ax_rt = fig.subplots(1, 2)

h = np.sqrt(3) / 2
border_eq = np.array([[0, 0], [1, 0], [0.5, h], [0, 0]])
ax_eq.plot(border_eq[:, 0], border_eq[:, 1], color='black', lw=1.2)
ax_eq.set_title('Liquid-Liquid Phase Diagram')
ax_eq.text(0.5, h + 0.05, 'toluene', ha='center', va='bottom')
ax_eq.text(-0.04, -0.04, 'n-heptane', ha='right', va='top')
ax_eq.text(1.04, -0.04, 'IL', ha='left', va='top')

border_rt = np.array([[0, 0], [1, 0], [0, 1], [0, 0]])
ax_rt.plot(border_rt[:, 0], border_rt[:, 1], color='black', lw=1.2)
ax_rt.set_title('Liquid-Liquid Phase Diagram')
ax_rt.set_xlabel('toluene')
ax_rt.set_ylabel('IL')

for no, group in plot_df.groupby('No.', sort=False):
    toluene = group['toluene (25°C)'].to_numpy()
    il = group['IL (25°C)'].to_numpy()

    x_eq = il + 0.5 * toluene
    y_eq = h * toluene
    ax_eq.plot(x_eq, y_eq, marker='o', linestyle='--', color=colors[no], markersize=5, linewidth=1.2)

    x_rt = toluene
    y_rt = il
    ax_rt.plot(x_rt, y_rt, marker='o', linestyle='--', color=colors[no], markersize=5, linewidth=1.2)

for a in (ax_eq, ax_rt):
    a.set_aspect('equal', adjustable='box')
    a.set_xticks([])
    a.set_yticks([])
    for spine in a.spines.values():
        spine.set_visible(False)

ax_eq.set_xlim(-0.08, 1.08)
ax_eq.set_ylim(-0.08, h + 0.1)
ax_rt.set_xlim(-0.05, 1.05)
ax_rt.set_ylim(-0.05, 1.05)

fig.tight_layout()