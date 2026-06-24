import seaborn as sns
import matplotlib.pyplot as plt
plt.style.use('dark_background')
fig = ax.get_figure()
fig.patch.set_facecolor('#1e1e1e')
ax.set_facecolor('#1e1e1e')
palette = {'Yes': '#2ca02c', 'No': '#808080'}
sns.violinplot(data=df, x='sex', y='size', hue='smoker', split=True, inner='quartile', palette=palette, ax=ax)
ax.set_title('Distribution of Size by Sex and Smoker Status', color='white')
ax.set_xlabel('Sex', color='white')
ax.set_ylabel('Size', color='white')
ax.tick_params(colors='white')
legend = ax.legend(title='Smoker', facecolor='#1e1e1e', edgecolor='white')
plt.setp(legend.get_texts(), color='white')
plt.setp(legend.get_title(), color='white')