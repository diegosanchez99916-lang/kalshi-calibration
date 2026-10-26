import time
import requests
import pandas as pd
from pathlib import Path

BASE = "https://external-api.kalshi.com/trade-api/v2"
HERE = Path(__file__).parent
SERIES = {"KXCPI": "CPI", "KXPAYROLLS": "Jobs", "KXFEDDECISION": "Fed decision", "KXGDP": "GDP",
          "KXFED": "Fed rate", "KXU3": "Unemployment", "KXCPIYOY": "CPI YoY"}
# The analysis scores each contract by its result, so strikes are kept for reference only. Legacy
# markets have no strike type. Anything new (e.g. "between", which also uses cap_strike) is flagged.
KNOWN_STRIKES = {"greater", "less", "between", "custom"}
throttled = 0

def get(url, params):
    global throttled
    for attempt in range(5):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 429:
                throttled += 1
                time.sleep(2 ** attempt)
                continue
            return r
        except requests.RequestException:
            time.sleep(2 ** attempt)
    return None

def get_all(path, params):
    out, cursor = [], ""
    while True:
        r = get(BASE + path, {**params, "cursor": cursor})
        if r is None:
            raise RuntimeError(f"Request kept failing: {path}")
        r.raise_for_status()
        data = r.json()
        out += data["markets"]
        cursor = data.get("cursor")
        if not cursor:
            return out

def val(d, key):
    if not d:
        return None
    return d.get(key + "_dollars", d.get(key))

def candles(series, ticker, start, end, old):
    params = {"start_ts": start, "end_ts": end, "period_interval": 1440}
    live = f"{BASE}/series/{series}/markets/{ticker}/candlesticks"
    hist = f"{BASE}/historical/markets/{ticker}/candlesticks"
    for url in ([hist, live] if old else [live, hist]):
        r = get(url, params)
        if r is not None and r.status_code == 200 and r.json().get("candlesticks"):
            return r.json()["candlesticks"]
    return []

# Step 1: every settled market in each series
frames = []
for s, name in SERIES.items():
    recent = get_all("/markets", {"series_ticker": s, "status": "settled", "limit": 1000})
    older = get_all("/historical/markets", {"series_ticker": s, "limit": 1000})
    df = pd.DataFrame(recent + older)
    df["series"], df["event_type"] = s, name
    frames.append(df)
    print(f"{name}: {len(recent)} recent + {len(older)} historical", flush=True)

cols = ["event_type", "series", "ticker", "event_ticker", "title", "floor_strike", "cap_strike",
        "strike_type", "expiration_value", "result", "open_time", "close_time", "volume_fp"]
markets = pd.concat(frames).reindex(columns=cols).drop_duplicates("ticker")
markets = markets[markets["result"].isin(["yes", "no"])].sort_values("close_time")
markets.to_csv(HERE / "markets.csv", index=False)
print(markets.groupby(["event_type", markets["strike_type"].fillna("legacy (none)")]).size(), flush=True)
unknown = set(markets["strike_type"].dropna()) - KNOWN_STRIKES
if unknown:
    print("WARNING: unhandled strike types:", unknown, flush=True)
print(markets.groupby("event_type").agg(markets=("ticker", "count"),
      first=("close_time", "min"), last=("close_time", "max")), flush=True)

# Step 2: daily price history for each market
recent_cut = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=90)
rows, failed = [], []
for i, m in enumerate(markets.itertuples()):
    close = pd.Timestamp(m.close_time)
    start = int(pd.Timestamp(m.open_time).timestamp())
    end = int(close.timestamp()) + 86400
    cs = candles(m.series, m.ticker, start, end, old=close < recent_cut)
    if not cs:
        failed.append(m.ticker)
    for c in cs:
        rows.append({
            "ticker": m.ticker,
            "date": pd.to_datetime(c["end_period_ts"], unit="s", utc=True),
            "yes_bid": val(c["yes_bid"], "close"),
            "yes_ask": val(c["yes_ask"], "close"),
            "last_price": val(c["price"], "close"),
            "volume": c.get("volume_fp", c.get("volume")),
        })
    if (i + 1) % 100 == 0:
        print(f"{i + 1}/{len(markets)} done, slowed down {throttled} times", flush=True)
    time.sleep(0.2)

prices = pd.DataFrame(rows)
prices.to_csv(HERE / "prices.csv", index=False)
print(len(prices), "daily price rows for", prices["ticker"].nunique(), "markets")
print(len(failed), "markets with no price data:", failed[:5])