import numpy as np
import pandas as pd
from matplotlib.patches import Patch

df = df.copy()
df['Time'] = pd.to_datetime(df['Time'])
df = df.sort_values('Time').reset_index(drop=True)

fig = ax.figure
if getattr(ax, 'name', '') != 'polar':
    pos = ax.get_position()
    ax.remove()
    ax = fig.add_axes(pos, projection='polar')

pollution = pd.to_numeric(df['Pollution Index'], errors='coerce').interpolate(limit_direction='both').to_numpy()
water_temp = pd.to_numeric(df['Water Temp'], errors='coerce').interpolate(limit_direction='both').to_numpy()

n = len(df)
theta = np.linspace(0, 2 * np.pi, n, endpoint=False)

inner_hole = 1.15
pollution_band = 2.35
separator_gap = 0.5
temp_band = 2.35

def scale_to_band(values, width):
    vmin = np.nanmin(values)
    vmax = np.nanmax(values)
    if np.isclose(vmax, vmin):
        return np.full(values.shape, width * 0.5, dtype=float)
    return (values - vmin) / (vmax - vmin) * width

pollution_top = inner_hole + scale_to_band(pollution, pollution_band)
separator_radius = inner_hole + pollution_band + separator_gap
temp_top = separator_radius + scale_to_band(water_temp, temp_band)

theta_c = np.r_[theta, theta[0]]
inner_c = np.r_[np.full(n, inner_hole), inner_hole]
pollution_c = np.r_[pollution_top, pollution_top[0]]
separator_c = np.r_[np.full(n, separator_radius), separator_radius]
temp_c = np.r_[temp_top, temp_top[0]]

ax.set_theta_zero_location('N')
ax.set_theta_direction(-1)
ax.set_facecolor('white')

ax.fill_between(theta_c, inner_c, pollution_c, color='red', alpha=0.35, linewidth=0, zorder=2)
ax.plot(theta_c, pollution_c, color='red', linewidth=2, zorder=3)

ax.fill_between(theta_c, pollution_c, separator_c, color='white', linewidth=0, zorder=4)
ax.plot(theta_c, np.full_like(theta_c, inner_hole), color='white', linewidth=5, zorder=5)
ax.plot(theta_c, np.full_like(theta_c, separator_radius), color='white', linewidth=5, zorder=5)

ax.fill_between(theta_c, separator_c, temp_c, color='#1f77b4', alpha=0.35, linewidth=0, zorder=2)
ax.plot(theta_c, temp_c, color='#1f77b4', linewidth=2, zorder=3)

disk_theta = np.linspace(0, 2 * np.pi, 721)
ax.fill_between(disk_theta, 0, inner_hole, color='white', zorder=6)

pollution_theta = theta[int(np.nanargmax(pollution_top))]
temp_theta = theta[int(np.nanargmax(temp_top))]
ax.plot([pollution_theta, pollution_theta], [0, float(np.max(pollution_top))], color='red', linewidth=1.8, zorder=7)
ax.plot([temp_theta, temp_theta], [0, float(np.max(temp_top))], color='#1f77b4', linewidth=1.8, zorder=7)

day_starts = df['Time'].dt.normalize().drop_duplicates().index.to_numpy()
if len(day_starts) > 8:
    day_starts = day_starts[np.linspace(0, len(day_starts) - 1, 8, dtype=int)]
tick_angles = 2 * np.pi * day_starts / n
tick_labels = df.loc[day_starts, 'Time'].dt.strftime('%Y-%m-%d')
ax.set_xticks(tick_angles)
ax.set_xticklabels(tick_labels, fontsize=9)
ax.tick_params(axis='x', pad=12)
ax.set_yticklabels([])
ax.set_ylim(0, float(np.max(temp_top)) + 0.5)
ax.grid(color='0.85')
ax.spines['polar'].set_visible(False)

ax.set_title('Stacked Radial Plots with Hourly Data', pad=24)
ax.legend(
    handles=[
        Patch(facecolor='red', edgecolor='red', alpha=0.35, label='Pollution Index'),
        Patch(facecolor='#1f77b4', edgecolor='#1f77b4', alpha=0.35, label='Water Temp')
    ],
    loc='upper right',
    bbox_to_anchor=(1.18, 1.12)
)