import duckdb
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "charts"
OUT.mkdir(exist_ok=True)
con = duckdb.connect(str(HERE / "kalshi.duckdb"), read_only=True)

# Price snapshot for each market at 1, 7 and 30 days before close
snap = con.sql("""
WITH horizons AS (SELECT * FROM (VALUES (1), (7), (30)) AS t(days)),
s AS (
    SELECT m.ticker, m.event_ticker, m.event_type, m.close_time, h.days,
           CASE WHEN m.result THEN 1 ELSE 0 END AS outcome,
           p.date, p.yes_bid, p.yes_ask, p.last_price
    FROM markets m
    CROSS JOIN horizons h
    JOIN prices p
      ON p.ticker = m.ticker
     AND p.date <= m.close_time - to_days(h.days)
     AND p.date >  m.close_time - to_days(h.days + 7)
    QUALIFY ROW_NUMBER() OVER (PARTITION BY m.ticker, h.days ORDER BY p.date DESC) = 1
)
SELECT *,
       CASE WHEN yes_ask > 0 AND yes_ask - yes_bid <= 0.20
            THEN (yes_bid + yes_ask) / 2
            ELSE last_price END AS price
FROM s
""").df()

snap = snap.dropna(subset=["price"])
snap["price"] = snap["price"].clip(0, 1)
snap["sq_err"] = (snap["price"] - snap["outcome"]) ** 2
bins = np.linspace(0, 1, 11)
labels = [f"{i*10}-{i*10+10}%" for i in range(10)]
snap["bucket"] = pd.cut(snap["price"], bins, labels=labels, include_lowest=True)
snap["year"] = pd.to_datetime(snap["close_time"], utc=True).dt.year
snap = snap.sort_values(["event_type", "ticker", "days"]).reset_index(drop=True)
snap.to_csv(HERE / "snapshots.csv", index=False)

def bootstrap_ci(df, n_boot=1000, seed=0):
    """95% interval for a hit rate. Strikes on the same release move together, so resample
    whole releases (event_ticker) with replacement n_boot times, not single contracts."""
    r = df.groupby("event_ticker")["outcome"].agg(["sum", "size"])
    idx = np.random.default_rng(seed).integers(0, len(r), size=(n_boot, len(r)))
    rates = r["sum"].values[idx].sum(axis=1) / r["size"].values[idx].sum(axis=1)
    return np.percentile(rates, [2.5, 97.5])

def calibration(df):
    g = df.groupby("bucket", observed=True)
    c = (g.agg(n=("outcome", "size"), avg_price=("price", "mean"), hit_rate=("outcome", "mean"))
          .reset_index())
    c[["ci_low", "ci_high"]] = [bootstrap_ci(b) for _, b in g]
    # The gap is significant when the average price falls outside the hit rate's 95% interval
    c["significant"] = (c["avg_price"] < c["ci_low"]) | (c["avg_price"] > c["ci_high"])
    return c

def curve(groups, title, file, error_bars=False):
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot([0, 1], [0, 1], "--", color="gray", label="Perfect calibration")
    for name, g in groups:
        c = calibration(g)
        if error_bars:
            yerr = [c["hit_rate"] - c["ci_low"], c["ci_high"] - c["hit_rate"]]
            ax.errorbar(c["avg_price"], c["hit_rate"], yerr=yerr, fmt="o-", capsize=3,
                        elinewidth=1, label=name)
        else:
            ax.plot(c["avg_price"], c["hit_rate"], "o-", label=name)
    ax.set_xlabel("Market price (implied probability)")
    ax.set_ylabel("How often it actually happened")
    ax.set_title(title)
    ax.legend()
    fig.savefig(OUT / file, dpi=150, bbox_inches="tight")
    plt.close(fig)

print("Snapshots per horizon:", snap.groupby("days").size().to_dict())

# Chart 1: calibration curve at each horizon
curve([(f"{d} day(s) before close", g) for d, g in snap.groupby("days")],
      "Kalshi economics markets: calibration by time before close\n(bars: 95% interval, resampling whole releases)",
      "calibration_by_horizon.png", error_bars=True)

# Chart 2: calibration by event type, 1 day before close
one = snap[snap["days"] == 1]
curve(one.groupby("event_type"), "Calibration by event type (1 day before close)",
      "calibration_by_event_type.png")

# Chart 3: Brier score by event type and horizon
brier = snap.pivot_table(index="event_type", columns="days", values="sq_err", aggfunc="mean")
ax = brier.plot(kind="bar", figsize=(8, 5))
ax.set_ylabel("Brier score (lower is better)")
ax.set_title("Accuracy by event type and time before close")
ax.legend(title="Days before close")
ax.figure.savefig(OUT / "brier_by_event_type.png", dpi=150, bbox_inches="tight")
plt.close(ax.figure)

# Chart 4: where prices sit 1 day out
fig, ax = plt.subplots(figsize=(8, 4))
ax.hist(one["price"], bins=20)
ax.set_xlabel("Price 1 day before close")
ax.set_ylabel("Number of contracts")
ax.set_title("Distribution of prices 1 day before close")
fig.savefig(OUT / "price_distribution.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# Printed results
c1 = calibration(one)
print("\nCalibration, 1 day before close:")
print(c1.round(3).to_string(index=False))

print("\nBuckets where the price-vs-hit-rate gap is statistically significant (95% release-level bootstrap):")
for d, g in snap.groupby("days"):
    sig = calibration(g).query("significant")
    print(f"  {d} day(s) before close: " + (", ".join(
        f"{r.bucket} (price {r.avg_price:.0%}, happened {r.hit_rate:.0%}, "
        f"CI {r.ci_low:.0%}-{r.ci_high:.0%}, n={r.n})" for r in sig.itertuples()) or "none"))

print("\nBrier score by event type (0 = perfect, 0.25 = coin flip):")
print(brier.round(3))

overall = snap.groupby("days")["sq_err"].mean()
base = one["outcome"].mean()
ece = (c1["n"] * (c1["avg_price"] - c1["hit_rate"]).abs()).sum() / c1["n"].sum()
print("\nOverall Brier by horizon:", overall.round(3).to_dict())
print(f"Baseline Brier (always guess the {base:.0%} base rate): {base * (1 - base):.3f}")
print(f"\nMAIN FINDING: 1 day before release, across {len(one)} contracts, Kalshi prices "
      f"had a Brier score of {overall[1]:.3f} and were off from real outcome frequencies "
      f"by {ece*100:.1f} percentage points on average.")
# Calibration over time, 1 day before close. Two things shift over the years besides skill:
# - the event-type mix (Fed and Jobs start in 2023, and Fed is far easier), so trends are
#   measured within each event type;
# - how many contracts are close calls. A perfectly priced 50% contract still scores 0.25, so
#   "excess" is Brier minus the p(1-p) a perfectly calibrated price would expect. It averages
#   0 for a calibrated market however hard the questions are; positive means prices were worse
#   than their own confidence implied.
one = one.assign(code=one["bucket"].cat.codes, gap=one["outcome"] - one["price"],
                 close_call=one["price"].between(0.1, 0.9),
                 excess=one["sq_err"] - one["price"] * (1 - one["price"]))
for col in ["sq_err", "excess"]:
    one["adj_" + col] = one[col] - one.groupby("event_type")[col].transform("mean")

def release_bootstrap(df, n_boot=1000, seed=0):
    """Yearly metrics with 95% intervals from resampling whole releases."""
    r = df.groupby("event_ticker")
    n = r.size().values
    sums = {c: r[c].sum().values for c in ["sq_err", "excess", "adj_sq_err", "adj_excess"]}
    gaps = df.pivot_table(index="event_ticker", columns="code", values="gap", aggfunc="sum",
                          fill_value=0).values
    idx = np.random.default_rng(seed).integers(0, len(n), size=(n_boot, len(n)))
    out = {"contracts": n.sum(), "releases": len(n), "close_calls": df["close_call"].mean()}
    for name, c in [("brier", "sq_err"), ("excess", "excess"), ("adj_brier", "adj_sq_err"),
                    ("adj_excess", "adj_excess")]:
        out[name] = sums[c].sum() / n.sum()
        out[name + "_lo"], out[name + "_hi"] = np.percentile(sums[c][idx].sum(1) / n[idx].sum(1), [2.5, 97.5])
    # Calibration gap = sum over buckets of |hits - prices| per contract, in points. Noise pushes
    # it up, so resampled gaps run high; flip the interval around the estimate (basic bootstrap).
    out["gap"] = np.abs(gaps.sum(0)).sum() / n.sum() * 100
    boot = np.abs(gaps[idx].sum(1)).sum(1) / n[idx].sum(1) * 100
    lo, hi = np.percentile(boot, [2.5, 97.5])
    out["gap_lo"], out["gap_hi"] = max(2 * out["gap"] - hi, 0), 2 * out["gap"] - lo
    return out

def within_type_trend(df, col, n_boot=1000, seed=0):
    """Change in col per year with each event type's average level removed (a fixed-effects
    slope), with a 95% interval from resampling releases."""
    r = df.groupby("event_ticker").agg(t=("event_type", "first"), yr=("year", "first"),
                                       n=(col, "size"), s=(col, "sum"))
    idx = np.random.default_rng(seed).integers(0, len(r), size=(n_boot, len(r)))
    # w[0] is the real data, w[1:] counts how often each release was drawn in each resample
    w = np.vstack([np.ones(len(r)), [np.bincount(i, minlength=len(r)) for i in idx]])
    num = den = 0
    for t in r["t"].unique():
        m = (r["t"] == t).values
        wt, n, s, yr = w[:, m], r["n"].values[m], r["s"].values[m], r["yr"].values[m]
        xbar = (wt * n * yr).sum(1) / (wt * n).sum(1)
        ybar = (wt * s).sum(1) / (wt * n).sum(1)
        dx = yr - xbar[:, None]
        num = num + (wt * dx * (s - n * ybar[:, None])).sum(1)
        den = den + (wt * n * dx ** 2).sum(1)
    b = num / den
    lo, hi = np.percentile(b[1:], [2.5, 97.5])
    return {"slope": b[0], "slope_lo": lo, "slope_hi": hi, "significant": lo > 0 or hi < 0}

yearly = pd.DataFrame(
    [{"year": y, "event_type": "All", **release_bootstrap(g)} for y, g in one.groupby("year")] +
    [{"year": y, "event_type": t, **release_bootstrap(g)} for (y, t), g in one.groupby(["year", "event_type"])])
yearly.to_csv(HERE / "yearly.csv", index=False)
trend = pd.DataFrame([{"metric": m, "event_type": t, **within_type_trend(g, col)}
                      for m, col in [("brier", "sq_err"), ("excess", "excess")]
                      for t, g in [("All", one)] + list(one.groupby("event_type"))])
trend.to_csv(HERE / "yearly_trend.csv", index=False)

# Chart 5: Brier and difficulty-adjusted pricing error by year, within each event type
years = sorted(one["year"].unique())
ticks = [f"{y}\n(Jul-Dec)" if y == 2021 else str(y) for y in years]
fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharex=True)
for ax, m, title in [(axes[0], "brier", "Brier score (lower is better)"),
                     (axes[1], "excess", "Pricing error after allowing for difficulty\n(0 = prices as good as they claimed)")]:
    # Skip cells with under 3 releases: too few to resample into a meaningful interval
    cells = yearly[(yearly["event_type"] != "All") & (yearly["releases"] >= 3)]
    for k, (t, g) in enumerate(cells.groupby("event_type")):
        ax.errorbar(g["year"] + (k - 1.5) * 0.08, g[m], capsize=3, elinewidth=1, fmt="o-", label=t,
                    yerr=[g[m] - g[m + "_lo"], g[m + "_hi"] - g[m]])
    ax.set_title(title)
    ax.set_xticks(years, ticks)
axes[1].axhline(0, color="gray", ls="--", lw=1)
axes[0].set_ylabel("1 day before close")
axes[0].legend()
fig.suptitle("Is Kalshi getting more accurate? (bars: 95% interval, resampling whole releases)", y=1.04)
fig.savefig(OUT / "brier_over_time.png", dpi=150, bbox_inches="tight")
plt.close(fig)

fmt = lambda r, m, f: f"{r[m]:{f}} [{r[m + '_lo']:{f}}, {r[m + '_hi']:{f}}]"
show = pd.DataFrame({"year": yearly["year"], "type": yearly["event_type"],
                     "contracts": yearly["contracts"], "releases": yearly["releases"],
                     "close_calls": yearly["close_calls"].map("{:.0%}".format),
                     "brier": yearly.apply(fmt, axis=1, args=("brier", ".3f")),
                     "excess": yearly.apply(fmt, axis=1, args=("excess", "+.3f")),
                     "gap_pts": yearly.apply(fmt, axis=1, args=("gap", ".1f"))})
print("\nCalibration over time, 1 day before close (95% intervals resample whole releases).")
print("excess = Brier minus what perfectly calibrated prices would score; 0 = prices as good as claimed.")
print("\nAll types, adjusted for event-type mix (each contract vs. its type's all-years average):")
adj = show[show["type"] == "All"].assign(
    adj_brier=yearly.apply(fmt, axis=1, args=("adj_brier", "+.3f")),
    adj_excess=yearly.apply(fmt, axis=1, args=("adj_excess", "+.3f")))
print(adj.drop(columns="type").to_string(index=False))
for t, g in show[show["type"] != "All"].groupby("type"):
    print(f"\n{t}:")
    print(g.drop(columns="type").to_string(index=False))
print("\nChange per year, within event type (negative = improving):")
for r in trend.itertuples():
    print(f"  {r.metric:6} {r.event_type:4} {r.slope:+.4f} [{r.slope_lo:+.4f}, {r.slope_hi:+.4f}]  "
          f"{'significant' if r.significant else 'within noise'}")
