import pandas as pd
import matplotlib.dates as mdates

df = df.copy()
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date")

x = df["date"]
djia = df["Dow Jones Industrial Average"]
ma = df["1 year moving average"]

ax.plot(x, djia, color="tab:blue", linewidth=2, label="Dow Jones Industrial Average")
ax.plot(x, ma, color="tab:orange", linewidth=2, label="1 year moving average")

ax.fill_between(x, djia, ma, where=(djia >= ma), interpolate=True, color="green", alpha=0.2, label="DJIA above MA")
ax.fill_between(x, djia, ma, where=(djia < ma), interpolate=True, color="red", alpha=0.2, label="DJIA below MA")

ax.set_title("Dow Jones Industrial Average (Oct 2006 to Aug 2013)")
ax.set_xlabel("Date")
ax.set_ylabel("Index Value")
ax.legend()

ax.xaxis.set_major_locator(mdates.YearLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
ax.figure.autofmt_xdate()