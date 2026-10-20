import requests

url = "https://external-api.kalshi.com/trade-api/v2/series"
r = requests.get(url, params={"category": "Economics", "include_volume": "true"})
series = r.json()["series"]

keywords = ["job", "payroll", "unemploy", "fed", "rate", "gdp", "cpi", "inflation"]
hits = [s for s in series if any(k in s["title"].lower() for k in keywords)]
hits.sort(key=lambda s: float(s.get("volume_fp") or 0), reverse=True)

for s in hits[:25]:
    print(f'{s["ticker"]:<20} {s.get("frequency",""):<10} {float(s.get("volume_fp") or 0):>14,.0f}  {s["title"]}')