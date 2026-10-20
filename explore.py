import requests, json

url = "https://external-api.kalshi.com/trade-api/v2/markets"
params = {"series_ticker": "KXCPI", "status": "settled", "limit": 1}

response = requests.get(url, params=params)
data = response.json()

print(json.dumps(data["markets"][0], indent=2))