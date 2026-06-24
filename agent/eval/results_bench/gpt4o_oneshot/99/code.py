import seaborn as sns

ax.set_facecolor('#111111')
ax.figure.set_facecolor('#111111')
palette = {'Yes': '#2ecc71', 'No': '#9e9e9e'}

sns.violinplot(
    data=df,
    x='sex',
    y='size',
    hue='smoker',
    hue_order=['No', 'Yes'],
    split=True,
    inner='quartile',
    palette=palette,
    cut=0,
    linewidth=1.2,
    ax=ax
)

ax.set_title('Party Size by Sex and Smoking Status', color='white')
ax.set_xlabel('Sex', color='white')
ax.set_ylabel('Size', color='white')
ax.tick_params(colors='white')
for spine in ax.spines.values():
    spine.set_color('white')
ax.grid(True, color='white', alpha=0.08)

legend = ax.legend(title='Smoker', frameon=True)
legend.get_frame().set_facecolor('#111111')
legend.get_frame().set_edgecolor('white')
legend.get_title().set_color('white')
for text in legend.get_texts():
    text.set_color('white')