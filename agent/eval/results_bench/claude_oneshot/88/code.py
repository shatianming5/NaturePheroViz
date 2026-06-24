import numpy as np
import matplotlib.pyplot as plt

region_colors = {
    'Europe': 'darkgreen',
    'Asia': 'gold',
    'Americas': 'blue',
    'Oceania': 'purple',
    'Africa': 'green',
}

def _shade(color, factor):
    rgb = np.array(plt.matplotlib.colors.to_rgb(color))
    return tuple(rgb + (1.0 - rgb) * factor)

data = df.copy()
data['Overall score'] = pd.to_numeric(data['Overall score'], errors='coerce').fillna(0)

levels = ['Major Area', 'Regions', 'Country']
radius_step = 1.0
inner_radius = 1.0

major_groups = data.groupby('Major Area', sort=False)['Overall score'].sum()
major_total = major_groups.sum()

major_sizes, major_colors, major_labels = [], [], []
for major in major_groups.index:
    sub = data[data['Major Area'] == major]
    rep_region = sub['Regions'].iloc[0]
    base = region_colors.get(rep_region, 'grey')
    major_sizes.append(major_groups[major])
    major_colors.append(_shade(base, 0.0))
    major_labels.append(major)

ax.set(aspect='equal')

size = 0.33

wedges0, _ = ax.pie(
    major_sizes, radius=inner_radius, colors=major_colors,
    labels=major_labels, labeldistance=None,
    wedgeprops=dict(width=size, edgecolor='white'),
    startangle=90,
)

region_sizes, region_colors_list, region_labels = [], [], []
for major in major_groups.index:
    sub = data[data['Major Area'] == major]
    rg = sub.groupby('Regions', sort=False)['Overall score'].sum()
    for region in rg.index:
        base = region_colors.get(region, 'grey')
        region_sizes.append(rg[region])
        region_colors_list.append(_shade(base, 0.15))
        region_labels.append(region)

ax.pie(
    region_sizes, radius=inner_radius + size, colors=region_colors_list,
    labels=region_labels, labeldistance=None,
    wedgeprops=dict(width=size, edgecolor='white'),
    startangle=90,
)

country_sizes, country_colors_list, country_labels = [], [], []
for major in major_groups.index:
    sub = data[data['Major Area'] == major]
    for region in sub['Regions'].drop_duplicates():
        rsub = sub[sub['Regions'] == region]
        base = region_colors.get(region, 'grey')
        for _, row in rsub.iterrows():
            country_sizes.append(row['Overall score'])
            country_colors_list.append(_shade(base, 0.30))
            country_labels.append(row['Country'])

ax.pie(
    country_sizes, radius=inner_radius + 2 * size, colors=country_colors_list,
    labels=country_labels, labeldistance=None,
    wedgeprops=dict(width=size, edgecolor='white'),
    startangle=90,
)

legend_order = ['Europe', 'Asia', 'Americas', 'Oceania', 'Africa']
handles = [plt.matplotlib.patches.Patch(facecolor=region_colors[r], label=r) for r in legend_order]
ax.legend(handles=handles, title='Regions', loc='center left', bbox_to_anchor=(1.0, 0.5), frameon=False)

fig = ax.figure
fig.suptitle('Global Food Security Index, 2020', fontsize=16, fontweight='bold')
ax.set_title('Overall score 0-100, 100 = best environment', fontsize=11)

fig.set_size_inches(10, 10)
fig.savefig('sunburst_chart.png', dpi=100)