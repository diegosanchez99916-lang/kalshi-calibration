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

## Is Kalshi getting more accurate?

No overall change from 2021 to 2026. One event type improved and one got worse, and those two
changes come mostly from how hard the questions were.

![Brier over time](charts/brier_over_time.png)

Prices 1 day before release, grouped by the year of the release. Two things change over the
years besides skill, and both are handled:

- **Event-type mix.** Fed and Jobs markets start in 2023, and Fed is far easier to call. So
  trends are measured *within* each event type (each type's average level is removed), and the
  "vs. usual" columns compare each contract with its own type's all-years average.
- **Question difficulty.** A perfectly priced 50% contract still scores 0.25. The *pricing
  error* column subtracts the Brier score the prices themselves predicted, p(1−p). It averages
  zero for a well-calibrated market however hard the questions are, and positive means prices
  were worse than their confidence implied.

All event types together (95% intervals resample whole releases):

| Year | Contracts | Releases | Close calls (10–90%) | Brier | Brier vs. usual for type | Pricing error vs. usual |
|---|---|---|---|---|---|---|
| 2021 (Jul–Dec) | 12 | 8 | 83% | 0.137 (0.069–0.252) | +0.062 (−0.008 to +0.180) | −0.035 (−0.082 to +0.059) |
| 2022 | 127 | 16 | 46% | 0.115 (0.087–0.150) | +0.042 (+0.013 to +0.076) | +0.017 (−0.010 to +0.049) |
| 2023 | 214 | 31 | 33% | 0.050 (0.034–0.069) | −0.042 (−0.060 to −0.023) | −0.027 (−0.044 to −0.009) |
| 2024 | 243 | 36 | 39% | 0.098 (0.072–0.123) | −0.006 (−0.029 to +0.019) | −0.001 (−0.023 to +0.023) |
| 2025 | 245 | 36 | 35% | 0.086 (0.061–0.112) | −0.015 (−0.039 to +0.009) | −0.004 (−0.025 to +0.018) |
| 2026 | 321 | 29 | 52% | 0.138 (0.086–0.186) | +0.025 (−0.009 to +0.062) | +0.017 (−0.014 to +0.051) |

Change per year, within event type (negative = improving):

| | Brier | Pricing error |
|---|---|---|
| All types | +0.004 (−0.007 to +0.015), noise | +0.006 (−0.003 to +0.015), noise |
| CPI | **−0.015 (−0.023 to −0.007)** | −0.004 (−0.011 to +0.005), noise |
| Jobs | **+0.051 (+0.024 to +0.076)** | **+0.028 (+0.001 to +0.053)**, borderline |
| Fed | −0.000, noise | −0.000, noise |
| GDP | +0.011, noise | +0.015, noise |

- **No overall trend.** After controlling for event type, neither the Brier score nor the
  pricing error moved by more than noise.
- **CPI scores improved, but the questions got easier.** Close calls fell from 46% of CPI
  contracts in 2022 to 22% in 2026. After allowing for that, CPI pricing shows no trend.
- **Jobs got worse, about half from harder questions.** 84% of 2026 jobs contracts were close
  calls. The rest is a borderline decline in pricing, driven by 2026 (10 releases). Ten trends
  were tested, so one borderline result can happen by chance. Worth watching, not yet a finding.
- **Fed prices are a bit underconfident every year:** outcomes were more certain than prices.
- **Small samples:** 2021 is 12 contracts and GDP has 3–4 releases a year, so their intervals
  are wide (and for GDP, probably still too narrow). The calibration gap (in `yearly.csv`) is
  pushed up by noise in small samples, which is why 2021 shows 24 points. It isn't used for the trend.

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
6. **Over time:** year of each release (`close_time`), 1 day before close. Trends are fixed-effects
   slopes within event type, with release-level bootstrap intervals; see the section above.

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
| `yearly.csv`, `yearly_trend.csv` | Yearly results and trends written by `analysis.py`, read by the dashboard |
| `app.py` | Streamlit dashboard |

Built with AI assistance (Claude) for code generation; analysis design and interpretation are my own.