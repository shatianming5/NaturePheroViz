df = df.sort_values('Series')
ax.plot(df['Series'], df['p position'], marker='o', linestyle='-')
ax.set_xlabel('Series')
ax.set_ylabel('p position')
ax.set_title('Electron Transitions for an Atom')
for label in ax.get_xticklabels():
    label.set_rotation(45)
    label.set_ha('right')
ax.figure.tight_layout()