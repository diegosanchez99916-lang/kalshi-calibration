import duckdb
from pathlib import Path

HERE = Path(__file__).parent
con = duckdb.connect(str(HERE / "kalshi.duckdb"))

con.execute(f"""
CREATE OR REPLACE TABLE markets AS
SELECT * REPLACE (CAST(open_time AS TIMESTAMPTZ) AS open_time,
                  CAST(close_time AS TIMESTAMPTZ) AS close_time)
FROM read_csv_auto('{HERE / "markets.csv"}')
""")

con.execute(f"""
CREATE OR REPLACE TABLE prices AS
SELECT * REPLACE (CAST(date AS TIMESTAMPTZ) AS date)
FROM read_csv_auto('{HERE / "prices.csv"}')
""")

print("Contracts by event type:")
con.sql("""
SELECT event_type,
       COUNT(*) AS markets,
       SUM(CASE WHEN result THEN 1 ELSE 0 END) AS settled_yes,
       COUNT(DISTINCT event_ticker) AS events
FROM markets
GROUP BY event_type
ORDER BY markets DESC
""").show()

print("Price coverage (JOIN check):")
con.sql("""
SELECT m.event_type,
       COUNT(DISTINCT p.ticker) AS markets_with_prices,
       COUNT(*) AS price_rows
FROM markets m
JOIN prices p ON m.ticker = p.ticker
GROUP BY m.event_type
ORDER BY price_rows DESC
""").show()