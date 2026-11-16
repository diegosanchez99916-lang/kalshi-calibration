# Forward test: the 70–80% sell-YES rule (v1)

A pre-registered, blind test of one trading rule. This file was committed before any new data
was pulled and before any code for the test was written. The rule below is frozen. Any change
to it is a new version (v2) with its own ledger; v1 results are never recomputed under new rules.

## Why

`tradability.py` found that selling YES at the bid on contracts priced 70–80% one day before
close made +11.06¢ per contract after fees in the original seven series (102 contracts, 74
releases, 95% interval +0.92¢ to +21.40¢). `tradability_checks.py` showed that result is
fragile: the interval includes zero under a volume filter and when the price window moves by 5
points, and the bucket was chosen after seeing the outcomes. A result found that way can only
be tested on data the rule has never seen.

## Freeze record

- **Freeze timestamp (UTC):** the committer timestamp of the commit that first adds this file.
  It is recorded in the line below by a follow-up commit, together with that commit's hash.
- **Recorded freeze:** _added in the next commit_
- The public proof of the date is the push to GitHub, not the local commit time. No data is
  pulled and no test code is written until after that push.
- **What had been seen at the freeze:** markets in the original seven series that closed on or
  before 2026-10-14 (the last pull, on 2026-10-26). Nothing from any other Kalshi series, and
  nothing from the seven series after that pull, had been downloaded or looked at.

## The frozen rule (v1)

Definitions are copied from `tradability.py` and `analysis.py`. Before freezing, a plain-pandas
version of these definitions was checked against the existing files: it reproduces all 2,484
one-day rows of `snapshots.csv` exactly, and the same 102 contracts and +11.06¢ as `tradability.py`.

1. **Snapshot.** For each market, the last daily candle whose end timestamp is at least 1 day
   and less than 8 days before the market's `close_time` (1 day = 24 hours). The candle's
   CLOSE values are used: `yes_bid`, `yes_ask`. If that one candle fails the quote test below,
   the contract is dropped; there is no fallback to an earlier candle. A market with no candle
   in the window is dropped.
2. **Tradable quote.** `yes_bid` and `yes_ask` both present, `yes_bid > 0`, `0 < yes_ask < 1.00`,
   and spread (`yes_ask − yes_bid`) `<= 0.20`.
3. **Bucket.** mid = (`yes_bid` + `yes_ask`) / 2. The contract qualifies if the mid is above 70¢
   and at most 80¢: `70 < round(mid × 100, 4) <= 80`. A mid of exactly 70¢ is out; exactly 80¢
   is in. These are the edges `tradability.py` uses.
4. **Trade.** Sell 1 YES at the bid and hold to settlement.
5. **P&L in cents** = 100 × (`yes_bid` − outcome − fee(`yes_bid`)), where outcome is 1 if the
   market settled yes and 0 if it settled no, and fee(p) = 0.07 × p × (1 − p). Fees at 1x, not
   rounded. Markets with any other result are dropped and counted.
6. **Primary metric.** Mean net P&L per contract in cents, with a 95% interval from a
   release-level bootstrap: whole releases resampled with replacement 1,000 times, NumPy
   `default_rng(0)`, 2.5th and 97.5th percentiles of the resampled means.
7. **Release.** One report on one date: the report family plus the UTC date of `close_time`.
   Families for the seven series are as in `analysis.py` (CPI and CPI YoY share one; Jobs and
   Unemployment share one; Fed decision and Fed rate share one; GDP alone). Families for any new
   series are fixed in the series inclusion list below, before their prices are pulled. Series
   settled by the same report on the same day share a family.

### Where this differs from the wording I was given

- The brief said the snapshot is "no more than 8 days" before close. `analysis.py` uses strictly
  less than 8 days, so that is what is frozen. No existing row sits on that edge.
- Nothing else differs. The quote test, bucket edges, fee and P&L formula match `tradability.py`.

## Test A: new instruments, settled history (run once)

**Question:** does the 70–80% overpricing show up in Kalshi economics series the rule never saw?

**Series inclusion criteria (fixed now, applied without looking at any price or P&L):**

- Listed in Kalshi's Economics category.
- Not one of the seven series already in this repo (`KXCPI`, `KXCPIYOY`, `KXPAYROLLS`, `KXU3`,
  `KXFEDDECISION`, `KXFED`, `KXGDP`).
- Its settled markets form a threshold ladder on one number: several strikes per event, each
  asking whether one published number is above (or at least, or below) a threshold. Series
  built on named outcomes, mentions, ranges with both a floor and a cap, sports or anything
  else that is not a threshold on one number are excluded.
- At least 20 settled events.
- Within an included series, only threshold markets are used; any market of another type is
  dropped and counted.

The included and excluded series, with the reason for each exclusion and each included series'
report family, are appended to this file and committed **before** any price is pulled.

**Sample:** every settled threshold market in the included series with `close_time` at or
before the freeze timestamp. Markets that close after the freeze belong to Test B only, so no
contract is counted in both tests.

**Reported:** per series and pooled: contracts, releases, mean net P&L, 95% interval, average
price and hit rate in the bucket, mean spread, median daily volume, contracts dropped by the
quote test, and the share of candidate contracts with zero volume on the snapshot day.

**Decision rule:**

- **Supported:** the pooled 95% interval's lower bound is above zero, with at least 60 contracts
  from at least 40 releases.
- **Too few contracts:** fewer than 60 contracts or fewer than 40 releases, whatever the mean.
- **Not supported:** enough contracts, and the interval's lower bound is at or below zero.

The test is run once. No other bucket, side or filter is run as a test. A full bucket table may
be printed for context and is labeled descriptive.

## Test B: live forward ledger (ongoing)

**Sample:** every settled market in the original seven series plus the Test A series whose
`close_time` is after the freeze timestamp. `forward_update.py` appends each qualifying contract
to `forward_ledger.csv` once, after it settles. Past rows are never rewritten or reordered.

**Scoreboard (`FORWARD_SCOREBOARD.md`):** contracts and releases so far and the running mean P&L.
A bootstrap interval is shown only from 30 contracts. Until there are 100 contracts the
scoreboard says "no inference until n >= 100".

**Decision rule:** one evaluation, at the first scoreboard update with at least 100 contracts.

- **Supported:** the 95% interval's lower bound is above zero and the contracts come from at
  least 40 releases.
- **Not supported:** otherwise.

Fixing the sample size in advance is what keeps the ledger honest: looking every week and
stopping when the number looks good would manufacture a result. After that one evaluation the
ledger keeps running as a description, not as further tests.

## Sample size: how long this takes

Contracts that qualified for the rule in the original seven series, by year of close:

| Year | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 (to Oct 14) |
|---|---|---|---|---|---|---|
| Contracts | 1 | 13 | 16 | 14 | 20 | 38 |
| Releases | 1 | 12 | 14 | 14 | 15 | 18 |

- 2023–2025 averaged 16.7 qualifying contracts a year. 2026 is running at about 48.5 a year.
- A forward-only test on the seven series would therefore reach 100 contracts in roughly **2
  years at the 2026 pace, or about 6 years at the 2023–2025 pace.**
- The Test A series will add to the forward ledger, by an amount unknown until they are pulled.
- The original result needed 102 contracts to get an interval of +0.92¢ to +21.40¢. A forward
  sample of 100 with the same spread of outcomes would give an interval about as wide. It could
  confirm an edge near 11¢; it could not tell a small edge from none.

## What this test can and cannot prove

**It can show**

- Whether the 70–80% pattern appears in series (Test A) and in a period (Test B) that played
  no part in finding it, with the rule, the sample and the decision fixed in advance.
- Whether the paper profit survives the quoted spread and today's fee formula.

**It cannot show**

- That the trade could actually have been done. Quotes are daily closing values, depth is
  unknown, and every row assumes one contract fills at the bid.
- Anything about other buckets, sides or horizons. They are not tested.
- That a "supported" result will last, or that a "not supported" result proves there is no
  edge: with this few contracts a real but small edge would usually not be detected.
- That fees were right. One formula, today's general taker schedule, is applied to every
  series and every year.
- Independence between the two tests in the strict sense: Test A's series are different
  instruments but cover the same years and the same economy as the original sample.
