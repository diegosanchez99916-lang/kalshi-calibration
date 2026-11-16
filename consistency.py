import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "charts"

# Are the strike ladders internally consistent? For "above X" contracts on one event,
# P(X > k) must not increase with k. The design is in METHOD_market_quality.md.
FEE_MULT = 0.07
MAX_SPREAD = 0.20
MIN_STRIKES = 3
EPS = 1e-9      # guards float noise when comparing prices
TOL = 1e-4      # Kalshi stores some strikes with rounding error (4.099999 for 4.1)

def fee(p, k=1):
    return k * FEE_MULT * p * (1 - p)

markets = pd.read_csv(HERE / "markets.csv")
# Fed decision is categorical (hike / cut / hold), not an "above X" ladder, so it is excluded
markets = markets[markets["event_type"] != "Fed decision"].copy()

def ticker_strike(ticker):
    """Number after -T at the end of the ticker. -TN or -T- means negative
    (CPI-22DEC-TN0.3 = -0.3, KXPAYROLLS-25JAN-T-100000 = -100000)."""
    m = re.search(r"-T(N|-)?(\d+\.?\d*)$", ticker)
    return (-1 if m.group(1) else 1) * float(m.group(2)) if m else np.nan

def title_numbers(title):
    """Standalone numbers in the title, commas removed. Skips ones glued to a word (U-3, Q4)."""
    return [float(x.replace(",", "")) for x in re.findall(r"(?<![\w.-])-?\d[\d,]*\.?\d*", title)]

def in_title(strike, title):
    nums = title_numbers(title)
    return any(abs(strike - n * scale) < TOL for n in nums for scale in (1, 1e3, 1e6))

# Step 1: strike for every market, checked against the ticker and the title
markets["from_ticker"] = markets["ticker"].map(ticker_strike)
markets["strike"] = markets["floor_strike"].fillna(markets["from_ticker"])
both = markets["floor_strike"].notna() & markets["from_ticker"].notna()
markets["title_ok"] = [in_title(s, t) for s, t in zip(markets["strike"], markets["title"])]
markets["above"] = (markets["strike_type"] == "greater") | markets["title"].str.contains(
    r"above|more than|higher than|greater than", case=False)
print(f"Ladder markets (all types except Fed decision): {len(markets)}")
print(f"  strike from floor_strike: {markets['floor_strike'].notna().sum()}, "
      f"parsed from the ticker: {(markets['floor_strike'].isna() & markets['from_ticker'].notna()).sum()}, "
      f"unparseable: {markets['strike'].isna().sum()}")
gap = (markets["floor_strike"] - markets["from_ticker"]).abs()
print(f"  floor_strike and ticker disagree (where both exist): {(both & (gap > TOL)).sum()} of {both.sum()}; "
      f"another {(both & (gap > EPS) & (gap <= TOL)).sum()} differ only by rounding error (e.g. 4.099999 for 4.1)")
print(f"  strike not found among the title's numbers: {(~markets['title_ok'] & markets['strike'].notna()).sum()}")
print(f"  confirmed 'above X' by strike_type or title wording: {markets['above'].sum()} of {len(markets)}")
for label, bad in [("Unparseable strike", markets["strike"].isna()),
                   ("Strike not in title", ~markets["title_ok"] & markets["strike"].notna()),
                   ("Not confirmed 'above'", ~markets["above"])]:
    for r in markets[bad].itertuples():
        print(f"    {label}: {r.ticker} | strike {r.strike} | {r.title}")
ok = markets[markets["strike"].notna() & markets["above"]]

# Snapshots at 1, 7 and 30 days before close, with strikes attached
snap = pd.read_csv(HERE / "snapshots.csv").merge(ok[["ticker", "strike"]], on="ticker")
snap["spread"] = snap["yes_ask"] - snap["yes_bid"]
snap["tradable"] = ((snap["yes_bid"] > 0) & (snap["yes_ask"] > 0) & (snap["yes_ask"] < 1)
                    & (snap["spread"] <= MAX_SPREAD))
snap["mid"] = (snap["yes_bid"] + snap["yes_ask"]) / 2

# Steps 2-3: ladders (events with at least MIN_STRIKES strikes at a horizon) and adjacent pairs
pairs, ladders, short, dups = [], [], 0, []
for (etype, days, event), g in snap.groupby(["event_type", "days", "event_ticker"]):
    if g["strike"].duplicated().any():
        dups.append((event, days))
        continue
    if len(g) < MIN_STRIKES:
        short += 1
        continue
    ladders.append({"event_type": etype, "days": days, "event_ticker": event, "strikes": len(g)})
    g = g.sort_values("strike")
    for lo, hi in zip(g.iloc[:-1].itertuples(), g.iloc[1:].itertuples()):
        pairs.append({
            "event_type": etype, "days": days, "event_ticker": event, "date_lo": lo.date, "date_hi": hi.date,
            "strike_lo": lo.strike, "strike_hi": hi.strike,
            "bid_lo": lo.yes_bid, "ask_lo": lo.yes_ask, "bid_hi": hi.yes_bid, "ask_hi": hi.yes_ask,
            "same_date": lo.date == hi.date, "tradable": lo.tradable and hi.tradable,
            # (a) mids, (a2) the price the calibration analysis used, in probability points
            "mid_gap": (hi.mid - lo.mid) * 100, "price_gap": (hi.price - lo.price) * 100,
            # (b) buy YES at the lower strike's ask, sell YES at the higher strike's bid, in cents
            "exec_gross": (hi.yes_bid - lo.yes_ask) * 100,
            "exec_net": (hi.yes_bid - lo.yes_ask - fee(lo.yes_ask) - fee(hi.yes_bid)) * 100})
pairs, ladders = pd.DataFrame(pairs), pd.DataFrame(ladders)
print(f"\nEvent-horizon groups skipped for under {MIN_STRIKES} priced strikes: {short}; "
      f"skipped for duplicate strikes: {len(dups)} {dups[:5]}")
print(f"Ladders: {len(ladders)}; adjacent pairs: {len(pairs)}; "
      f"dropped because the two snapshots are from different days: {(~pairs['same_date']).sum()}")

# Step 4: the tests, on same-date pairs
p = pairs[pairs["same_date"]].copy()
t = p["tradable"]
p["mid_viol"] = t & (p["mid_gap"] > EPS)
p["price_viol"] = p["price_gap"] > EPS
p["exec_viol"] = t & (p["exec_gross"] > EPS)
p["exec_viol_net"] = t & (p["exec_net"] > EPS)

def report(g, lad):
    size = lambda mask, col: (g.loc[mask, col].median(), g.loc[mask, col].max()) if mask.any() else (np.nan, np.nan)
    mid, gross, net = size(g["mid_viol"], "mid_gap"), size(g["exec_viol"], "exec_gross"), size(g["exec_viol_net"], "exec_net")
    n_t = g["tradable"].sum()
    return {"ladders": len(lad), "pairs": len(g), "tradable_pairs": n_t,
            "mid_viol": g["mid_viol"].sum(), "mid_viol_share": g["mid_viol"].sum() / n_t if n_t else np.nan,
            "mid_viol_median": mid[0], "mid_viol_max": mid[1],
            "price_viol": g["price_viol"].sum(), "price_viol_share": g["price_viol"].mean(),
            "exec_viol": g["exec_viol"].sum(), "exec_share": g["exec_viol"].sum() / n_t if n_t else np.nan,
            "exec_median": gross[0], "exec_max": gross[1],
            "exec_after_fees": g["exec_viol_net"].sum(), "net_median": net[0], "net_max": net[1]}

# Step 5: by event type and horizon, with totals
rows = []
for days in [1, 7, 30]:
    for etype in sorted(p["event_type"].unique()) + ["All"]:
        sel = (p["days"] == days) & ((p["event_type"] == etype) | (etype == "All"))
        lsel = (ladders["days"] == days) & ((ladders["event_type"] == etype) | (etype == "All"))
        rows.append({"table": "1 by type and horizon", "event_type": etype, "days": days, **report(p[sel], ladders[lsel])})
rows.append({"table": "1 by type and horizon", "event_type": "All", "days": "all", **report(p, ladders)})
t1 = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print("""
TABLE 1. Ladder consistency by event type and horizon (days before close). Same-date pairs only.
mid_viol: higher strike's mid above the lower strike's (share of tradable pairs; size in probability points).
price_viol: same test on the calibration analysis's price column, all pairs.
exec_viol: higher strike's bid above the lower strike's ask (size in cents); after_fees: still positive
after both legs' taker fees.""")
print(t1.drop(columns="table").round(2).to_string(index=False))

# By event type with horizons pooled, for the chart
t2 = pd.DataFrame([{"table": "2 by type, horizons pooled", "event_type": e,
                    **report(g, ladders[ladders["event_type"] == e])} for e, g in p.groupby("event_type")])
print("\nTABLE 2. By event type, all three horizons pooled")
print(t2.drop(columns="table").round(2).to_string(index=False))

# Step 6: the 10 largest executable violations, ranked by size after fees
top = p[p["exec_viol"]].sort_values("exec_net", ascending=False).head(10)
t3 = top[["event_type", "days", "event_ticker", "date_lo", "strike_lo", "strike_hi", "bid_lo", "ask_lo",
          "bid_hi", "ask_hi", "exec_gross", "exec_net"]].assign(table="3 top executable violations")
print(f"\nTABLE 3. Largest executable violations by size after fees (cents). {int(p['exec_viol'].sum())} found before fees.")
print(t3.drop(columns="table").round(2).to_string(index=False) if len(t3) else "  None.")

pd.concat([t1, t2, t3]).to_csv(HERE / "consistency.csv", index=False)

# Chart: share of tradable adjacent pairs with each kind of violation, by event type
fig, ax = plt.subplots(figsize=(8, 5))
x = np.arange(len(t2))
ax.bar(x - 0.2, t2["mid_viol_share"] * 100, 0.4, label="Mid violation")
ax.bar(x + 0.2, t2["exec_share"] * 100, 0.4, label="Executable violation (before fees)")
ax.set_xticks(x, [f"{e}\n(n={n})" for e, n in zip(t2["event_type"], t2["tradable_pairs"])])
ax.set_ylabel("Share of adjacent strike pairs (%)")
ax.set_title("Strike-ladder violations by event type\n(tradable pairs at 1, 7 and 30 days before close)")
ax.legend()
fig.savefig(OUT / "ladder_violations.png", dpi=150, bbox_inches="tight")
plt.close(fig)

a = t1.iloc[-1]
print(f"""
SUMMARY
- {a['ladders']} ladders, {a['pairs']} same-date adjacent pairs, {a['tradable_pairs']} with both legs tradable.
- Mid violations: {a['mid_viol']} of {a['tradable_pairs']} tradable pairs ({a['mid_viol_share']:.1%}), median {a['mid_viol_median']:.1f} points, max {a['mid_viol_max']:.1f}.
- Analysis-price violations: {a['price_viol']} of {a['pairs']} pairs ({a['price_viol_share']:.1%}).
- Executable violations before fees: {a['exec_viol']} ({a['exec_share']:.1%} of tradable pairs){f", median {a['exec_median']:.1f}c, max {a['exec_max']:.1f}c" if a['exec_viol'] else ""}.
- Executable violations after fees: {a['exec_after_fees']}{f", median {a['net_median']:.1f}c, max {a['net_max']:.1f}c" if a['exec_after_fees'] else ""}.
Limits: these are daily closing quotes, so the two legs' quotes may not have coexisted at one instant;
depth is unknown (one contract per leg assumed); the fee is today's general formula for all years.""")
