import requests
import pandas as pd
from pathlib import Path

BASE = "https://external-api.kalshi.com/trade-api/v2"

def get_all(path, params):
    markets = []
    cursor = ""
    while True:
        params["cursor"] = cursor
        r = requests.get(BASE + path, params=params)
        r.raise_for_status()
        data = r.json()
        markets += data["markets"]
        cursor = data.get("cursor")
        if not cursor:
            break
    return markets

recent = get_all("/markets", {"series_ticker": "KXCPI", "status": "settled", "limit": 1000})
older = get_all("/historical/markets", {"series_ticker": "KXCPI", "limit": 1000})

df = pd.DataFrame(recent + older)
cols = ["ticker", "event_ticker", "title", "floor_strike", "strike_type",
        "expiration_value", "result", "open_time", "close_time", "volume_fp"]
df = df.reindex(columns=cols).drop_duplicates("ticker").sort_values("close_time")

df.to_csv(Path(__file__).parent / "cpi_markets.csv", index=False)

print(len(recent), "recent +", len(older), "historical =", len(df), "markets")
print("From", df["close_time"].min(), "to", df["close_time"].max())
print(df["result"].value_counts())