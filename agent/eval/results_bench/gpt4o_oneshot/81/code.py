import matplotlib.pyplot as plt
from matplotlib import patches
from matplotlib.path import Path

data = df[['blueberry', 'blueberry.1']].dropna().astype(str)
if data.empty:
    raise ValueError('df has no non-null rows in blueberry and blueberry.1')

pair_counts = data.groupby(['blueberry', 'blueberry.1']).size().reset_index(name='value')
source_totals = pair_counts.groupby('blueberry')['value'].sum().sort_values(ascending=False)
target_totals = pair_counts.groupby('blueberry.1')['value'].sum().sort_values(ascending=False)
grand_total = float(pair_counts['value'].sum())

source_order = list(source_totals.index)
target_order = list(target_totals.index)
all_labels = list(dict.fromkeys(source_order + target_order))
cmap = plt.get_cmap('tab20', max(len(all_labels), 1))
label_colors = {label: cmap(i) for i, label in enumerate(all_labels)}

full_height = 0.9

def calc_gap(n):
    return 0 if n <= 1 else min(0.03, full_height / (n * 6.0))

source_gap = calc_gap(len(source_order))
target_gap = calc_gap(len(target_order))
source_unit = (full_height - source_gap * max(len(source_order) - 1, 0)) / grand_total
target_unit = (full_height - target_gap * max(len(target_order) - 1, 0)) / grand_total
unit = min(source_unit, target_unit)

def build_positions(labels, totals, gap, unit_height):
    total_height = grand_total * unit_height + gap * max(len(labels) - 1, 0)
    top = 0.5 + total_height / 2.0
    positions = {}
    cursor = top
    for label in labels:
        height = float(totals[label]) * unit_height
        y1 = cursor
        y0 = y1 - height
        positions[label] = (y0, y1)
        cursor = y0 - gap
    return positions

source_pos = build_positions(source_order, source_totals, source_gap, unit)
target_pos = build_positions(target_order, target_totals, target_gap, unit)

source_rank = {label: i for i, label in enumerate(source_order)}
target_rank = {label: i for i, label in enumerate(target_order)}
pair_counts = pair_counts.assign(
    source_rank=pair_counts['blueberry'].map(source_rank),
    target_rank=pair_counts['blueberry.1'].map(target_rank)
).sort_values(['source_rank', 'target_rank', 'blueberry', 'blueberry.1']).reset_index(drop=True)

source_offsets = {label: source_pos[label][1] for label in source_order}
target_offsets = {label: target_pos[label][1] for label in target_order}

ax.clear()
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis('off')

left_x, right_x = 0.1, 0.84
node_w = 0.06
flow_left_x = left_x + node_w
flow_right_x = right_x
ctrl_left_x = 0.36
ctrl_right_x = 0.64

for _, row in pair_counts.iterrows():
    source = row['blueberry']
    target = row['blueberry.1']
    height = float(row['value']) * unit

    sy1 = source_offsets[source]
    sy0 = sy1 - height
    source_offsets[source] = sy0

    ty1 = target_offsets[target]
    ty0 = ty1 - height
    target_offsets[target] = ty0

    vertices = [
        (flow_left_x, sy1),
        (ctrl_left_x, sy1),
        (ctrl_right_x, ty1),
        (flow_right_x, ty1),
        (flow_right_x, ty0),
        (ctrl_right_x, ty0),
        (ctrl_left_x, sy0),
        (flow_left_x, sy0),
        (flow_left_x, sy1),
    ]
    codes = [
        Path.MOVETO,
        Path.CURVE4, Path.CURVE4, Path.CURVE4,
        Path.LINETO,
        Path.CURVE4, Path.CURVE4, Path.CURVE4,
        Path.CLOSEPOLY,
    ]
    ax.add_patch(
        patches.PathPatch(
            Path(vertices, codes),
            facecolor=label_colors[source],
            edgecolor='none',
            alpha=0.35,
        )
    )

for label in source_order:
    y0, y1 = source_pos[label]
    ax.add_patch(
        patches.Rectangle(
            (left_x, y0),
            node_w,
            y1 - y0,
            facecolor=label_colors[label],
            edgecolor='white',
            linewidth=1.0,
        )
    )
    ax.text(left_x - 0.02, (y0 + y1) / 2.0, label, ha='right', va='center', fontsize=10)

for label in target_order:
    y0, y1 = target_pos[label]
    ax.add_patch(
        patches.Rectangle(
            (right_x, y0),
            node_w,
            y1 - y0,
            facecolor=label_colors[label],
            edgecolor='white',
            linewidth=1.0,
        )
    )
    ax.text(right_x + node_w + 0.02, (y0 + y1) / 2.0, label, ha='left', va='center', fontsize=10)

ax.set_title('Sankey Diagram: blueberry -> blueberry.1', fontsize=13, pad=12)
ax.figure.tight_layout()
ax.figure.savefig('sankey_diagram.png', dpi=300, bbox_inches='tight')
plt.show()