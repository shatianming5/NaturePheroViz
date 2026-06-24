import numpy as np
import matplotlib.patches as mpatches
from matplotlib.path import Path

src_col, tgt_col = 'blueberry', 'blueberry.1'
flows = df.groupby([src_col, tgt_col]).size().reset_index(name='count')

sources = list(dict.fromkeys(df[src_col].astype(str)))
targets = list(dict.fromkeys(df[tgt_col].astype(str)))
all_labels = list(dict.fromkeys(list(df[src_col].astype(str)) + list(df[tgt_col].astype(str))))
cmap = plt.get_cmap('tab20') if 'plt' in dir() else __import__('matplotlib.pyplot', fromlist=['get_cmap']).get_cmap('tab20')
colors = {lbl: cmap(i % 20) for i, lbl in enumerate(all_labels)}

gap = 0.02

def node_positions(labels, weights):
    total = sum(weights.get(l, 0) for l in labels)
    total_gap = gap * max(len(labels) - 1, 0)
    scale = (1.0 - total_gap) / total if total > 0 else 0
    pos = {}
    y = 1.0
    for l in labels:
        h = weights.get(l, 0) * scale
        pos[l] = (y - h, y)
        y -= h + gap
    return pos

src_w = flows.groupby(src_col)['count'].sum().to_dict()
tgt_w = flows.groupby(tgt_col)['count'].sum().to_dict()
src_w = {str(k): v for k, v in src_w.items()}
tgt_w = {str(k): v for k, v in tgt_w.items()}
src_pos = node_positions(sources, src_w)
tgt_pos = node_positions(targets, tgt_w)

x_left, x_right, node_w = 0.0, 1.0, 0.04

total_src = sum(src_w.values()) or 1
total_tgt = sum(tgt_w.values()) or 1
scale_src = (1.0 - gap * max(len(sources) - 1, 0)) / total_src
scale_tgt = (1.0 - gap * max(len(targets) - 1, 0)) / total_tgt

src_cursor = {l: src_pos[l][1] for l in sources}
tgt_cursor = {l: tgt_pos[l][1] for l in targets}

for _, row in flows.iterrows():
    s, t, c = str(row[src_col]), str(row[tgt_col]), row['count']
    hs, ht = c * scale_src, c * scale_tgt
    s_top, t_top = src_cursor[s], tgt_cursor[t]
    s_bot, t_bot = s_top - hs, t_top - ht
    src_cursor[s] = s_bot
    tgt_cursor[t] = t_bot
    xl, xr = x_left + node_w, x_right - node_w
    xm = (xl + xr) / 2
    verts = [(xl, s_top), (xm, s_top), (xm, t_top), (xr, t_top),
             (xr, t_bot), (xm, t_bot), (xm, s_bot), (xl, s_bot), (xl, s_top)]
    codes = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4,
             Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4, Path.CLOSEPOLY]
    ax.add_patch(mpatches.PathPatch(Path(verts, codes), facecolor=colors[s], edgecolor='none', alpha=0.45))

for l in sources:
    b, top = src_pos[l]
    ax.add_patch(mpatches.Rectangle((x_left, b), node_w, top - b, color=colors[l]))
    ax.text(x_left - 0.01, (b + top) / 2, l, ha='right', va='center', fontsize=9)
for l in targets:
    b, top = tgt_pos[l]
    ax.add_patch(mpatches.Rectangle((x_right - node_w, b), node_w, top - b, color=colors[l]))
    ax.text(x_right + 0.01, (b + top) / 2, l, ha='left', va='center', fontsize=9)

ax.set_xlim(-0.2, 1.2)
ax.set_ylim(-0.05, 1.05)
ax.axis('off')
ax.set_title('Sankey Diagram: Source \u2192 Target')
fig = ax.figure
fig.savefig('sankey_diagram.png', dpi=150, bbox_inches='tight')
plt.show()