plot_df = df[['Temperature(K)', 'Pressure(Gas)']].dropna().sort_values('Temperature(K)')
temps_k = plot_df['Temperature(K)']
pressures_pa = plot_df['Pressure(Gas)']

bar_width = 1.0
if len(temps_k) > 1:
    diffs = temps_k.diff().dropna().abs()
    if not diffs.empty:
        bar_width = max(float(diffs.median()) * 0.9, 1e-6)

positive_pressures = pressures_pa[pressures_pa > 0]
log_bottom = float(positive_pressures.min()) / 10.0 if not positive_pressures.empty else 1e-3

ax.bar(
    temps_k,
    pressures_pa,
    width=bar_width,
    bottom=log_bottom,
    color='tab:blue',
    alpha=0.7,
    edgecolor='black',
    linewidth=0.6,
    label='Pressure (Gas)'
)

ax.set_yscale('log')
ax.set_xlabel('Temperature (K)')
ax.set_ylabel('Pressure (Pa; 1 mbar = 100 Pa)')
ax.set_title('Water Phase Diagram')
ax.grid(True, which='both', linestyle='--', alpha=0.4)

secax_x = ax.secondary_xaxis('top', functions=(lambda k: k - 273.15, lambda c: c + 273.15))
secax_x.set_xlabel('Temperature (degC)')

secax_y = ax.secondary_yaxis('right', functions=(lambda pa: pa / 1e5, lambda bar: bar * 1e5))
secax_y.set_ylabel('Pressure (bar)')

ax.axvline(273.15, color='red', linestyle='--', linewidth=1.5, label='Freezing point (1 atm)')
ax.axvline(373.15, color='red', linestyle='-.', linewidth=1.5, label='Boiling point (1 atm)')

ax.scatter(273.16, 611.657, color='purple', s=50, zorder=5)
ax.annotate('Triple point', xy=(273.16, 611.657), xytext=(8, 8), textcoords='offset points', color='purple')

ax.scatter(647.396, 22.064e6, color='darkgreen', s=50, zorder=5)
ax.annotate('Critical point', xy=(647.396, 22.064e6), xytext=(8, -14), textcoords='offset points', color='darkgreen')

ax.set_ylim(log_bottom, max(float(pressures_pa.max()) * 1.2 if not pressures_pa.empty else 1.0, 22.064e6 * 1.2))
ax.legend()