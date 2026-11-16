import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "charts"

# Kalshi taker fee per contract = FEE_MULT * P * (1 - P), no settlement fee. 0.07 is the general
# schedule (confirmed in Kalshi's Oct 14, 2026 CFTC rebate filing). The schedule has changed over
# time, so applying today's formula to 2021-2026 is an approximation; see the 0x and 2x columns.
FEE_MULT = 0.07
FEE_LEVELS = [0, 1, 2]
MAX_SPREAD = 0.20
MIN_N = 20      # cells under this many contracts are too small to trust
SIDES = {"sell": "Sell YES at bid", "buy": "Buy YES at ask"}

def fee(p, k=1):
    return k * FEE_MULT * p * (1 - p)

# Price 1 day before close only. Everything used to pick a trade (bucket, event type, quote)
# is known at the snapshot; the outcome is only used to settle the trade afterwards.
snap = pd.read_csv(HERE / "snapshots.csv")
one = snap[snap["days"] == 1].copy()
one["spread"] = one["yes_ask"] - one["yes_bid"]

# Keep rows with a real two-sided quote. A bid of 0 or an ask of 1.00 means nobody is quoting
# that side, so there is nothing to trade against.
reasons = {
    "missing bid or ask": one["yes_bid"].isna() | one["yes_ask"].isna(),
    "no bid (yes_bid = 0)": one["yes_bid"] <= 0,
    "no ask (yes_ask <= 0 or = 1.00)": (one["yes_ask"] <= 0) | (one["yes_ask"] >= 1),
    f"spread over {MAX_SPREAD:.2f}": one["spread"] > MAX_SPREAD,
}
drop = pd.concat(reasons, axis=1).any(axis=1)
print(f"Rows 1 day before close: {len(one)}")
for why, mask in reasons.items():
    print(f"  dropped, {why}: {mask.sum()}")
print(f"  dropped in total (a row can fail more than one test): {drop.sum()}")
q = one[~drop].copy()
print(f"  kept with a two-sided quote: {len(q)} contracts from {q['release'].nunique()} releases")
print("\nKept per price bucket (all rows -> tradable rows):")
print(pd.DataFrame({"all": one.groupby("bucket").size(), "tradable": q.groupby("bucket").size()}).T.to_string())

# P&L per contract at settlement, in dollars, at each fee level.
# Sell YES at the bid: collect the bid, pay 1 if it happens. Buy YES at the ask: the reverse.
for k in FEE_LEVELS:
    q[f"sell_{k}x"] = q["yes_bid"] - q["outcome"] - fee(q["yes_bid"], k)
    q[f"buy_{k}x"] = q["outcome"] - q["yes_ask"] - fee(q["yes_ask"], k)
q["sell_fee"], q["buy_fee"] = fee(q["yes_bid"]), fee(q["yes_ask"])

def bootstrap_mean(df, col, n_boot=1000, seed=0):
    """95% interval for a mean. Contracts on the same release move together, so resample
    whole releases with replacement n_boot times, not single contracts (as in analysis.py)."""
    r = df.groupby("release")[col].agg(["sum", "size"])
    idx = np.random.default_rng(seed).integers(0, len(r), size=(n_boot, len(r)))
    means = r["sum"].values[idx].sum(axis=1) / r["size"].values[idx].sum(axis=1)
    return np.percentile(means, [2.5, 97.5])

def cell(df, side, k=1):
    """n, mean P&L and its interval for one side at one fee level, in cents per contract."""
    if len(df) == 0:
        return {"n": 0, "releases": 0, "pnl": np.nan, "lo": np.nan, "hi": np.nan}
    lo, hi = bootstrap_mean(df, f"{side}_{k}x")
    return {"n": len(df), "releases": df["release"].nunique(),
            "pnl": df[f"{side}_{k}x"].mean() * 100, "lo": lo * 100, "hi": hi * 100}

buckets = sorted(q["bucket"].unique(), key=lambda b: int(b.split("-")[0]))

# Table 1: every bucket and both sides, at 1x fees
rows = []
for b in buckets:
    g = q[q["bucket"] == b]
    for s in SIDES:
        rows.append({"bucket": b, "side": SIDES[s], "spread": g["spread"].mean() * 100,
                     "fee": g[f"{s}_fee"].mean() * 100, **cell(g, s)})
t1 = pd.DataFrame(rows)
t1["above_zero"] = t1["lo"] > 0
pd.set_option("display.width", 200)
print(f"\nTABLE 1. Net P&L per contract in cents at 1x fees, by bucket and side ({len(t1)} cells tested).")
print("Interval = 95% release-level bootstrap. above_zero = whole interval above 0.")
print(t1.round(2).to_string(index=False))
print(f"Cells with the whole interval above zero: {t1['above_zero'].sum()} of {len(t1)}. "
      f"With {len(t1)} cells, about {0.025 * len(t1):.1f} would land there by chance.")

# Table 2: pick the rule on one period, test it on the other. The pick is the bucket and side
# with the best mean net P&L (1x fees) among cells with at least MIN_N contracts in the
# selection period. Nothing is tuned after seeing the test period.
def pick(df):
    c = pd.DataFrame([{"bucket": b, "side": s, "n": (df["bucket"] == b).sum(),
                       "pnl": df.loc[df["bucket"] == b, f"{s}_1x"].mean() * 100}
                      for b in buckets for s in SIDES]).dropna()
    best_any = c.loc[c["pnl"].idxmax()]
    best = c[c["n"] >= MIN_N].loc[lambda x: x["pnl"].idxmax()]
    return best, best_any

early, late = q[q["year"] <= 2024], q[q["year"] >= 2025]
rows = []
for name_a, a, name_b, b in [("2021-2024", early, "2025-2026", late), ("2025-2026", late, "2021-2024", early)]:
    best, best_any = pick(a)
    if (best_any["bucket"], best_any["side"]) != (best["bucket"], best["side"]):
        print(f"\nNote: on {name_a} the best cell of any size was {best_any['bucket']} {best_any['side']} "
              f"(n={best_any['n']}, {best_any['pnl']:+.2f}c), skipped for having under {MIN_N} contracts.")
    rule = lambda df: df[df["bucket"] == best["bucket"]]
    for period, role, df in [(name_a, "picked on", a), (name_b, "tested on", b)]:
        rows.append({"rule": f"{best['bucket']} {SIDES[best['side']]}", "role": role, "period": period,
                     **cell(rule(df), best["side"])})
t2 = pd.DataFrame(rows)
t2["verdict"] = np.where(t2["n"] < MIN_N, "too few contracts",
                np.where(t2["lo"] > 0, "edge (interval above 0)",
                np.where(t2["hi"] < 0, "loses (interval below 0)", "no edge (interval includes 0)")))
print("\nTABLE 2. Out-of-sample test: rule picked on one period, applied unchanged to the other.")
print("Net P&L per contract in cents at 1x fees. The 'picked on' rows are in-sample and biased up.")
print(t2.round(2).to_string(index=False))

# Table 3: the 70-80% sell-YES rule (the README's main miss) at each fee level, by event type
b70 = q[q["bucket"] == "70-80%"]
groups = [("All", b70)] + [(t, g) for t, g in b70.groupby("event_type")]
t3 = pd.DataFrame([{"event_type": t, "fees": f"{k}x", **cell(g, "sell", k)} for t, g in groups for k in FEE_LEVELS])
t3["too_small"] = t3["n"] < MIN_N
print(f"\nTABLE 3. Sell YES at the bid in the 70-80% bucket, cents per contract. too_small = under {MIN_N} contracts.")
print(t3.round(2).to_string(index=False))
hit = b70["outcome"].mean()
print(f"\n70-80% bucket, tradable rows: n={len(b70)} (README has {int((one['bucket'] == '70-80%').sum())}; "
      f"{int((one['bucket'] == '70-80%').sum()) - len(b70)} dropped for the quote filter). "
      f"Mid {b70['price'].mean():.3f}, bid {b70['yes_bid'].mean():.3f}, ask {b70['yes_ask'].mean():.3f}, "
      f"happened {hit:.3f}, fee at 1x {b70['sell_fee'].mean() * 100:.2f}c.")

pd.concat([t1.assign(table="1 by bucket and side"), t2.assign(table="2 out of sample"),
           t3.assign(table="3 sell YES 70-80%")]).to_csv(HERE / "tradability.csv", index=False)

# Chart: mean net P&L by bucket, sell vs buy, at 1x fees
fig, ax = plt.subplots(figsize=(9, 5))
x = np.arange(len(buckets))
for off, (s, label) in zip([-0.12, 0.12], SIDES.items()):
    g = t1[t1["side"] == label]
    ax.errorbar(x + off, g["pnl"], yerr=[g["pnl"] - g["lo"], g["hi"] - g["pnl"]], fmt="o", capsize=3,
                elinewidth=1, label=label)
ax.axhline(0, color="gray", ls="--", lw=1)
ax.set_xticks(x, buckets)
ax.set_xlabel("Price bucket 1 day before close")
ax.set_ylabel("Mean net P&L per contract (cents)")
ax.set_title("Can you trade the miscalibration? Net of spread and 1x fees\n"
             "(bars: 95% interval, resampling whole releases)")
ax.legend()
fig.savefig(OUT / "tradability_by_bucket.png", dpi=150, bbox_inches="tight")
plt.close(fig)

a = t3[(t3["event_type"] == "All")].set_index("fees")
oos = "\n".join(f"- Picked on the other period, tested on {r.period}: {r.rule}, {r.pnl:+.1f}c per contract "
                f"({r.lo:+.1f}c to {r.hi:+.1f}c, n={r.n}): {r.verdict}."
                for r in t2[t2["role"] == "tested on"].itertuples())
print(f"""
SUMMARY
Selling YES at the bid on every 70-80% contract, 1 day before release, made {a.loc['1x', 'pnl']:+.1f}c per
contract after 1x fees (95% interval {a.loc['1x', 'lo']:+.1f}c to {a.loc['1x', 'hi']:+.1f}c, n={a.loc['1x', 'n']});
{a.loc['0x', 'pnl']:+.1f}c with no fees and {a.loc['2x', 'pnl']:+.1f}c at 2x fees. That is in-sample.
Out of sample (Table 2):
{oos}

Limits of this test:
- Daily data: the quote is the day's closing bid and ask, not a price you could act on at a chosen time.
- No depth: assumes 1 contract at a time fills at the quoted price. Real size would move the price.
- Fees: fee = {FEE_MULT} * P * (1 - P) per contract with no settlement fee is today's general taker
  schedule. Kalshi's fees have changed since 2021, so this is an approximation (hence 0x and 2x).
  Kalshi rounds each order's fee up to the next cent, which costs more on 1-contract orders.
- In-sample selection: Tables 1 and 3 look at buckets chosen after seeing the outcomes.
- Multiple cells: {len(t1)} bucket-side cells were tested, so about {0.025 * len(t1):.1f} would look
  profitable by chance.""")
