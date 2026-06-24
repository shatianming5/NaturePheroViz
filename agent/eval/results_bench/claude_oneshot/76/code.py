col = "Woman's millions of dollars"
data = df[col].dropna().astype(float)

q1 = data.quantile(0.25)
med = data.quantile(0.50)
q3 = data.quantile(0.75)
mn = data.min()
mx = data.max()
mean = data.mean()

fig = ax.get_figure()
ax.set_axis_off()
pos = ax.get_position()
fig.delaxes(ax)

ax_box = fig.add_axes([pos.x0, pos.y0 + pos.height * 0.78, pos.width, pos.height * 0.22])
ax_hist = fig.add_axes([pos.x0, pos.y0, pos.width, pos.height * 0.72], sharex=ax_box)

bp = ax_box.boxplot(data, vert=False, widths=0.6, patch_artist=True,
                    boxprops=dict(facecolor='#9ecae1', color='#3182bd'),
                    medianprops=dict(color='black', linewidth=2),
                    whiskerprops=dict(color='#3182bd'),
                    capprops=dict(color='#3182bd'),
                    flierprops=dict(marker='o', markerfacecolor='gray', markersize=4, alpha=0.5))
ax_box.set_axis_off()

for val, lbl in [(mn, 'Min'), (q1, 'Q1'), (med, 'Median'), (q3, 'Q3'), (mx, 'Max')]:
    ax_box.annotate(f'{lbl}\n{val:.1f}', xy=(val, 1), xytext=(val, 1.45),
                    ha='center', va='bottom', fontsize=8,
                    arrowprops=dict(arrowstyle='-', color='gray', lw=0.6))
ax_box.set_ylim(0.4, 2.0)

counts, bins, patches = ax_hist.hist(data, bins='auto', color='#6baed6',
                                     edgecolor='white')
ax_hist.set_xlabel(col)
ax_hist.set_ylabel('Frequency')
for c, left, right in zip(counts, bins[:-1], bins[1:]):
    if c > 0:
        ax_hist.text((left + right) / 2, c, int(c), ha='center', va='bottom', fontsize=8)

for val, color, lbl in [(q1, 'red', 'Q1'), (med, 'darkred', 'Median'), (q3, 'red', 'Q3')]:
    line = matplotlib.lines.Line2D([val, val], [0, 1], transform=ax_hist.get_xaxis_transform(),
                                   color=color, linestyle='--', linewidth=1.5, zorder=5, clip_on=False)
    ax_hist.add_line(line)
    bline = matplotlib.lines.Line2D([val, val], [0, 1], transform=ax_box.get_xaxis_transform(),
                                    color=color, linestyle='--', linewidth=1.5, zorder=5, clip_on=False)
    ax_box.add_line(bline)

ax_hist.margins(x=0)
ax_box.set_title("Distribution of " + col, fontsize=11)