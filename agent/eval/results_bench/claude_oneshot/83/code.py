import pandas as pd
import numpy as np
import matplotlib.dates as mdates

df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date')

x = df['date']
dow = df['Dow Jones Industrial Average']
ma = df['1 year moving average']

ax.plot(x, dow, color='steelblue', linewidth=1.2, label='Dow Jones Industrial Average')
ax.plot(x, ma, color='darkorange', linewidth=1.5, label='1 year moving average')

ax.fill_between(x, dow, ma, where=(dow >= ma), interpolate=True, color='green', alpha=0.3, label='Above moving average')
ax.fill_between(x, dow, ma, where=(dow < ma), interpolate=True, color='red', alpha=0.3, label='Below moving average')

ax.set_title('Dow Jones Industrial Average (Oct 2006 - Aug 2013)')
ax.set_xlabel('Date')
ax.set_ylabel('Index Value')
ax.legend(loc='upper left')

ax.xaxis.set_major_locator(mdates.YearLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
for label in ax.get_xticklabels():
    label.set_rotation(45)
    label.set_ha('right')

ax.figure.tight_layout()