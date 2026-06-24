import seaborn as sns
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from matplotlib.patches import Ellipse, Patch
from matplotlib.lines import Line2D

# solution plan
# i. Standardize the numeric protein-consumption fields and fit K-Means with 3 clusters.
# ii. Project the standardized data and cluster centroids into 2D with PCA for plotting.
# iii. Draw a labeled seaborn scatter plot with centroid links, semi-transparent ellipses, and a clear legend.

def plot(data: pd.DataFrame):

    sns.set_theme(style="whitegrid")
    df = data.copy()

    alias_map = {
        "Country": ["Country"],
        "Red_Meat": ["Red_Meat", "Red Meat"],
        "White_Meat": ["White_Meat", "White Meat"],
        "Eggs": ["Eggs"],
        "Milk": ["Milk"],
        "Fish": ["Fish"],
        "Cereals": ["Cereals"],
        "Starch": ["Starch"],
        "Nuts": ["Nuts"],
        "Fruits___Vegetables": ["Fruits___Vegetables", "Fruits & Vegetables"],
    }

    rename_dict = {}
    for canonical, aliases in alias_map.items():
        for alias in aliases:
            if alias in df.columns:
                rename_dict[alias] = canonical
                break

    df = df.rename(columns=rename_dict).copy()

    features = [
        "Red_Meat", "White_Meat", "Eggs", "Milk", "Fish",
        "Cereals", "Starch", "Nuts", "Fruits___Vegetables"
    ]
    required_cols = ["Country"] + features

    for col in features:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=required_cols).copy()

    scaler = StandardScaler()
    X = scaler.fit_transform(df[features])

    kmeans = KMeans(n_clusters=3, random_state=42, n_init=20)
    df["Cluster"] = kmeans.fit_predict(X)

    pca = PCA(n_components=2, random_state=42)
    coords_2d = pca.fit_transform(X)
    centroids_2d = pca.transform(kmeans.cluster_centers_)

    df["PC1"] = coords_2d[:, 0]
    df["PC2"] = coords_2d[:, 1]
    df["Cluster_Name"] = df["Cluster"].map(lambda x: f"Cluster {x + 1}")

    )
    palette = sns.color_palette("Set2", 3)
    color_map = {f"Cluster {i + 1}": palette[i] for i in range(3)}

    for i in range(3):
        subset = df[df["Cluster"] == i]
        color = palette[i]

        for _, row in subset.iterrows():
            ax.plot(
                [row["PC1"], centroids_2d[i, 0]],
                [row["PC2"], centroids_2d[i, 1]],
                color=color,
                alpha=0.35,
                linewidth=0.9,
                zorder=1
            )

        points = subset[["PC1", "PC2"]].to_numpy()
        if len(points) > 0:
            if len(points) == 1:
                center = points[0]
                width, height, angle = 0.8, 0.8, 0
            else:
                cov = np.cov(points, rowvar=False)
                if not np.all(np.isfinite(cov)):
                    cov = np.eye(2) * 0.1
                vals, vecs = np.linalg.eigh(cov)
                vals = np.clip(vals, 1e-4, None)
                order = vals.argsort()[::-1]
                vals, vecs = vals[order], vecs[:, order]
                angle = np.degrees(np.arctan2(vecs[1, 0], vecs[0, 0]))
                width, height = 4 * np.sqrt(vals)
                center = points.mean(axis=0)

            ellipse = Ellipse(
                xy=center,
                width=width,
                height=height,
                angle=angle,
                facecolor=color,
                edgecolor=color,
                alpha=0.18,
                linewidth=2,
                zorder=0
            )
            ax.add_patch(ellipse)

    sns.scatterplot(
        data=df,
        x="PC1",
        y="PC2",
        hue="Cluster_Name",
        palette=color_map,
        s=90,
        edgecolor="black",
        linewidth=0.6,
        legend=False,
        ax=ax
    )

    ax.scatter(
        centroids_2d[:, 0],
        centroids_2d[:, 1],
        marker="X",
        s=240,
        c=palette,
        edgecolor="black",
        linewidth=1.2,
        zorder=4
    )

    for _, row in df.iterrows():
        ax.annotate(
            str(row["Country"]),
            (row["PC1"], row["PC2"]),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=9
        )

    legend_handles = [
        Line2D([0], [0], marker="o", color="w", label=f"Cluster {i + 1}",
               markerfacecolor=palette[i], markeredgecolor="black", markersize=9)
        for i in range(3)
    ]
    legend_handles += [
        Line2D([0], [0], marker="X", color="w", label="Centroids",
               markerfacecolor="gray", markeredgecolor="black", markersize=10),
        Line2D([0], [0], color="gray", lw=1.2, alpha=0.6, label="Point-to-centroid lines"),
        Patch(facecolor="gray", edgecolor="gray", alpha=0.18, label="Cluster ellipses")
    ]

    ax.legend(handles=legend_handles, title="Legend", loc="best", frameon=True)
    ax.set_xlabel(f'PCA Component 1 ({pca.explained_variance_ratio_[0] * 100:.1f}% variance)')
    ax.set_ylabel(f'PCA Component 2 ({pca.explained_variance_ratio_[1] * 100:.1f}% variance)')
    ax.tick_params(axis="x", labelrotation=0)
    ax.set_title(
        "K-Means Clusters of European Protein Consumption\n"
        "2D PCA Projection with Centroids, Links, and Cluster Ellipses"
    )
    ax.grid(True, linestyle="--", alpha=0.3)
    plt.tight_layout()
    return plt

chart = plot(data)