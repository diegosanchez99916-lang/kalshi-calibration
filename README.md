# Are Kalshi Economics Markets Calibrated?

**When a Kalshi market says 70%, does the event actually happen about 70% of the time?**

This project pulls every settled Kalshi contract on CPI, jobs reports, Fed decisions and GDP
(July 2021 – October 2026), takes each market's price before the data release, and checks
how often those events really happened.

**[Live dashboard](https://kalshi-calibration-g5d69fgdf7ztnxstxevy2q.streamlit.app/)**

## Main finding

One day before release, across **1,162 contracts**, Kalshi prices were off from real outcome
frequencies by **3.0 percentage points** on average, with a **Brier score of 0.100**
(vs. 0.250 for always guessing the base rate). Accuracy ranged from near-perfect on Fed
decisions to weakest on jobs reports.

![Calibration curve](charts/calibration_by_horizon.png)

## Results by event type

Brier score (0 = perfect, 0.25 = coin flip). Lower is better.

| Event type | Markets | 30 days before | 7 days before | 1 day before |
|---|---|---|---|---|
| Fed decisions | 145 | 0.033 | 0.014 | 0.005 |
| CPI | 522 | 0.121 | 0.072 | 0.067 |
| GDP | 183 | 0.121 | 0.100 | 0.112 |
| Jobs (payrolls) | 396 | 0.168 | 0.170 | 0.166 |

- **Fed markets are almost perfectly priced**, since the Fed signals its decisions in advance.
- **CPI markets learn the most** as the release approaches (0.121 → 0.067).
- **Jobs markets barely improve**, even a day out. Payrolls stay hard to predict.

## Where the market missed

| Price bucket | Contracts | Avg price | Actually happened |
|---|---|---|---|
| 10–20% | 78 | 15% | 24% |
| 70–80% | 63 | 75% | 59% |

Low-probability contracts won more often than priced, and 70–80% contracts won less often.
Bucket sizes are small, so some of this may be noise. Confidence intervals are a planned next step.

## Method

1. **Data:** every settled market in four Kalshi series (`KXCPI`, `KXPAYROLLS`, `KXFEDDECISION`,
   `KXGDP`) from the public API, combining live and historical endpoints: 1,246 markets and
   83,590 daily price records.
2. **Price snapshot:** for each market, the last daily price at least 1, 7 or 30 days before close.
   Price = midpoint of best bid and ask, or the last trade if the spread exceeded 20¢.
3. **Calibration:** contracts grouped into 10-point price buckets; each bucket's average price
   compared with the share that settled yes.
4. **Brier score:** mean of (price − outcome)², overall and by event type.

**Caveats:** 58% of contracts were priced below 10% or above 90% the day before, and those easy
calls make the overall Brier score look better. Jobs and Fed data start in 2023.

## Tools

Python (requests, pandas, matplotlib), DuckDB + SQL, Streamlit, GitHub.

## Run it yourself

```
pip install requests pandas duckdb matplotlib streamlit
python pull_all.py      # pull markets and daily prices (~10 min)
python build_db.py      # load into DuckDB
python analysis.py      # calibration, Brier scores, charts
streamlit run app.py    # dashboard
```

## Files

| File | What it does |
|---|---|
| `explore.py` | First look at one raw market from the API |
| `find_series.py` | Lists economics series on Kalshi |
| `pull_all.py` | Pulls all settled markets and daily price history |
| `build_db.py` | Loads CSVs into DuckDB and runs SQL checks |
| `analysis.py` | Calibration tables, Brier scores and charts |
| `app.py` | Streamlit dashboard |

Built with AI assistance (Claude) for code generation; analysis design and interpretation are my own.