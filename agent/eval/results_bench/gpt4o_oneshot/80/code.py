import numpy as np
from matplotlib import cm, colors

ax.clear()

if not hasattr(ax, 'plot_surface'):
    raise TypeError('ax must be a 3D matplotlib Axes')

Z = np.asarray(df, dtype=float)
if Z.ndim == 1:
    Z = Z[np.newaxis, :]

x = np.asarray(df.columns, dtype=float)
try:
    y = np.asarray(df.index, dtype=float)
    if np.isnan(y).any():
        raise ValueError
except Exception:
    y = np.arange(Z.shape[0], dtype=float)

if Z.shape[0] == 1:
    step_y = float(np.diff(y).mean()) if y.size > 1 else 1.0
    y = np.array([y[0], y[0] + (step_y if step_y != 0 else 1.0)], dtype=float)
    Z = np.vstack([Z, Z])
if Z.shape[1] == 1:
    step_x = float(np.diff(x).mean()) if x.size > 1 else max(abs(x[0]) * 0.01, 1.0)
    x = np.array([x[0], x[0] + (step_x if step_x != 0 else 1.0)], dtype=float)
    Z = np.hstack([Z, Z])

X, Y = np.meshgrid(x, y)

zmin, zmax = float(np.nanmin(Z)), float(np.nanmax(Z))
zr = zmax - zmin if zmax > zmin else 1.0
base_z = zmin - 0.35 * zr
contour_z = zmax + 0.20 * zr
grid_z = zmax + 0.50 * zr

norm = colors.Normalize(vmin=zmin, vmax=zmax)
terrain_cmap = cm.get_cmap('terrain')
terrain_colors = terrain_cmap(norm(Z))

ax.plot_surface(X, Y, np.full_like(Z, base_z), facecolors=terrain_colors, shade=False, linewidth=0, antialiased=False)
ax.plot_surface(X, Y, Z, color='saddlebrown', alpha=0.92, linewidth=0, antialiased=True, shade=True)

if zmax > zmin:
    levels = np.linspace(zmin, zmax, 12)
    ax.contour(X, Y, Z, zdir='z', offset=contour_z, levels=levels, cmap='turbo', linewidths=1.6)

ax.plot_wireframe(
    X, Y, np.full_like(Z, grid_z),
    rstride=max(1, Z.shape[0] // 15),
    cstride=max(1, Z.shape[1] // 15),
    color='black', linewidth=0.6, alpha=0.75
)

x_span = float(np.ptp(x)) if x.size > 1 else 1.0
y_span = float(np.ptp(y)) if y.size > 1 else 1.0
bar_y = y.max() + 0.10 * (y_span if y_span != 0 else 1.0)
ax.bar([510.1], [583.3 - base_z], zs=bar_y, zdir='y',
       width=max(0.015 * (x_span if x_span != 0 else 1.0), 0.5),
       bottom=base_z, color='royalblue', edgecolor='black', alpha=0.9)

mappable = cm.ScalarMappable(norm=norm, cmap=terrain_cmap)
mappable.set_array([])
cbar = ax.figure.colorbar(mappable, ax=ax, shrink=0.70, pad=0.10)
cbar.set_label('Height (m)')

ax.set_xlabel('X')
ax.set_ylabel('Y')
ax.set_zlabel('Z')
ax.set_xlim(x.min(), x.max())
ax.set_ylim(y.min(), bar_y + 0.10 * (y_span if y_span != 0 else 1.0))
ax.set_zlim(base_z, grid_z + 0.15 * zr)
ax.set_box_aspect((max(x_span, 1.0), max(y_span, 1.0), max((grid_z + 0.15 * zr) - base_z, 1.0)))
ax.view_init(elev=32, azim=-60)
ax.grid(False)