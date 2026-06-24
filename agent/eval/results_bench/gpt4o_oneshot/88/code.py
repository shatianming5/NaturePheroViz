import pandas as pd
import numpy as np
from pathlib import Path
from matplotlib.patches import Wedge, Circle, Patch
from matplotlib import colors as mcolors

csv_path = Path('data.csv')
if csv_path.exists():
    df = pd.read_csv(csv_path, keep_default_na=False)
else:
    df = df.copy()

data = df[['Major Area', 'Regions', 'Country', 'Overall score']].copy()
data['Regions'] = data['Regions'].astype(str)
data['Country'] = data['Country'].astype(str)
data['Overall score'] = pd.to_numeric(data['Overall score'], errors='coerce')
data = data.dropna(subset=['Overall score'])

region_palette = {
    'Europe': '#1b5e20',
    'Asia': '#fdd835',
    'Americas': '#1e88e5',
    'Oceania': '#8e24aa',
    'Africa': '#43a047'
}

region_aliases = {
    'Europe': 'Europe',
    'Asia': 'Asia',
    'Americas': 'Americas',
    'America': 'Americas',
    'North America': 'Americas',
    'South America': 'Americas',
    'Latin America': 'Americas',
    'Latin America and the Caribbean': 'Americas',
    'Oceania': 'Oceania',
    'Africa': 'Africa',
    'NA': 'Americas'
}

def region_color(region_name):
    key = str(region_name).strip()
    return region_palette.get(region_aliases.get(key, key), '#9e9e9e')

ax.clear()
fig = ax.figure
fig.set_size_inches(10, 10, forward=True)
fig.set_dpi(100)
fig.patch.set_facecolor('white')
fig.subplots_adjust(left=0.05, right=0.82, bottom=0.05, top=0.86)
ax.set_position([0.05, 0.08, 0.72, 0.74])
ax.set_aspect('equal')
ax.axis('off')
ax.set_xlim(-1.12, 1.12)
ax.set_ylim(-1.12, 1.12)

major_totals = data.groupby('Major Area', sort=False)['Overall score'].sum()
total_value = major_totals.sum()

major_outer_radius, major_width = 0.46, 0.18
region_outer_radius, region_width = 0.69, 0.20
country_outer_radius, country_width = 0.98, 0.27

major_ranges = {}
current_angle = 90.0

if total_value > 0:
    for major_area, major_value in major_totals.items():
        sweep = 360.0 * major_value / total_value
        theta1, theta2 = current_angle, current_angle + sweep
        major_ranges[major_area] = (theta1, theta2)
        ax.add_patch(
            Wedge(
                (0, 0), major_outer_radius, theta1, theta2,
                width=major_width, facecolor='#e6e6e6',
                edgecolor='white', linewidth=1.2
            )
        )
        if sweep >= 8:
            angle = np.deg2rad((theta1 + theta2) / 2.0)
            ax.text(
                0.37 * np.cos(angle), 0.37 * np.sin(angle), str(major_area),
                ha='center', va='center', fontsize=9, color='#222222'
            )
        current_angle = theta2

    region_ranges = {}
    for major_area, (theta1, theta2) in major_ranges.items():
        major_subset = data[data['Major Area'] == major_area]
        region_totals = major_subset.groupby('Regions', sort=False)['Overall score'].sum()
        major_sum = region_totals.sum()
        region_angle = theta1
        for region_name, region_value in region_totals.items():
            sweep = (theta2 - theta1) * region_value / major_sum if major_sum else 0
            start, end = region_angle, region_angle + sweep
            region_ranges[(major_area, region_name)] = (start, end)
            ax.add_patch(
                Wedge(
                    (0, 0), region_outer_radius, start, end,
                    width=region_width, facecolor=region_color(region_name),
                    edgecolor='white', linewidth=1.2
                )
            )
            if sweep >= 6:
                angle = np.deg2rad((start + end) / 2.0)
                ax.text(
                    0.58 * np.cos(angle), 0.58 * np.sin(angle), str(region_name),
                    ha='center', va='center', fontsize=8, color='black'
                )
            region_angle = end

    for (major_area, region_name), (theta1, theta2) in region_ranges.items():
        region_subset = data[(data['Major Area'] == major_area) & (data['Regions'] == region_name)]
        country_totals = region_subset.groupby('Country', sort=False)['Overall score'].sum()
        region_sum = country_totals.sum()
        country_angle = theta1
        base_rgba = list(mcolors.to_rgba(region_color(region_name)))
        base_rgba[3] = 0.9
        for country_name, country_value in country_totals.items():
            sweep = (theta2 - theta1) * country_value / region_sum if region_sum else 0
            start, end = country_angle, country_angle + sweep
            ax.add_patch(
                Wedge(
                    (0, 0), country_outer_radius, start, end,
                    width=country_width, facecolor=tuple(base_rgba),
                    edgecolor='white', linewidth=0.8
                )
            )
            if sweep >= 4:
                mid = (start + end) / 2.0
                angle = np.deg2rad(mid)
                rotation = mid - 90
                if 90 < (mid % 360) < 270:
                    rotation += 180
                ax.text(
                    0.84 * np.cos(angle), 0.84 * np.sin(angle), str(country_name),
                    ha='center', va='center', fontsize=6,
                    rotation=rotation, rotation_mode='anchor'
                )
            country_angle = end

ax.add_patch(Circle((0, 0), 0.24, facecolor='white', edgecolor='white'))

legend_handles = [Patch(facecolor=region_palette[name], edgecolor='none', label=name) for name in ['Europe', 'Asia', 'Americas', 'Oceania', 'Africa']]
ax.legend(handles=legend_handles, loc='center left', bbox_to_anchor=(1.01, 0.5), frameon=False, title='Regions')

fig.suptitle('Global Food Security Index, 2020', fontsize=18, fontweight='bold', y=0.97)
fig.text(0.5, 0.935, 'Overall score 0-100, 100 = best environment', ha='center', va='top', fontsize=11)

major_summary = data.groupby('Major Area', sort=False)['Overall score'].mean()
inset_ax = ax.inset_axes([0.02, 0.02, 0.34, 0.22])
inset_ax.bar(major_summary.index, major_summary.values, color='#b0bec5', edgecolor='#546e7a')
inset_ax.set_title('Average score by Major Area', fontsize=8)
inset_ax.set_xlabel('Major Area', fontsize=7)
inset_ax.set_ylabel('Overall score', fontsize=7)
inset_ax.tick_params(axis='x', labelrotation=45, labelsize=6)
inset_ax.tick_params(axis='y', labelsize=6)
inset_ax.spines['top'].set_visible(False)
inset_ax.spines['right'].set_visible(False)
inset_ax.set_ylim(0, max(100, float(major_summary.max()) * 1.1 if len(major_summary) else 100))

fig.savefig('global_food_security_index_2020.png', dpi=100, facecolor='white')