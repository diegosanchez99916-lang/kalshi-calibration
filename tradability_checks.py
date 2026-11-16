import numpy as np
import pandas as pd
import statsmodels.api as sm
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "charts"

# Robustness checks for tradability.py's main result (sell YES at the bid, 70-80% bucket,
# 1 day before close). Every variant below was fixed before looking at its result.
# The setup block is copied from tradability.py so the numbers are comparable.
FEE_MULT = 0.07
MAX_SPREAD = 0.20
MIN_N = 20

def fee(p, k=1):
    return k * FEE_MULT * p * (1 - p)

snap = pd.read_csv(HERE / "snapshots.csv")
one = snap[snap["days"] == 1].copy()
one["spread"] = one["yes_ask"] - one["yes_bid"]
drop = (one["yes_bid"].isna() | one["yes_ask"].isna() | (one["yes_bid"] <= 0)
        | (one["yes_ask"] <= 0) | (one["yes_ask"] >= 1) | (one["spread"] > MAX_SPREAD))
q = one[~drop].copy()
q["sell_1x"] = q["yes_bid"] - q["outcome"] - fee(q["yes_bid"])

def bootstrap_mean(df, col, n_boot=1000, seed=0):
    """95% interval for a mean. Contracts on the same release move together, so resample
    whole releases with replacement n_boot times, not single contracts (as in analysis.py)."""
    r = df.groupby("release")[col].agg(["sum", "size"])
    idx = np.random.default_rng(seed).integers(0, len(r), size=(n_boot, len(r)))
    means = r["sum"].values[idx].sum(axis=1) / r["size"].values[idx].sum(axis=1)
    return np.percentile(means, [2.5, 97.5])

def cell(df, col="sell_1x"):
    """n, mean P&L and its interval, in cents per contract."""
    if len(df) == 0:
        return {"n": 0, "releases": 0, "pnl": np.nan, "lo": np.nan, "hi": np.nan}
    lo, hi = bootstrap_mean(df, col)
    return {"n": len(df), "releases": df["release"].nunique(),
            "pnl": df[col].mean() * 100, "lo": lo * 100, "hi": hi * 100}

pd.set_option("display.width", 200)
b70 = q[q["bucket"] == "70-80%"].copy()
base = cell(b70)
print(f"Baseline (must match tradability.py): n={base['n']}, releases={base['releases']}, "
      f"{base['pnl']:+.2f}c ({base['lo']:+.2f}c to {base['hi']:+.2f}c)")
tables = []

# CHECK 1: quote timing and look-ahead
print("\nCHECK 1. Quote timing and look-ahead")
print("(a) Lines in pull_all.py that store each candle (all three prices are the candle 'close'):")
for line in (HERE / "pull_all.py").read_text().splitlines():
    if '"close")' in line or "end_period_ts" in line:
        print("   ", line.strip())
prices = pd.read_csv(HERE / "prices.csv")
prices["ts"] = pd.to_datetime(prices["date"], utc=True, format="ISO8601")
hours = prices["ts"].dt.strftime("%H:%M UTC").value_counts(normalize=True)
print("(b) end_period_ts is the end of the daily candle. Clock time of all candle timestamps:")
print("   ", ", ".join(f"{h} {s:.1%}" for h, s in hours.head(4).items()),
      "(04:00 or 05:00 UTC = midnight US Eastern)")

# The snapshot's date is the candle's end timestamp; close_time is when the market closed
b70["ts"] = pd.to_datetime(b70["date"], utc=True, format="ISO8601")
b70["gap_h"] = (pd.to_datetime(b70["close_time"], utc=True, format="ISO8601") - b70["ts"]).dt.total_seconds() / 3600
g = b70["gap_h"]
print(f"(c) Hours from the snapshot candle's end to the market's close_time, 70-80% sample (n={len(b70)}):")
print(f"    min {g.min():.1f}, median {g.median():.1f}, max {g.max():.1f}")
print(f"    under 24h (LOOK-AHEAD if any): {(g < 24).sum()} | 24-48h: {((g >= 24) & (g < 48)).sum()} | "
      f"48-96h: {((g >= 48) & (g < 96)).sum()} | 96h or more: {(g >= 96).sum()}")
print(f"    bid below ask in every sample row: {(b70['yes_bid'] < b70['yes_ask']).all()}")
print("""    Verified from the data: the stored bid, ask and last price are each candle's closing values;
    the bid and ask come from the same candle row, so both are the quote at the candle's end;
    every sample quote is at least 24 hours older than the market's close.
    Not verifiable from daily data: that the closing bid and ask stood at the exact same instant
    or for how long; how much size they held; and that close_time is never later than the data
    release itself (if a market closed after its release, the gap to the release would be shorter).""")
tables.append(pd.DataFrame([{"check": "1 timing", "variant": "hours from snapshot to close", "n": len(b70),
                             "min": g.min(), "median": g.median(), "max": g.max(), "under_24h": (g < 24).sum()}]))

# CHECK 2: volume filter. Join daily candle volume on ticker and candle timestamp.
print("\nCHECK 2. Volume filter (sell YES at the bid, 70-80%, 1x fees)")
prices = prices.sort_values(["ticker", "ts"])
prices["cum_volume"] = prices.groupby("ticker")["volume"].cumsum()
v = b70.merge(prices[["ticker", "ts", "volume", "cum_volume"]], on=["ticker", "ts"], how="left")
print(f"Rows matched to a prices.csv candle: {v['volume'].notna().sum()} of {len(v)}")
if v["volume"].isna().any():
    print("  unmatched tickers:", v.loc[v["volume"].isna(), "ticker"].tolist())
print(f"Median volume on the snapshot day: {v['volume'].median():.0f} contracts. "
      f"Median cumulative volume through that day: {v['cum_volume'].median():.0f}.")
subsets = [("(a) all tradable rows", v),
           ("(b) volume > 0 on the snapshot day", v[v["volume"] > 0]),
           ("(c) cumulative volume >= 100", v[v["cum_volume"] >= 100])]
t2 = pd.DataFrame([{"check": "2 volume", "variant": name, **cell(d)} for name, d in subsets])
t2["too_small"] = t2["n"] < MIN_N
print(t2.drop(columns="check").round(2).to_string(index=False))
tables.append(t2)

# CHECK 3a: sliding 10-point windows every 2.5 points. Same edges as the buckets:
# start < price <= start + 10 (the first window also includes 0).
print("\nCHECK 3a. Sliding 10-point price windows, sell YES at the bid, 1x fees, tradable rows")
cents = (q["price"] * 100).round(4)
rows = []
for start in np.arange(0, 90.1, 2.5):
    d = q[(cents > start) & (cents <= start + 10)] if start > 0 else q[cents <= 10]
    rows.append({"check": "3a windows", "variant": f"{start:g}-{start + 10:g}", "center": start + 5, **cell(d)})
t3 = pd.DataFrame(rows)
t3["too_small"] = t3["n"] < MIN_N
t3["above_zero"] = (t3["lo"] > 0) & ~t3["too_small"]
t3["below_zero"] = (t3["hi"] < 0) & ~t3["too_small"]
print(t3.drop(columns="check").round(2).to_string(index=False))
tables.append(t3)

# CHECK 3c: how many windows, and how many clear zero
ok = t3[~t3["too_small"]]
print(f"\nCHECK 3c. Windows tested: {len(t3)} ({len(ok)} with at least {MIN_N} contracts). "
      f"Whole interval above zero: {ok['above_zero'].sum()} "
      f"({', '.join(ok.loc[ok['above_zero'], 'variant']) or 'none'}). Below zero: {ok['below_zero'].sum()}.")
print(f"By chance about {0.025 * len(ok):.1f} of {len(ok)} independent tests would land above zero. These windows "
      f"overlap\n(each contract sits in up to 4), so they act like roughly {len(ok) / 4:.0f} independent tests, "
      f"or about {0.025 * len(ok) / 4:.1f} by chance.")

# CHECK 3b: calibration regression on all tradable rows, with statsmodels Logit.
# outcome ~ log-odds of the price. Perfect calibration is intercept 0, slope 1; a slope below 1
# means prices are too extreme (high prices too high, low prices too low).
print("\nCHECK 3b. Calibration regression (statsmodels Logit): outcome ~ log-odds of price, all tradable rows")
q["logit"] = np.log(q["price"] / (1 - q["price"]))
X, y = sm.add_constant(q["logit"]).values, q["outcome"].values
fit = sm.Logit(y, X).fit(disp=0).params
# Release-level bootstrap: refit on resampled releases
groups = [np.flatnonzero(q["release"].values == r) for r in q["release"].unique()]
rng = np.random.default_rng(0)
boots = []
for _ in range(1000):
    i = np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))])
    boots.append(sm.Logit(y[i], X[i]).fit(disp=0).params)
boots = np.array(boots)
at75 = lambda p: 1 / (1 + np.exp(-(p[..., 0] + p[..., 1] * np.log(0.75 / 0.25))))
est = {"intercept": (fit[0], boots[:, 0]), "slope": (fit[1], boots[:, 1]),
       "fitted chance of YES at a 75c price": (at75(fit), at75(boots))}
t4 = pd.DataFrame([{"check": "3b regression", "variant": k, "n": len(q), "releases": len(groups),
                    "estimate": e, "lo": np.percentile(b, 2.5), "hi": np.percentile(b, 97.5)}
                   for k, (e, b) in est.items()])
print(t4.drop(columns="check").round(3).to_string(index=False))
tables.append(t4)
slope = t4.set_index("variant").loc["slope"]
p75 = t4.set_index("variant").loc["fitted chance of YES at a 75c price"]
print(f"""What the slope says: it measures one overall tilt across every price. The slope's interval
{'includes' if slope['lo'] <= 1 <= slope['hi'] else 'excludes'} 1, so there is {'no' if slope['lo'] <= 1 <= slope['hi'] else 'some'} evidence that prices as a whole are too extreme.
What it does not say: it cannot confirm or rule out a dip at one price range. The smooth fit puts
the chance of YES at a 75c price at {p75['estimate']:.1%} ({p75['lo']:.1%} to {p75['hi']:.1%}); the 70-80% bucket actually
happened {b70['outcome'].mean():.1%} of the time. A gap between those two is a local bump the overall tilt does not explain.""")

# EXTRA: fee rounding. Kalshi rounds an order's total fee up to the next cent.
print("\nEXTRA. Fee rounding, sell YES at the bid, 70-80%")
def rounded_fee(p, contracts):
    return np.ceil((contracts * fee(p) * 100).round(9)) / 100 / contracts
rows = []
for name, f in [("unrounded formula (tradability.py)", fee(b70["yes_bid"])),
                ("1-contract orders, fee rounded up", rounded_fee(b70["yes_bid"], 1)),
                ("100-contract orders, fee rounded up", rounded_fee(b70["yes_bid"], 100))]:
    d = b70.assign(pnl=b70["yes_bid"] - b70["outcome"] - f)
    rows.append({"check": "extra rounding", "variant": name, "fee": f.mean() * 100, **cell(d, "pnl")})
t5 = pd.DataFrame(rows)
print(t5.drop(columns="check").round(2).to_string(index=False))
print("The 100-contract case is the realistic one for anyone trading more than a few contracts, since the\n"
      "round-up is spread over the order. But this test cannot show that 100 contracts would fill at the bid.")
tables.append(t5)

pd.concat(tables).to_csv(HERE / "tradability_checks.csv", index=False)

# Chart: mean net P&L by window center
fig, ax = plt.subplots(figsize=(9, 5))
for small, fmt, label in [(False, "o", f"n >= {MIN_N}"), (True, "x", f"n < {MIN_N} (too small)")]:
    d = t3[t3["too_small"] == small]
    if len(d):
        ax.errorbar(d["center"], d["pnl"], yerr=[d["pnl"] - d["lo"], d["hi"] - d["pnl"]], fmt=fmt,
                    capsize=3, elinewidth=1, label=label)
ax.axhline(0, color="gray", ls="--", lw=1)
ax.set_xlabel("Center of 10-point price window (cents), 1 day before close")
ax.set_ylabel("Mean net P&L per contract (cents)")
ax.set_title("Sell YES at the bid across sliding price windows, net of 1x fees\n"
             "(bars: 95% interval, resampling whole releases)")
ax.legend()
fig.savefig(OUT / "tradability_windows.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# Summary, built from the tables
s2 = t2.set_index("variant")
line = lambda r: f"{r['pnl']:+.1f}c ({r['lo']:+.1f}c to {r['hi']:+.1f}c, n={r['n']})"
near = t3[t3["center"].between(70, 80)]
print(f"""
SUMMARY
Baseline: sell YES at the bid, 70-80%, 1x fees: {line(base)}.
1. Timing: quotes are candle closes, {g.min():.0f} to {g.max():.0f} hours before close (median {g.median():.0f}); {(g < 24).sum()} rows under 24h.
2. Volume: traded that day {line(s2.iloc[1])}; cumulative volume >= 100 {line(s2.iloc[2])}.
3. Windows: {ok['above_zero'].sum()} of {len(ok)} windows clear zero. Windows centered 70 to 80:
{chr(10).join(f"   {r.variant}: {r.pnl:+.1f}c ({r.lo:+.1f}c to {r.hi:+.1f}c, n={r.n})" for r in near.itertuples())}
   Calibration slope {slope['estimate']:.2f} ({slope['lo']:.2f} to {slope['hi']:.2f}); 1 = calibrated.
Extra. Fee rounding: 1-contract orders {line(t5.iloc[1])}; 100-contract orders {line(t5.iloc[2])}.""")
