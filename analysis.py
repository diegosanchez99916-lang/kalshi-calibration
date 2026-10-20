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
    SELECT m.ticker, m.event_type, h.days,
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
snap.to_csv(HERE / "snapshots.csv", index=False)

def calibration(df):
    return (df.groupby("bucket", observed=True)
              .agg(n=("outcome", "size"), avg_price=("price", "mean"), hit_rate=("outcome", "mean"))
              .reset_index())

def curve(groups, title, file):
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot([0, 1], [0, 1], "--", color="gray", label="Perfect calibration")
    for name, g in groups:
        c = calibration(g)
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
      "Kalshi economics markets: calibration by time before close", "calibration_by_horizon.png")

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