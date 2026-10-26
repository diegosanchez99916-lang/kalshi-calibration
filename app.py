import numpy as np
import pandas as pd
import altair as alt
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="Kalshi Calibration", page_icon="◐", layout="wide")

INK, MUTED, LINE, PAPER, RED = "#14171A", "#6A7178", "#D6D9D4", "#F3F4F1", "#C8102E"
# Sister series share a hue: CPI blues, jobs reds, Fed greens
TYPE_COLORS = {"CPI": "#1B2A41", "CPI YoY": "#5E7BA3", "Jobs": RED, "Unemployment": "#E58A6E",
               "Fed decision": "#4F7A6A", "Fed rate": "#93B5A4", "GDP": "#8A6D3B"}
FONT = "Archivo"
VFONT = "Archivo, Helvetica Neue, Arial, sans-serif"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@100..125,300..800&display=swap');
html, body, [class*="st-"], .stMarkdown, button, input {{ font-family: '{FONT}', sans-serif !important; }}
header[data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer {{ display: none !important; }}
.block-container, [data-testid="stMainBlockContainer"] {{ max-width: 1180px; padding: 4.5rem 2rem 5rem; }}
.stApp {{ background: {PAPER}; color: {INK}; }}
.kicker {{ color: {MUTED}; font-size: .95rem; margin-bottom: 1.4rem; }}
.hero {{ font-stretch: 118%; font-weight: 640; font-size: clamp(2.4rem, 5.6vw, 4.6rem);
        line-height: 1.02; letter-spacing: -.025em; margin: 0 0 1.6rem; max-width: 18ch; }}
.lede {{ font-size: 1.22rem; line-height: 1.55; max-width: 58ch; color: #2B3036; margin-bottom: 3rem; }}
.lede b {{ font-weight: 650; color: {INK}; font-variant-numeric: tabular-nums; }}
.stats {{ border-top: 1px solid {INK}; margin: 2rem 0 0; }}
.stat {{ padding: 1.1rem 0 1.2rem; }}
.stat + .stat {{ border-top: 1px solid {LINE}; }}
.stat .v {{ font-stretch: 112%; font-size: 2.1rem; font-weight: 600; font-variant-numeric: tabular-nums;
           letter-spacing: -.02em; }}
.stat .l {{ color: {MUTED}; font-size: .92rem; margin-top: .2rem; line-height: 1.4; }}
h2.sec {{ font-stretch: 112%; font-weight: 620; font-size: 1.7rem; letter-spacing: -.015em;
          margin: 0 0 .5rem; padding-top: 1.6rem; border-top: 1px solid {LINE}; }}
p.sub {{ color: {MUTED}; max-width: 62ch; line-height: 1.5; margin-bottom: 1.6rem; }}
table.t, table.t th, table.t td {{ border: none !important; }}
table.t {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; font-size: .98rem; }}
table.t th {{ text-align: right; font-weight: 500; color: {MUTED}; padding: .55rem 0;
             border-bottom: 1px solid {INK} !important; }}
table.t td {{ text-align: right; padding: .6rem 0; border-bottom: 1px solid {LINE} !important; }}
table.t th:first-child, table.t td:first-child {{ text-align: left; }}
table.t td.miss {{ color: {RED}; font-weight: 600; }}
.foot {{ color: {MUTED}; font-size: .9rem; line-height: 1.6; max-width: 70ch; margin-top: 4rem;
         padding-top: 1.4rem; border-top: 1px solid {LINE}; }}
.foot a {{ color: {INK}; }}
[data-testid="stWidgetLabel"] p {{ color: {MUTED}; font-size: .9rem; }}
@media (max-width: 700px) {{
  .block-container, [data-testid="stMainBlockContainer"] {{ padding: 2.5rem 1rem 3rem; }}
}}
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load(name="snapshots.csv"):
    return pd.read_csv(Path(__file__).parent / name)


def bootstrap_ci(df, n_boot=1000, seed=0):
    # Resample whole releases (a report and its date), since strikes on the same report move together
    r = df.groupby("release")["outcome"].agg(["sum", "size"])
    idx = np.random.default_rng(seed).integers(0, len(r), size=(n_boot, len(r)))
    rates = r["sum"].values[idx].sum(axis=1) / r["size"].values[idx].sum(axis=1)
    return np.percentile(rates, [2.5, 97.5])


def calibration(df):
    bins = np.linspace(0, 1, 11)
    labels = [f"{i*10}–{i*10+10}%" for i in range(10)]
    b = pd.cut(df["price"], bins, labels=labels, include_lowest=True)
    g = df.assign(bucket=b).groupby("bucket", observed=True)
    c = (g.agg(n=("outcome", "size"), price=("price", "mean"), hit=("outcome", "mean"))
          .reset_index())
    c[["lo", "hi"]] = [bootstrap_ci(x) for _, x in g]
    c["bucket"] = c["bucket"].astype(str)
    c["gap"] = (c["hit"] - c["price"]) * 100
    c["sig"] = (c["price"] < c["lo"]) | (c["price"] > c["hi"])
    return c


def calib_chart(c, color, height, show_axes=True):
    diag = alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]})).mark_line(
        strokeDash=[4, 4], color=MUTED, strokeWidth=1).encode(x="x:Q", y="y:Q")
    axis = alt.Axis(format="%", values=[0, .25, .5, .75, 1], grid=False, domainColor=LINE,
                    tickColor=LINE, labelColor=MUTED, titleColor=MUTED, labelFont=VFONT,
                    titleFont=VFONT, titleFontWeight=400, labelPadding=6)
    if not show_axes:
        axis = alt.Axis(format="%", values=[0, .5, 1], grid=False, domainColor=LINE, tickColor=LINE,
                        labelColor=MUTED, labelFont=VFONT, title=None)
    x = alt.X("price:Q", scale=alt.Scale(domain=[0, 1]), axis=axis,
              title="Market price the day before (implied probability)" if show_axes else None)
    y = alt.Y("hit:Q", scale=alt.Scale(domain=[0, 1]), axis=axis,
              title="How often it actually happened" if show_axes else None)
    tip = [alt.Tooltip("bucket:N", title="Price bucket"), alt.Tooltip("n:Q", title="Contracts"),
           alt.Tooltip("price:Q", title="Avg price", format=".1%"),
           alt.Tooltip("hit:Q", title="Happened", format=".1%")]
    line = alt.Chart(c).mark_line(color=color, strokeWidth=2.2).encode(x=x, y=y)
    pts = alt.Chart(c).mark_circle(color=color, opacity=1, stroke=PAPER, strokeWidth=2).encode(
        x=x, y=y, size=alt.Size("n:Q", scale=alt.Scale(range=[40, 520]), legend=None), tooltip=tip)
    return ((diag + line + pts).properties(height=height, background="transparent")
            .configure_view(stroke=None).configure(font=VFONT))


df = load()
types = sorted(df["event_type"].unique())

st.markdown('<div class="kicker">Kalshi economics markets, July 2021 to October 2026</div>',
            unsafe_allow_html=True)
st.markdown('<h1 class="hero">When Kalshi says 70%, does it happen 70% of the time?</h1>',
            unsafe_allow_html=True)

lede = st.empty()
left, right = st.columns([5, 2], gap="large")
with right:
    days = st.segmented_control("Price taken this far before release", [1, 7, 30], default=1,
                                format_func=lambda d: f"{d} day{'s' if d > 1 else ''}")
    picked = st.pills("Event types", types, default=types, selection_mode="multi")
days = days or 1
picked = picked or types

f = df[(df["days"] == days) & df["event_type"].isin(picked)]
cal = calibration(f)
brier = f["sq_err"].mean()
ece = (cal["n"] * cal["gap"].abs()).sum() / cal["n"].sum()
worst = cal.loc[cal["gap"].abs().idxmax()]

lede.markdown(f"""
<p class="lede">{"Mostly, yes." if ece < 5 else "Not quite."} Across <b>{len(f):,}</b> settled
contracts, prices taken {days} day{'s' if days > 1 else ''} before the data release missed the real
outcome rate by <b>{ece:.1f} points</b> on average. The widest miss was the {worst['bucket']}
bucket, which happened <b>{worst['hit']:.0%}</b> of the time.</p>
""", unsafe_allow_html=True)

with left:
    st.altair_chart(calib_chart(cal, INK, 560), use_container_width=True)
with right:
    st.markdown(f"""
<div class="stats">
  <div class="stat"><div class="v">{brier:.3f}</div><div class="l">Brier score. 0 is perfect,
  0.25 is a coin flip.</div></div>
  <div class="stat"><div class="v">{ece:.1f} pts</div><div class="l">Average gap between price
  and how often it happened.</div></div>
  <div class="stat"><div class="v">{len(f):,}</div><div class="l">Contracts in this view, each a
  yes/no bet on one data release.</div></div>
</div>
""", unsafe_allow_html=True)

st.markdown('<div style="height:3.5rem"></div>', unsafe_allow_html=True)
st.markdown('<h2 class="sec">Where the price was wrong</h2>'
            '<p class="sub">Each row groups contracts by their price. The 95% range comes from '
            'resampling whole data releases 1,000 times. Red marks buckets where the average price '
            'falls outside that range, so the gap is unlikely to be luck.</p>', unsafe_allow_html=True)
rows = "".join(
    f"<tr><td>{r.bucket}</td><td>{r.n:,}</td><td>{r.price:.1%}</td><td>{r.hit:.1%}</td>"
    f"<td>{r.lo:.1%}–{r.hi:.1%}</td>"
    f"<td class='{'miss' if r.sig else ''}'>{r.gap:+.1f}</td></tr>"
    for r in cal.itertuples())
st.markdown(f"<table class='t'><tr><th>Price bucket</th><th>Contracts</th><th>Average price</th>"
            f"<th>Happened</th><th>95% range</th><th>Gap (pts)</th></tr>{rows}</table>",
            unsafe_allow_html=True)

st.markdown('<div style="height:4rem"></div><h2 class="sec">By event type</h2>'
            '<p class="sub">The Fed signals its moves in advance, so both Fed series sit almost on the '
            'line. Payrolls are the hardest to call, even a day out, while the unemployment rate from '
            'the same jobs report is far easier. Year-over-year CPI is easier than the monthly change, '
            'since eleven of its twelve months are already known.</p>', unsafe_allow_html=True)
# Four small charts per row
cols = [c for _ in range(0, len(types), 4) for c in st.columns(4, gap="medium")]
for col, t in zip(cols, types):
    sub = df[(df["days"] == days) & (df["event_type"] == t)]
    with col:
        st.markdown(f"<div style='font-weight:620;font-stretch:112%;font-size:1.15rem'>{t}</div>"
                    f"<div style='color:{MUTED};font-size:.9rem;margin-bottom:.4rem'>Brier "
                    f"{sub['sq_err'].mean():.3f}, {len(sub):,} contracts</div>",
                    unsafe_allow_html=True)
        st.altair_chart(calib_chart(calibration(sub), TYPE_COLORS.get(t, INK), 220, False),
                        use_container_width=True)

st.markdown('<div style="height:3rem"></div><h2 class="sec">Does the market learn as the release nears?</h2>'
            '<p class="sub">Brier score by event type at each horizon. Lower is better.</p>',
            unsafe_allow_html=True)
tbl = df.pivot_table(index="event_type", columns="days", values="sq_err", aggfunc="mean")
rows = "".join(f"<tr><td>{t}</td>" + "".join(f"<td>{tbl.loc[t, d]:.3f}</td>" for d in (30, 7, 1))
               + "</tr>" for t in tbl.index)
st.markdown(f"<table class='t'><tr><th>Event type</th><th>30 days out</th><th>7 days out</th>"
            f"<th>1 day out</th></tr>{rows}</table>", unsafe_allow_html=True)

yearly, trend = load("yearly.csv"), load("yearly_trend.csv").set_index(["metric", "event_type"])
tr = lambda m, t: trend.loc[(m, t)]
fmt_slope = lambda r: f"{r.slope:+.3f} a year (95% range {r.slope_lo:+.3f} to {r.slope_hi:+.3f})"
cell = lambda y, t: yearly[(yearly["year"] == y) & (yearly["event_type"] == t)].iloc[0]
st.markdown(f"""<div style="height:3rem"></div><h2 class="sec">Is Kalshi getting more accurate?</h2>
<p class="sub">Prices 1 day before release, grouped by the year of the release. Two things change over
time besides skill. Series start in different years and some, like the Fed, are far easier to call,
so every trend here compares years within the same event type. And the share of close calls changes:
a perfectly priced 50% contract still scores 0.25, so the second view subtracts the Brier score the
prices themselves predicted. Zero there means prices were exactly as good as they claimed; above zero,
prices were overconfident; below, underconfident. The chart follows the event types picked above.</p>
<p class="lede" style="font-size:1.08rem;margin-bottom:1.6rem"><b>No overall change.</b> Within each
event type, the Brier score moved {fmt_slope(tr("brier", "All"))}, which is within noise.
<b>CPI</b> scores improved ({tr("brier", "CPI").slope:+.3f} a year), but mostly because fewer CPI
contracts were close calls. After allowing for difficulty, its trend is {tr("excess", "CPI").slope:+.3f}
a year, within noise. <b>Payrolls</b> got worse ({tr("brier", "Jobs").slope:+.3f} a year). About half
of that is harder questions ({cell(2026, "Jobs").close_calls:.0%} of 2026 payroll contracts were close
calls), and the rest is a borderline decline in pricing, {fmt_slope(tr("excess", "Jobs"))}, driven by
2026. <b>Unemployment</b>, settled by the same jobs report, went the other way: its Brier score
improved {tr("brier", "Unemployment").slope:+.3f} a year, and its prices went from overconfident in 2023
to slightly underconfident. The Fed rate's pricing error also moved
({tr("excess", "Fed rate").slope:+.3f} a year), but that is a tiny shift toward zero on a market that
is almost always right. Sixteen trends were tested, so about one would be flagged by chance. 2021
covers only July to December, with {cell(2021, "All").contracts} contracts.</p>
""", unsafe_allow_html=True)

view = st.segmented_control("Measure", ["Brier score", "Pricing error after difficulty"],
                            default="Brier score") or "Brier score"
m = "brier" if view == "Brier score" else "excess"
# Cells with under 3 releases are too thin to resample into a meaningful range
cells = yearly[yearly["event_type"].isin(picked) & (yearly["releases"] >= 3)].copy()
cells["x"] = cells["year"] + cells["event_type"].map({t: (k - (len(types) - 1) / 2) * 0.06
                                                         for k, t in enumerate(types)})
style = dict(grid=False, domainColor=LINE, tickColor=LINE, labelColor=MUTED, titleColor=MUTED,
             labelFont=VFONT, titleFont=VFONT, titleFontWeight=400)
x = alt.X("x:Q", scale=alt.Scale(domain=[2020.7, 2026.3]), title=None,
          axis=alt.Axis(format="d", values=sorted(cells["year"].unique()), **style))
y = alt.Y(f"{m}:Q", title=view + (" (lower is better)" if m == "brier" else " (0 = as claimed)"),
          axis=alt.Axis(**style))
# Solid circle swatches, so the legend isn't faded like the range bars
color = alt.Color("event_type:N", scale=alt.Scale(domain=list(TYPE_COLORS), range=list(TYPE_COLORS.values())),
                  legend=alt.Legend(title=None, orient="top", labelFont=VFONT, labelColor=MUTED,
                                    symbolType="circle", symbolOpacity=1))
tip = [alt.Tooltip("event_type:N", title="Event type"), alt.Tooltip("year:O", title="Year"),
       alt.Tooltip("contracts:Q", title="Contracts"), alt.Tooltip("releases:Q", title="Releases"),
       alt.Tooltip(f"{m}:Q", title=view, format=".3f"),
       alt.Tooltip(f"{m}_lo:Q", title="95% low", format=".3f"), alt.Tooltip(f"{m}_hi:Q", title="95% high", format=".3f")]
base = alt.Chart(cells)
layers = [base.mark_rule(strokeWidth=1.4, opacity=.55).encode(x=x, y=alt.Y(f"{m}_lo:Q"), y2=f"{m}_hi:Q", color=color),
          base.mark_line(strokeWidth=2).encode(x=x, y=y, color=color),
          base.mark_circle(size=70, opacity=1).encode(x=x, y=y, color=color, tooltip=tip)]
if m == "excess":
    layers.insert(0, alt.Chart(pd.DataFrame({"z": [0]})).mark_rule(strokeDash=[4, 4], color=MUTED).encode(y="z:Q"))
st.altair_chart(alt.layer(*layers).properties(height=380, background="transparent")
                .configure_view(stroke=None).configure(font=VFONT), use_container_width=True)

rng_ = lambda r, k, f: f"{r[k]:{f}}<span style='color:{MUTED}'> ({r[k + '_lo']:{f}} to {r[k + '_hi']:{f}})</span>"
rows = "".join(
    f"<tr><td>{r.year}{' (Jul–Dec)' if r.year == 2021 else ''}</td><td>{r.contracts:,}</td>"
    f"<td>{r.releases}</td><td>{r.close_calls:.0%}</td><td>{rng_(r._asdict(), 'brier', '.3f')}</td>"
    f"<td>{rng_(r._asdict(), 'adj_brier', '+.3f')}</td><td>{rng_(r._asdict(), 'adj_excess', '+.3f')}</td>"
    f"<td>{rng_(r._asdict(), 'gap', '.1f')}</td></tr>"
    for r in yearly[yearly["event_type"] == "All"].itertuples())
st.markdown('<p class="sub" style="margin-top:1.4rem">All event types together. The adjusted columns '
            'compare each contract with its own event type\'s usual level, so a change in the mix of '
            'event types does not show up as a trend. Close calls are contracts priced 10–90%. The '
            'calibration gap is pushed up by noise in small samples, which is why 2021 looks so bad, '
            'so its range is mostly below the estimate.</p>', unsafe_allow_html=True)
st.markdown(f"<table class='t'><tr><th>Year</th><th>Contracts</th><th>Releases</th><th>Close calls</th>"
            f"<th>Brier</th><th>Brier vs. usual for type</th><th>Pricing error vs. usual</th>"
            f"<th>Calibration gap (pts)</th></tr>{rows}</table>", unsafe_allow_html=True)

st.markdown("""
<div class="foot">Method: every settled Kalshi market in seven economics series: CPI (monthly and
year-over-year), jobs (payrolls and unemployment), Fed (decision and rate) and GDP,
pulled from the public Kalshi API. Price is the midpoint of the best bid and ask on the last daily
snapshot before the cutoff, or the last trade when the spread was wider than 20 cents. Built by
Diego Sanchez with Python, DuckDB and Streamlit.
<a href="https://github.com/diegosanchez99916-lang/kalshi-calibration">Code on GitHub</a>.</div>
""", unsafe_allow_html=True)