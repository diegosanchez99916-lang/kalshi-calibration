# Method: market quality and strike-ladder consistency

Written and committed before any result was computed. The scripts `market_quality.py` and
`consistency.py` implement exactly this. Nothing here is changed after seeing results; if a
rule turns out to be wrong for the data, the scripts report that instead of quietly adapting.

**Question (descriptive):** what does it cost to trade Kalshi's economics markets, and are the
strike ladders internally consistent?

**Data:** `prices.csv`, `markets.csv` and `snapshots.csv` only. No new pull, no database rebuild,
no new packages. No existing script, output, chart or README number is modified.

## Definitions

- **Daily row:** one candle in `prices.csv` (closing `yes_bid`, `yes_ask`, `last_price`, and the
  day's `volume`), joined to `markets.csv` on `ticker` for `event_type` and `close_time`.
- **Tradable quote:** `yes_bid > 0`, `yes_ask > 0` and `< 1.00`, spread (`ask - bid`) `<= 0.20`.
  Same rule as `tradability.py`.
- **Days to close:** (market `close_time` − candle end timestamp) in days.
  Rows with negative days to close (the candle ends after the market closed, so its closing
  quote is post-close) are excluded from every cut, and the count is printed.
- **Days-to-close bins:** 0-1, 1-3, 3-7, 7-14, 14-30, 30+. Lower edge included, upper excluded.
- **Mid:** (bid + ask) / 2. **Price bucket:** 10-point bucket of the mid, same edges as
  `analysis.py` (above the lower edge, up to and including the upper; the first includes 0).
- **Era:** "legacy" if the market's close time in US Eastern is at or after noon, "new" if before
  noon. The script prints the number of markets in each era and the close clock times by event
  type and era.
  - *Ambiguity check, fixed now:* the brief describes legacy closes as about 7pm ET and new
    closes as 08:25-08:29 ET. A market is "ambiguous" if its ET close time is in neither
    18:00-19:59 nor 08:00-08:59. Ambiguous markets are still assigned by the noon rule, their
    count is printed by event type, and the overall era rows are shown both for all markets
    and excluding ambiguous ones.
  - *Known before running:* Fed decision and Fed rate markets close around 1:55pm ET on meeting
    day (seen in earlier work), so the noon rule will label them "legacy" although they are not
    evening-before closes. The era cuts within CPI, Jobs and Unemployment are unaffected.
- **Cost to take a position and hold to settlement,** per contract in cents: half the spread
  plus the taker fee `0.07 * P * (1 - P)` at the mid price. Shown at 0x, 1x and 2x fees.
  This ignores depth and assumes the bid or ask is available for one contract. The fee is
  today's general formula applied to all years.
- **Too small:** a cell with fewer than 30 daily rows is marked `too_small`. A cell with fewer
  than 30 *tradable* rows is marked `few_tradable`, since spread and cost use tradable rows only.

## Part A: cost and liquidity profile (`market_quality.py` → `market_quality.csv`)

All daily rows with days to close >= 0, not only the 1/7/30-day snapshots. For every cell:
number of daily rows, share with a tradable quote, median and mean spread in cents (tradable
rows), median daily volume (all rows in the cell), and median all-in cost in cents at 0x, 1x
and 2x fees (tradable rows).

1. By event type (7 types).
2. By days-to-close bin.
3. By mid-price bucket (tradable rows only, so the tradable share is 100% by construction).
4. By era: overall (all markets, and excluding ambiguous), and within CPI, Jobs, Unemployment.
5. Event type × days-to-close bin, one table. This is the main exhibit.
6. Spread vs. volume: within each event type, split tradable rows into terciles of daily volume
   (`pd.qcut`; if tied values such as many zero-volume days make boundaries coincide, fewer
   than three groups are reported and said so). Report median spread and the volume range per
   group, plus the Spearman rank correlation between spread and volume as a description, not a
   test. "Weak" means |correlation| below 0.2.

No significance tests in Part A.

## Part B: strike-ladder consistency (`consistency.py` → `consistency.csv`)

Events with an "above X" ladder: CPI, CPI YoY, Jobs, Unemployment, GDP, Fed rate. Fed decision
is categorical and excluded; Fed decision and Fed rate are never compared. Snapshots at
`days == 1`, `7` and `30` from `snapshots.csv`, joined to `markets.csv` on `ticker` for strikes.

1. **Strike:** `floor_strike` if present, otherwise the number after `-T` in the ticker. Each
   strike is checked against the numbers in the title text (ignoring commas and percent signs;
   a title in thousands or millions is accepted if it matches after scaling). Unparseable
   strikes and title mismatches are printed. The script also prints how many markets are
   confirmed "above" by `strike_type = greater` or by the title's wording, and lists any that
   are not; those are excluded from ladders.
2. **Ladder:** the strikes of one event at one horizon, sorted ascending. Only events with at
   least 3 priced strikes at that horizon count as ladders. Two strikes with the same value in
   one event are printed and the event is skipped.
3. **Pairs:** adjacent strikes (lower, higher). A pair is checked only if both snapshots come
   from the same candle timestamp, because quotes from different days are not comparable.
   Pairs dropped for mismatched dates are counted.
4. **Tests.** P(X > k) must not increase with k.
   - **(a) Mid violation:** `mid_higher > mid_lower`, mid = (bid + ask) / 2, on pairs where both
     legs have a tradable quote. Size in probability points.
   - **(a2) Analysis-price violation:** the same test using the `price` column the calibration
     analysis used (mid, or last trade when the spread is over 20¢), on all same-date pairs.
     This shows whether the calibration inputs themselves are consistent; violations here can
     come from stale last trades.
   - **(b) Executable violation:** `yes_bid_higher > yes_ask_lower`, both legs tradable. Buying
     YES at the lower strike's ask and selling YES at the higher strike's bid pays at least $0
     in every outcome, so `bid_higher − ask_lower` is a risk-free profit before fees. Net of
     fees subtracts `0.07 * P * (1 − P)` at each leg's traded price. "Survives fees" means net > 0.
5. **Report** by event type and horizon: ladders (events with at least 3 strikes), adjacent pairs
   checked, pairs dropped for date mismatch, pairs with both legs tradable; mid violations
   (count, share of tradable pairs, median and max size); analysis-price violations (count,
   share of pairs); executable violations before fees and after fees (count, median and max
   size in cents).
6. **Top 10:** the 10 largest executable violations ranked by size after fees (shown even if the
   net is negative), with event, strikes, quotes and date.

## Outputs

- `market_quality.csv` and `consistency.csv`, each with a `table` column.
- `charts/spread_by_days_to_close.png`: median spread by days-to-close bin, one line per event
  type; bins under 30 tradable rows are drawn hollow.
- `charts/ladder_violations.png`: share of adjacent pairs with a mid violation and with an
  executable violation (before fees), by event type, all horizons pooled.
- `README.md`: a section "Market quality: what does it cost to trade?".

## Caveats fixed in advance

- Quotes are daily closing values. The bid and ask of two strikes may not have coexisted at one
  instant, and daily data cannot show how long a quote stood.
- Depth is unknown. Every number assumes one contract fills at the quoted price.
- The fee is today's general taker formula, applied to all years.
- Legacy and new markets close at different times of day relative to the data release, so
  "days to close" does not mean the same distance to the release in both eras.
