import numpy as np
import pandas as pd
import matplotlib.colors as mcolors
from matplotlib import cm
from matplotlib.lines import Line2D

fig = ax.figure
pos = ax.get_position()
if getattr(ax, 'name', '') != 'polar':
    ax.remove()
    ax = fig.add_axes(pos, projection='polar')

plot_df = df.copy()
plot_df['Series'] = plot_df['Series'].astype(str)
plot_df['l position'] = pd.to_numeric(plot_df['l position'], errors='coerce')
plot_df['p position'] = pd.to_numeric(plot_df['p position'], errors='coerce')
plot_df = plot_df.dropna(subset=['Series', 'Wavelength', 'l position', 'p position']).sort_values(['Series', 'p position', 'l position', 'Wavelength']).reset_index(drop=True)

ax.clear()
ax.set_theta_zero_location('E')
ax.set_theta_direction(1)
ax.set_thetamin(0)
ax.set_thetamax(180)
ax.set_ylim(0, 6.55)
ax.grid(False)
ax.set_xticks([])
ax.set_yticks([])
ax.spines['polar'].set_visible(False)
ax.set_facecolor('white')

theta_arc = np.linspace(0, np.pi, 600)
for radius in range(1, 7):
    ax.plot(theta_arc, np.full_like(theta_arc, radius), color='black', lw=1.05, zorder=2)
ax.plot([0, 0], [0, 6], color='black', lw=1.05, zorder=2)
ax.plot([np.pi, np.pi], [0, 6], color='black', lw=1.05, zorder=2)

level_centers = {i: i - 0.5 for i in range(1, 7)}
energy_labels = {1: '0 eV', 2: '10.20 eV', 3: '12.09 eV', 4: '12.75 eV', 5: '13.05 eV', 6: '13.22 eV'}
for level, r in level_centers.items():
    ax.text(np.pi - np.deg2rad(1.8), r, f'{level}n', ha='right', va='center', fontsize=10, color='black', clip_on=False)
    ax.text(np.deg2rad(1.8), r, energy_labels[level], ha='left', va='center', fontsize=10, color='black', clip_on=False)

def level_radius(value):
    try:
        value = float(value)
    except Exception:
        return np.nan
    if np.isfinite(value):
        return float(np.clip(value - 0.5, 0.25, 5.75))
    return np.nan

def lighten(color, amount=0.72):
    rgb = np.array(mcolors.to_rgb(color))
    return tuple(1 - (1 - rgb) * (1 - amount))

unique_series = list(dict.fromkeys(plot_df['Series'].tolist()))
n_series = max(len(unique_series), 1)
gap = min(np.deg2rad(6), np.pi / (4 * n_series + 4))
usable = max(np.pi - gap * (n_series + 1), np.deg2rad(30))
band_width = usable / n_series

series_meta = {}
theta_positions = np.zeros(len(plot_df))
local_order = np.zeros(len(plot_df), dtype=int)
cmap = cm.get_cmap('tab10', n_series)

cursor = gap
for i, series_name in enumerate(unique_series):
    series_idx = np.flatnonzero((plot_df['Series'] == series_name).to_numpy())
    start = cursor
    end = cursor + band_width
    color = cmap(i % cmap.N)
    series_meta[series_name] = (start, end, color)
    ax.bar((start + end) / 2, 6, width=end - start, bottom=0, color=lighten(color), alpha=0.28, edgecolor='none', zorder=1)
    if len(series_idx) == 1:
        theta_vals = np.array([(start + end) / 2])
    else:
        inner_pad = min((end - start) * 0.15, np.deg2rad(8))
        theta_vals = np.linspace(start + inner_pad, end - inner_pad, len(series_idx))
    theta_positions[series_idx] = theta_vals
    local_order[series_idx] = np.arange(len(series_idx))
    cursor = end + gap

if len(plot_df):
    p_r = np.array([level_radius(v) for v in plot_df['p position']])
    ax.plot(theta_positions, p_r, color='0.35', lw=1.2, alpha=0.75, marker='o', ms=3.5, mfc='white', mec='0.35', zorder=3)

for row_idx, row in plot_df.iterrows():
    theta = float(theta_positions[row_idx])
    color = series_meta[row['Series']][2]
    r0 = level_radius(row['l position'])
    r1 = level_radius(row['p position'])
    ax.annotate(
        '',
        xy=(theta, r1),
        xytext=(theta, r0),
        xycoords='data',
        textcoords='data',
        arrowprops=dict(arrowstyle='-|>', lw=2.0, color=color, shrinkA=0, shrinkB=0, mutation_scale=12),
        annotation_clip=False,
        zorder=4
    )
    wl = row['Wavelength']
    if isinstance(wl, (int, float, np.integer, np.floating)) and np.isfinite(wl):
        wl_text = f'{wl:g}'
    else:
        wl_text = str(wl)
    label_r = 6.17 + 0.11 * (local_order[row_idx] % 3)
    if theta < np.pi * 0.25:
        ha = 'left'
    elif theta > np.pi * 0.75:
        ha = 'right'
    else:
        ha = 'center'
    ax.text(
        theta,
        label_r,
        wl_text,
        ha=ha,
        va='bottom',
        fontsize=9,
        color=color,
        bbox=dict(boxstyle='round,pad=0.18', fc='white', ec='none', alpha=0.9),
        clip_on=False,
        zorder=5
    )

if unique_series:
    handles = [Line2D([0], [0], color=series_meta[s][2], lw=3, label=s) for s in unique_series]
    ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, 1.16), ncol=min(3, len(handles)), frameon=False, fontsize=9)

ax.set_title('Electron Transitions for an Atom', pad=22, fontsize=14)