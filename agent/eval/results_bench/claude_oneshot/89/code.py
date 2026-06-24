import numpy as np

# Aggregate inner ring (Browser) totals
browser_totals = df.groupby('Browser', sort=False)['Data'].sum()
browsers = list(browser_totals.index)
browser_vals = browser_totals.values

# Build outer ring data in browser order
outer_labels = []
outer_vals = []
for b in browsers:
    sub = df[df['Browser'] == b]
    for _, row in sub.iterrows():
        outer_labels.append(str(row['Version']))
        outer_vals.append(row['Data'])

total = float(sum(browser_vals))
size = 0.3
cmap = plt.get_cmap('tab20')
inner_colors = [cmap(i % 20) for i in range(len(browsers))]
# Assign outer colors as lighter shades grouped by browser
outer_colors = []
ci = 0
for i, b in enumerate(browsers):
    n = len(df[df['Browser'] == b])
    base = np.array(cmap((i % 20)))
    for j in range(n):
        shade = base.copy()
        shade[:3] = shade[:3] * (1 - 0.12 * (j % 4)) + 0.12 * (j % 4)
        outer_colors.append(tuple(shade))

# Inner ring: browser names written on segments
inner_wedges, _ = ax.pie(
    browser_vals,
    radius=1 - size,
    colors=inner_colors,
    labels=browsers,
    labeldistance=0.75,
    startangle=90,
    counterclock=False,
    wedgeprops=dict(width=size, edgecolor='w', linewidth=2),
    textprops=dict(ha='center', va='center', fontsize=9, color='white', fontweight='bold'),
)

# Outer ring: versions with leader lines and labels
outer_wedges, _ = ax.pie(
    outer_vals,
    radius=1,
    colors=outer_colors,
    startangle=90,
    counterclock=False,
    wedgeprops=dict(width=size, edgecolor='w', linewidth=1.5),
)

bbox_props = dict(boxstyle='round,pad=0.3', fc='w', ec='0.6', lw=0.7)
kw = dict(arrowprops=dict(arrowstyle='-', color='0.4'),
          bbox=bbox_props, zorder=5, va='center', fontsize=8)
for w, lbl in zip(outer_wedges, outer_labels):
    ang = (w.theta2 - w.theta1) / 2.0 + w.theta1
    y = np.sin(np.deg2rad(ang))
    x = np.cos(np.deg2rad(ang))
    ha = 'right' if x < 0 else 'left'
    conn = 'angle,angleA=0,angleB={}'.format(ang)
    kw['arrowprops']['connectionstyle'] = conn
    ax.annotate(lbl, xy=(x, y), xytext=(1.35 * np.sign(x), 1.3 * y),
                horizontalalignment=ha, **kw)

ax.set_title('Browser Market Share', fontsize=14, fontweight='bold')
ax.set(aspect='equal')
