import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "charts"

# What does it cost to trade these markets? Descriptive only, no significance tests.
# The design is in METHOD_market_quality.md, written before any result was computed.
FEE_MULT = 0.07     # Kalshi taker fee per contract = FEE_MULT * P * (1 - P), today's general formula
FEE_LEVELS = [0, 1, 2]
MAX_SPREAD = 0.20
MIN_ROWS = 30       # cells under this many daily rows are too small to describe
DAY_BINS = [0, 1, 3, 7, 14, 30, np.inf]
DAY_LABELS = ["0-1", "1-3", "3-7", "7-14", "14-30", "30+"]

def fee(p, k=1):
    return k * FEE_MULT * p * (1 - p)

# One row per market per day: the candle's closing bid, ask and last price, and the day's volume
markets = pd.read_csv(HERE / "markets.csv")
close = pd.to_datetime(markets["close_time"], utc=True, format="ISO8601")
markets["close_utc"] = close

# Era by the market's close time in US Eastern: at or after noon = legacy, before noon = new.
# Ambiguous = fits neither description in the brief (about 7pm ET, or 08:25-08:29 ET).
et = close.dt.tz_convert("America/New_York")
markets["era"] = np.where(et.dt.hour >= 12, "legacy", "new")
markets["ambiguous"] = ~(et.dt.hour.isin([18, 19]) | (et.dt.hour == 8))
markets["close_et"] = et.dt.strftime("%H:%M")
print(f"Markets: {len(markets)}. By era:", markets["era"].value_counts().to_dict())
print("Ambiguous (ET close time in neither 18:00-19:59 nor 08:00-08:59):", int(markets["ambiguous"].sum()),
      markets[markets["ambiguous"]].groupby("event_type").size().to_dict())
print("\nClose clock time (US Eastern) by event type and era, number of markets:")
print(markets.groupby(["event_type", "era", "close_et"]).size().rename("markets").reset_index().to_string(index=False))
print("\nClose dates by era:")
print(markets.groupby("era")["close_utc"].agg(["min", "max"]).apply(lambda c: c.dt.strftime("%Y-%m-%d")).to_string())

d = pd.read_csv(HERE / "prices.csv").merge(
    markets[["ticker", "event_type", "close_utc", "era", "ambiguous"]], on="ticker")
d["days"] = (d["close_utc"] - pd.to_datetime(d["date"], utc=True, format="ISO8601")).dt.total_seconds() / 86400
print(f"\nDaily rows: {len(d)} from {d['ticker'].nunique()} markets")
print(f"  dropped, candle ends after the market closed (days to close < 0): {(d['days'] < 0).sum()}")
d = d[d["days"] >= 0].copy()
print(f"  kept: {len(d)}")

# Tradable two-sided quote, same rule as tradability.py
d["spread"] = d["yes_ask"] - d["yes_bid"]
d["tradable"] = (d["yes_bid"] > 0) & (d["yes_ask"] > 0) & (d["yes_ask"] < 1) & (d["spread"] <= MAX_SPREAD)
d["mid"] = (d["yes_bid"] + d["yes_ask"]) / 2
# Cost to take a position and hold to settlement: half the spread plus the fee at the mid.
# Assumes one contract fills at the quote; depth is unknown.
for k in FEE_LEVELS:
    d[f"cost_{k}x"] = d["spread"] / 2 + fee(d["mid"], k)
d["day_bin"] = pd.cut(d["days"], DAY_BINS, right=False, labels=DAY_LABELS)
buckets = [f"{i*10}-{i*10+10}%" for i in range(10)]
d["bucket"] = pd.cut(d["mid"], np.linspace(0, 1, 11), labels=buckets, include_lowest=True)
print(f"  with a tradable quote: {d['tradable'].sum()} ({d['tradable'].mean():.1%})")

def profile(g):
    """Liquidity and cost summary for one cell. Spread and cost use tradable rows only."""
    t = g[g["tradable"]]
    out = {"rows": len(g), "tradable_rows": len(t),
           "tradable_share": len(t) / len(g) if len(g) else np.nan,
           "spread_median": t["spread"].median() * 100, "spread_mean": t["spread"].mean() * 100,
           "volume_median": g["volume"].median()}
    for k in FEE_LEVELS:
        out[f"cost_{k}x"] = t[f"cost_{k}x"].median() * 100
    out["too_small"], out["few_tradable"] = len(g) < MIN_ROWS, len(t) < MIN_ROWS
    return out

def table(name, df, by):
    """One profile row per group of `by`, with empty groups kept so every cell is shown."""
    rows = [{"table": name, **dict(zip(by, key if isinstance(key, tuple) else (key,))), **profile(g)}
            for key, g in df.groupby(by, observed=False)]
    return pd.DataFrame(rows)

def show(title, t):
    print(f"\n{title}")
    print(t.drop(columns="table").round(2).to_string(index=False))
    return t

pd.set_option("display.width", 250)
note = "Spread and cost in cents per contract, tradable rows only. Volume = contracts per day, all rows."
print("\n" + note)
tables = [
    show("TABLE 1. By event type", table("1 event type", d, ["event_type"])),
    show("TABLE 2. By days to close", table("2 days to close", d, ["day_bin"])),
    show("TABLE 3. By mid-price bucket (tradable rows only)", table("3 price bucket", d[d["tradable"]], ["bucket"])),
    show("TABLE 4a. By era, all markets", table("4a era, all markets", d, ["era"])),
    show("TABLE 4b. By era, excluding ambiguous markets", table("4b era, excl. ambiguous", d[~d["ambiguous"]], ["era"])),
    show("TABLE 4c. By era within CPI, Jobs and Unemployment",
         table("4c era within type", d[d["event_type"].isin(["CPI", "Jobs", "Unemployment"])], ["event_type", "era"])),
]
t5 = show("TABLE 5 (main). Event type x days to close", table("5 type x days", d, ["event_type", "day_bin"]))
tables.append(t5)

# Table 6: spread vs volume, terciles of daily volume within each event type (tradable rows)
rows = []
for etype, g in d[d["tradable"]].groupby("event_type"):
    rho = g["spread"].corr(g["volume"], method="spearman")
    groups = pd.qcut(g["volume"], 3, duplicates="drop")
    for i, (interval, h) in enumerate(g.groupby(groups, observed=True), 1):
        rows.append({"table": "6 spread vs volume", "event_type": etype, "volume_group": f"{i} of {groups.cat.categories.size}",
                     "volume_min": h["volume"].min(), "volume_max": h["volume"].max(), "tradable_rows": len(h),
                     "spread_median": h["spread"].median() * 100, "spread_mean": h["spread"].mean() * 100,
                     "spearman": rho, "weak": abs(rho) < 0.2, "zero_volume_share": (g["volume"] == 0).mean()})
t6 = show("TABLE 6. Spread by daily-volume tercile within event type (tradable rows). spearman = rank\n"
          "correlation of spread with volume for the whole event type; weak = |spearman| under 0.2.\n"
          "Fewer than 3 groups means zero-volume days made tercile edges coincide: with 2 groups, group 1 is\n"
          "the bottom two-thirds; with 1 group, over two-thirds of days had no trades (see zero_volume_share).",
          pd.DataFrame(rows))
tables.append(t6)
pd.concat(tables).to_csv(HERE / "market_quality.csv", index=False)

# Chart: median spread by days to close, one line per event type
fig, ax = plt.subplots(figsize=(9, 5))
x = np.arange(len(DAY_LABELS))
for etype, g in t5.groupby("event_type"):
    g = g.set_index("day_bin").reindex(DAY_LABELS)
    line, = ax.plot(x, g["spread_median"], "-", label=etype)
    few = g["few_tradable"].fillna(True).values
    ax.plot(x[~few], g["spread_median"][~few], "o", color=line.get_color())
    ax.plot(x[few], g["spread_median"][few], "o", mfc="white", color=line.get_color())
ax.set_xticks(x, DAY_LABELS)
ax.invert_xaxis()
ax.set_xlabel("Days to close (closer to the release on the right)")
ax.set_ylabel("Median spread (cents), tradable quotes")
ax.set_title("Bid-ask spread by days to close\n(hollow marker: under 30 tradable daily rows)")
ax.legend()
fig.savefig(OUT / "spread_by_days_to_close.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# Summary, built from the tables
t1, t2 = tables[0].set_index("event_type"), tables[1].set_index("day_bin")
allt = d[d["tradable"]]
print(f"""
SUMMARY
- {len(d)} daily rows; {d['tradable'].mean():.1%} have a tradable two-sided quote.
- Tradable rows overall: median spread {allt['spread'].median() * 100:.1f}c, median all-in cost {allt['cost_1x'].median() * 100:.2f}c
  per contract at 1x fees ({allt['cost_0x'].median() * 100:.2f}c at 0x, {allt['cost_2x'].median() * 100:.2f}c at 2x).
- Cheapest event type by median cost (1x): {t1['cost_1x'].idxmin()} at {t1['cost_1x'].min():.2f}c; most expensive: {t1['cost_1x'].idxmax()} at {t1['cost_1x'].max():.2f}c.
- Median spread by days to close: {', '.join(f'{b} {t2.loc[b, "spread_median"]:.1f}c' for b in DAY_LABELS)}.
- Tradable share by days to close: {', '.join(f'{b} {t2.loc[b, "tradable_share"]:.0%}' for b in DAY_LABELS)}.
- Spread vs volume (Spearman by event type): {', '.join(f'{e} {r:+.2f}' for e, r in t6.groupby('event_type')['spearman'].first().items())}.
Limits: daily closing quotes; depth unknown (assumes one contract fills at the quote); the fee is today's
general formula applied to all years; legacy and new markets close at different times of day.""")
