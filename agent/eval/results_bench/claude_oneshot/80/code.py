import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm

z = df.iloc[0].astype(float).values
x = df.columns.astype(float).values
n = len(z)
X, Y = np.meshgrid(np.arange(n), np.arange(n))
Z = np.sqrt(np.outer(z, z))
Z = (Z - Z.min()) / (Z.max() - Z.min()) * (z.max() - z.min()) + z.min()

base = z.min() - 40
contour_level = z.max() + 20
grid_level = z.max() + 60

base_offset = np.full_like(Z, base)
ax.contourf(X, Y, Z, zdir='z', offset=base, levels=20, cmap=cm.terrain)

surf = ax.plot_surface(X, Y, Z, color='saddlebrown', alpha=0.85, linewidth=0, antialiased=True, shade=True)

cs = ax.contour(X, Y, Z, zdir='z', offset=contour_level, levels=12, cmap=cm.viridis)

gx, gy = np.meshgrid(np.linspace(0, n - 1, 10), np.linspace(0, n - 1, 10))
gz = np.full_like(gx, grid_level)
ax.plot_wireframe(gx, gy, gz, color='gray', linewidth=0.7)

mappable = cm.ScalarMappable(cmap=cm.terrain)
mappable.set_array(Z)
cbar = plt.colorbar(mappable, ax=ax, shrink=0.6, pad=0.1)
cbar.set_label('Height (m)')

ax.set_zlim(base, grid_level + 20)
ax.view_init(elev=35, azim=-60)
ax.set_xlabel('X')
ax.set_ylabel('Y')
ax.set_zlabel('Height (m)')
