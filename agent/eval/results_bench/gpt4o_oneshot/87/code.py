import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import Wedge

ax.clear()
for extra_ax in list(ax.figure.axes):
    if extra_ax is not ax and extra_ax.get_label() in {'country_iso_num_inset', 'lifeexp_colorbar'}:
        extra_ax.remove()

plot_df = df[['continent', 'country', 'lifeExp', 'pop', 'iso_num']].dropna(subset=['continent', 'country', 'lifeExp', 'pop']).copy()
plot_df = plot_df[plot_df['pop'] > 0]
plot_df['weighted_life'] = plot_df['lifeExp'] * plot_df['pop']

country_df = plot_df.groupby(['continent', 'country'], as_index=False).agg(
    pop=('pop', 'sum'),
    weighted_life=('weighted_life', 'sum'),
    iso_num=('iso_num', 'mean')
)
country_df['lifeExp'] = country_df['weighted_life'] / country_df['pop']
country_df['weighted_life'] = country_df['lifeExp'] * country_df['pop']

continent_df = country_df.groupby('continent', as_index=False).agg(
    pop=('pop', 'sum'),
    weighted_life=('weighted_life', 'sum')
)
continent_df['lifeExp'] = continent_df['weighted_life'] / continent_df['pop']
continent_df = continent_df.sort_values(['pop', 'continent'], ascending=[False, True])

weighted_avg_life = np.average(country_df['lifeExp'], weights=country_df['pop'])
vmin = country_df['lifeExp'].min()
vmax = country_df['lifeExp'].max()
if np.isclose(vmin, vmax):
    norm = mcolors.Normalize(vmin=vmin - 0.5, vmax=vmax + 0.5)
elif vmin < weighted_avg_life < vmax:
    norm = mcolors.TwoSlopeNorm(vmin=vmin, vcenter=weighted_avg_life, vmax=vmax)
else:
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
cmap = plt.cm.RdBu

inner_radius = 0.28
continent_width = 0.24
country_width = 0.38
total_pop = country_df['pop'].sum()
start_angle = 90.0

for _, cont in continent_df.iterrows():
    cont_countries = country_df[country_df['continent'] == cont['continent']].sort_values(['pop', 'country'], ascending=[False, True])
    cont_angle = 360.0 * cont['pop'] / total_pop
    theta1, theta2 = start_angle, start_angle + cont_angle

    ax.add_patch(Wedge(
        (0, 0),
        inner_radius + continent_width,
        theta1,
        theta2,
        width=continent_width,
        facecolor=cmap(norm(cont['lifeExp'])),
        edgecolor='white',
        linewidth=1.5
    ))

    mid = 0.5 * (theta1 + theta2)
    ang = np.deg2rad(mid)
    ax.text(
        (inner_radius + continent_width * 0.55) * np.cos(ang),
        (inner_radius + continent_width * 0.55) * np.sin(ang),
        cont['continent'],
        ha='center',
        va='center',
        fontsize=10,
        fontweight='bold'
    )

    country_start = theta1
    for _, row in cont_countries.iterrows():
        country_angle = 360.0 * row['pop'] / total_pop
        c1, c2 = country_start, country_start + country_angle
        ax.add_patch(Wedge(
            (0, 0),
            inner_radius + continent_width + country_width,
            c1,
            c2,
            width=country_width,
            facecolor=cmap(norm(row['lifeExp'])),
            edgecolor='white',
            linewidth=0.8
        ))

        if country_angle >= 5:
            mid_country = 0.5 * (c1 + c2)
            ang_country = np.deg2rad(mid_country)
            rotation = mid_country - 90
            if 90 < mid_country < 270:
                rotation += 180
            ax.text(
                (inner_radius + continent_width + country_width * 0.6) * np.cos(ang_country),
                (inner_radius + continent_width + country_width * 0.6) * np.sin(ang_country),
                row['country'],
                rotation=rotation,
                rotation_mode='anchor',
                ha='center',
                va='center',
                fontsize=7
            )
        country_start = c2

    start_angle = theta2

ax.text(0, 0, f'Pop-weighted\navg lifeExp\n{weighted_avg_life:.1f}', ha='center', va='center', fontsize=10)

sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
sm.set_array([])
cbar = ax.figure.colorbar(sm, ax=ax, fraction=0.045, pad=0.04)
cbar.ax.set_label('lifeexp_colorbar')
cbar.set_label('Life expectancy')

ax.set_aspect('equal')
outer_radius = inner_radius + continent_width + country_width
ax.set_xlim(-outer_radius - 0.15, outer_radius + 0.15)
ax.set_ylim(-outer_radius - 0.15, outer_radius + 0.15)
ax.axis('off')
ax.set_title('Population-weighted sunburst of life expectancy by continent and country')

other_source = country_df.dropna(subset=['iso_num']).sort_values('iso_num')
if not other_source.empty:
    other_df = other_source.tail(min(15, len(other_source)))
    other_ax = ax.figure.add_axes([0.72, 0.08, 0.24, 0.22], label='country_iso_num_inset')
    other_ax.bar(other_df['country'], other_df['iso_num'], color='0.6')
    other_ax.set_title('Country vs iso_num', fontsize=9)
    other_ax.set_xlabel('country', fontsize=7)
    other_ax.set_ylabel('iso_num', fontsize=7)
    other_ax.tick_params(axis='x', rotation=90, labelsize=6)
    other_ax.tick_params(axis='y', labelsize=7)
    other_ax.grid(axis='y', alpha=0.25)