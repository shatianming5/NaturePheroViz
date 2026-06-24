import numpy as np
import pandas as pd

months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
dt = pd.to_datetime(df['Date'])
month = dt.dt.month
year = df['Year'].astype(int)
temp = df['Temperature'].astype(float)

base_angles = (month - 1) * (2 * np.pi / 12)
rng = np.random.RandomState(0)
offset = (rng.rand(len(df)) - 0.5) * (2 * np.pi / 12) * 0.6
theta = base_angles + offset

ax.scatter(theta, temp, s=20, alpha=0.6, label='2004-2015')

mask2015 = year == 2015
t15 = base_angles[mask2015]
temp15 = temp[mask2015]
order = np.argsort(month[mask2015].values)
ax.plot(t15.values[order], temp15.values[order], color='blue', marker='o', label='2015')

ax.set_xticks(np.arange(12) * (2 * np.pi / 12))
ax.set_xticklabels(months)
ax.set_theta_direction(-1)
ax.set_theta_offset(np.pi / 2)
ax.legend(loc='center left', bbox_to_anchor=(1.05, 0.5))
ax.set_title('Monthly Highest Temperature in Amherst (2004-2015)')