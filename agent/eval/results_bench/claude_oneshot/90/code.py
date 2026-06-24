import plotly.express as px
import pandas as pd

# Ensure 'NA' in Regions is treated as a string, not NaN
df['Regions'] = df['Regions'].fillna('NA').astype(str)

# Compute averages for coloring: country = own score, region = avg of countries, continent = avg of regions
region_avg = df.groupby(['Major Area', 'Regions'])['Overall score'].mean().reset_index()
continent_avg = region_avg.groupby('Major Area')['Overall score'].mean().reset_index()

fig = px.sunburst(
    df,
    path=['Major Area', 'Regions', 'Country'],
    values='Overall score',
    color='Overall score',
    color_continuous_scale='RdYlGn',
    range_color=[0, 100],
)

fig.update_layout(
    title={
        'text': 'Global Food Security Index, 2020<br><sup>Overall score 0-100, 100 = best environment</sup>',
        'x': 0.5,
        'xanchor': 'center'
    },
    coloraxis_colorbar=dict(title='Overall score'),
    width=1000,
    height=1000,
)

fig.write_image('sunburst_chart.png', width=1000, height=1000)
