import duckdb
from pathlib import Path

HERE = Path(__file__).parent
con = duckdb.connect(str(HERE / "kalshi.duckdb"))

con.execute(f"""
CREATE OR REPLACE TABLE markets AS
SELECT * REPLACE (CAST(open_time AS TIMESTAMPTZ) AS open_time,
                  CAST(close_time AS TIMESTAMPTZ) AS close_time)
FROM read_csv_auto('{HERE / "cpi_markets.csv"}')
""")

con.execute(f"""
CREATE OR REPLACE TABLE prices AS
SELECT * REPLACE (CAST(date AS TIMESTAMPTZ) AS date)
FROM read_csv_auto('{HERE / "cpi_prices.csv"}')
""")

print("Markets by result:")
con.sql("""
SELECT result, COUNT(*) AS markets
FROM markets
GROUP BY result
""").show()

print("Markets per year:")
con.sql("""
SELECT YEAR(close_time) AS year,
       COUNT(DISTINCT event_ticker) AS months,
       COUNT(*) AS markets
FROM markets
GROUP BY year
ORDER BY year
""").show()

print("Price days per market (JOIN check):")
con.sql("""
SELECT m.ticker, m.result, COUNT(p.date) AS price_days
FROM markets m
JOIN prices p ON m.ticker = p.ticker
GROUP BY m.ticker, m.result
ORDER BY price_days DESC
LIMIT 5
""").show()