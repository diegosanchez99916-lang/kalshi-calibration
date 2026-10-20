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

Each bucket's 95% interval comes from a bootstrap that resamples whole data releases 1,000 times.
It resamples releases instead of single contracts because strikes on the same release move together.

| Price bucket | Contracts | Avg price | Actually happened | 95% interval |
|---|---|---|---|---|
| 10–20% | 78 | 15% | 24% | 14.5–34.9% |
| 70–80% | 63 | 75% | 59% | 44.8–73.5% |

- **70–80% is the one real miss, and only barely.** One day before release, these contracts were
  priced at 75% but happened 59% of the time. The interval excludes the price by about one point.
  Jobs reports drive most of it: 33 of the 63 contracts, with a 55% hit rate. The miss doesn't
  appear at other horizons: the same bucket hit 71% at 7 days out and 80% at 30 days out.
- **10–20% is not significant.** Its interval includes the 15% average price.
- **Some flags will happen by chance.** 30 buckets were tested (10 buckets × 3 horizons), so at 95%
  confidence about 1.5 would be flagged by chance alone. The 7-day 0–10% and 90–100% flags are
  1–2 point gaps where nearly every contract settled the same way, and they shouldn't be read as
  real mispricing.

## Method

1. **Data:** every settled market in four Kalshi series (`KXCPI`, `KXPAYROLLS`, `KXFEDDECISION`,
   `KXGDP`) from the public API, combining live and historical endpoints: 1,246 markets and
   83,590 daily price records.
2. **Price snapshot:** for each market, the last daily price at least 1, 7 or 30 days before close.
   Price = midpoint of best bid and ask, or the last trade if the spread exceeded 20¢.
3. **Calibration:** contracts grouped into 10-point price buckets; each bucket's average price
   compared with the share that settled yes.
4. **Brier score:** mean of (price − outcome)², overall and by event type.
5. **Confidence intervals:** 95% bootstrap interval on each bucket's hit rate, resampling whole
   releases (`event_ticker`) 1,000 times. A gap is significant when the average price falls outside it.

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