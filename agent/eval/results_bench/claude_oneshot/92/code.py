import numpy as np
import matplotlib.dates as mdates

df = df.copy()
df['Time'] = pd.to_datetime(df['Time'])
df = df.sort_values('Time').reset_index(drop=True)

n = len(df)
angles = np.linspace(0, 2 * np.pi, n, endpoint=False)

def _norm(s):
    s = pd.to_numeric(s, errors='coerce').astype(float)
    lo, hi = np.nanmin(s), np.nanmax(s)
    if hi == lo:
        return np.zeros_like(s)
    return (s - lo) / (hi - lo)

poll = _norm(df['Pollution Index'])
temp = _norm(df['Water Temp'])

hollow = 1.0
band = 1.0
gap = 0.35

poll_r = hollow + poll * band
ring_base = hollow + band + gap
temp_r = ring_base + temp * band

ca = np.concatenate([angles, angles[:1]])
poll_rc = np.concatenate([poll_r, poll_r[:1]])
temp_rc = np.concatenate([temp_r, temp_r[:1]])

ax.set_ylim(0, ring_base + band + 0.1)

ax.fill_between(ca, hollow, poll_rc, color='red', alpha=0.3)
ax.plot(ca, poll_rc, color='red', linewidth=1.8, label='Pollution Index')

ax.fill_between(ca, ring_base, temp_rc, color='blue', alpha=0.3)
ax.plot(ca, temp_rc, color='blue', linewidth=1.8, label='Water Temp')

ax.fill_between(ca, hollow - 0.0, hollow, color='white')
ax.fill_between(ca, hollow + band, ring_base, color='white')

ax.set_rorigin(-0.2)
ax.set_yticklabels([])

ax.set_xticks(angles)
ax.set_xticklabels([t.strftime('%Y-%m-%d') for t in df['Time']], fontsize=8)
ax.tick_params(axis='x', pad=8)

ax.set_title('Stacked Radial Plots with Hourly Data', va='bottom')
ax.legend(loc='upper right', bbox_to_anchor=(1.15, 1.1))
