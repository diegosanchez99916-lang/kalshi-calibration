import time
import requests
import pandas as pd
from pathlib import Path

BASE = "https://external-api.kalshi.com/trade-api/v2"
HERE = Path(__file__).parent

def get(url, params):
    for attempt in range(5):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            return r
        except requests.RequestException:
            time.sleep(2 ** attempt)
    return None

def val(d, key):
    if not d:
        return None
    return d.get(key + "_dollars", d.get(key))

def candles(ticker, start, end):
    params = {"start_ts": start, "end_ts": end, "period_interval": 1440}
    urls = [f"{BASE}/series/KXCPI/markets/{ticker}/candlesticks",
            f"{BASE}/historical/markets/{ticker}/candlesticks"]
    for url in urls:
        r = get(url, params)
        if r is not None and r.status_code == 200 and r.json().get("candlesticks"):
            return r.json()["candlesticks"]
    return []

markets = pd.read_csv(HERE / "cpi_markets.csv")
rows, failed = [], []

for i, m in markets.iterrows():
    start = int(pd.Timestamp(m["open_time"]).timestamp())
    end = int(pd.Timestamp(m["close_time"]).timestamp()) + 86400
    cs = candles(m["ticker"], start, end)
    if not cs:
        failed.append(m["ticker"])
    for c in cs:
        rows.append({
            "ticker": m["ticker"],
            "date": pd.to_datetime(c["end_period_ts"], unit="s", utc=True),
            "yes_bid": val(c["yes_bid"], "close"),
            "yes_ask": val(c["yes_ask"], "close"),
            "last_price": val(c["price"], "close"),
            "volume": c.get("volume_fp", c.get("volume")),
        })
    if (i + 1) % 50 == 0:
        print(f"{i + 1}/{len(markets)} markets done")
    time.sleep(0.1)

prices = pd.DataFrame(rows)
prices.to_csv(HERE / "cpi_prices.csv", index=False)
print(len(prices), "daily price rows for", prices["ticker"].nunique(), "markets")
print(len(failed), "markets with no price data:", failed[:5])