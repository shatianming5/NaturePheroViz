import pandas as pd
import plotly.graph_objects as go

plot_df = df.copy()
plot_df["Regions"] = plot_df["Regions"].astype("string").fillna("NA")
plot_df["Overall score"] = pd.to_numeric(plot_df["Overall score"], errors="coerce")
plot_df = plot_df.dropna(subset=["Major Area", "Country", "Overall score"])

country_df = plot_df[["Major Area", "Regions", "Country", "Overall score"]].copy()
region_stats = country_df.groupby(["Major Area", "Regions"], as_index=False).agg(value=("Overall score", "sum"), color=("Overall score", "mean"))
major_stats = region_stats.groupby("Major Area", as_index=False).agg(value=("value", "sum"), color=("color", "mean"))

ids, labels, parents, values, colors = [], [], [], [], []

for row in major_stats.itertuples(index=False):
    major, value, color = row
    ids.append(f"major::{major}")
    labels.append(major)
    parents.append("")
    values.append(value)
    colors.append(color)

for row in region_stats.itertuples(index=False):
    major, region, value, color = row
    ids.append(f"region::{major}::{region}")
    labels.append(region)
    parents.append(f"major::{major}")
    values.append(value)
    colors.append(color)

for row in country_df.itertuples(index=False):
    major, region, country, score = row
    ids.append(f"country::{major}::{region}::{country}")
    labels.append(country)
    parents.append(f"region::{major}::{region}")
    values.append(score)
    colors.append(score)

fig = go.Figure(go.Sunburst(
    ids=ids,
    labels=labels,
    parents=parents,
    values=values,
    branchvalues="total",
    marker=dict(
        colors=colors,
        colorscale="Viridis",
        cmin=0,
        cmax=100,
        colorbar=dict(title="Overall score")
    ),
    hovertemplate="<b>%{label}</b><br>Value: %{value:.2f}<br>Score: %{color:.2f}<extra></extra>"
))

fig.update_layout(
    title=dict(
        text="Global Food Security Index, 2020<br><sup>Overall score 0-100, 100 = best environment</sup>",
        x=0.5
    ),
    width=1000,
    height=1000,
    margin=dict(t=100, l=20, r=20, b=20)
)
fig.write_image("global_food_security_index_2020.png", width=1000, height=1000)

major_scores = plot_df.groupby("Major Area", as_index=False)["Overall score"].mean()
ax.bar(major_scores["Major Area"], major_scores["Overall score"], color="#4C78A8")
ax.set_xlabel("Major Area")
ax.set_ylabel("Overall score")
ax.set_title("Overall score by Major Area")
ax.tick_params(axis="x", rotation=45)