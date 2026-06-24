import numpy as np
from matplotlib.colors import Normalize

cols = ['0-60 mph(sec)', 'Gas Mileage(mpg)', 'Power(kW)', 'Engine Displacement(cc)']
data = df[cols].dropna().copy()

x = data['0-60 mph(sec)'].to_numpy(dtype=float)
y = data['Gas Mileage(mpg)'].to_numpy(dtype=float)
z = data['Power(kW)'].to_numpy(dtype=float)
disp = data['Engine Displacement(cc)'].to_numpy(dtype=float)

fig = ax.figure
fig.patch.set_facecolor('white')

base_pos = ax.get_position()
bar_ax = ax
bar_ax.set_position([base_pos.x0, base_pos.y0, base_pos.width, base_pos.height * 0.22])

x_range = np.ptp(x) if np.ptp(x) else 1.0
y_range = np.ptp(y) if np.ptp(y) else 1.0
z_range = np.ptp(z) if np.ptp(z) else 1.0
disp_range = np.ptp(disp) if np.ptp(disp) else 1.0

bar_ax.bar(
    x,
    disp,
    width=max(x_range / max(len(x) * 1.8, 1), 0.12),
    color='#7c3aed',
    alpha=0.8,
    edgecolor='white',
    linewidth=0.6
)
bar_ax.set_xlabel('0-60 mph (sec)')
bar_ax.set_ylabel('Engine Displacement (cc)')
bar_ax.set_title('Acceleration vs Engine Displacement', fontsize=10, pad=6)
bar_ax.grid(axis='y', alpha=0.25, linewidth=0.8)
bar_ax.spines['top'].set_visible(False)
bar_ax.spines['right'].set_visible(False)
bar_ax.set_facecolor('white')

ax = fig.add_axes([base_pos.x0, base_pos.y0 + base_pos.height * 0.28, base_pos.width, base_pos.height * 0.72], projection='3d')

norm = Normalize(vmin=disp.min(), vmax=disp.max())
sizes = 50 + 240 * (disp - disp.min()) / disp_range

x_plane = x.min() - 0.12 * x_range
y_plane = y.min() - 0.12 * y_range
z_plane = z.min() - 0.12 * z_range

sc = ax.scatter(x, y, z, c=disp, s=sizes, cmap='viridis', norm=norm, alpha=0.72, edgecolors='white', linewidths=0.5, depthshade=True)
ax.scatter(x, y, np.full(x.shape, z_plane), s=sizes * 0.45, c='tab:blue', alpha=0.18, edgecolors='none', depthshade=False)
ax.scatter(x, np.full(y.shape, y_plane), z, s=sizes * 0.45, c='tab:red', alpha=0.18, edgecolors='none', depthshade=False)
ax.scatter(np.full(x.shape, x_plane), y, z, s=sizes * 0.45, c='tab:green', alpha=0.18, edgecolors='none', depthshade=False)

ax.set_xlim(x_plane, x.max() + 0.08 * x_range)
ax.set_ylim(y_plane, y.max() + 0.08 * y_range)
ax.set_zlim(z_plane, z.max() + 0.08 * z_range)

ax.set_xlabel('0-60 mph (sec)', labelpad=10)
ax.set_ylabel('Gas Mileage (mpg)', labelpad=10)
ax.set_zlabel('Power (kW)', labelpad=10)
ax.set_title('Car Performance in 3D', pad=14)
ax.view_init(elev=24, azim=-58)
ax.set_proj_type('persp')
ax.set_facecolor('white')

for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
    axis.pane.set_facecolor((1.0, 1.0, 1.0, 0.0))
    axis._axinfo['grid']['color'] = (0.82, 0.82, 0.82, 0.7)
    axis._axinfo['grid']['linewidth'] = 0.8

cbar = fig.colorbar(sc, ax=ax, pad=0.08, shrink=0.8)
cbar.set_label('Engine Displacement (cc)')