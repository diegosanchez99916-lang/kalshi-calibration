import numpy as np
import pandas as pd
import altair as alt
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="Kalshi Calibration", page_icon="◐", layout="wide")

INK, MUTED, LINE, PAPER, RED = "#14171A", "#6A7178", "#D6D9D4", "#F3F4F1", "#C8102E"
TYPE_COLORS = {"CPI": "#1B2A41", "Jobs": RED, "GDP": "#8A6D3B", "Fed": "#4F7A6A"}
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
def load():
    return pd.read_csv(Path(__file__).parent / "snapshots.csv")


def calibration(df):
    bins = np.linspace(0, 1, 11)
    labels = [f"{i*10}–{i*10+10}%" for i in range(10)]
    b = pd.cut(df["price"], bins, labels=labels, include_lowest=True)
    c = (df.assign(bucket=b).groupby("bucket", observed=True)
           .agg(n=("outcome", "size"), price=("price", "mean"), hit=("outcome", "mean"))
           .reset_index())
    c["bucket"] = c["bucket"].astype(str)
    c["gap"] = (c["hit"] - c["price"]) * 100
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
            '<p class="sub">Each row groups contracts by their price. Red marks a gap of 8 points or '
            'more between what the market said and what happened.</p>', unsafe_allow_html=True)
rows = "".join(
    f"<tr><td>{r.bucket}</td><td>{r.n:,}</td><td>{r.price:.1%}</td><td>{r.hit:.1%}</td>"
    f"<td class='{'miss' if abs(r.gap) >= 8 else ''}'>{r.gap:+.1f}</td></tr>"
    for r in cal.itertuples())
st.markdown(f"<table class='t'><tr><th>Price bucket</th><th>Contracts</th><th>Average price</th>"
            f"<th>Happened</th><th>Gap (pts)</th></tr>{rows}</table>", unsafe_allow_html=True)

st.markdown('<div style="height:4rem"></div><h2 class="sec">By event type</h2>'
            '<p class="sub">Fed decisions are signaled in advance, so their prices sit almost on the '
            'line. Jobs reports are the hardest to call, even a day out.</p>', unsafe_allow_html=True)
cols = st.columns(len(types), gap="medium")
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

st.markdown("""
<div class="foot">Method: every settled Kalshi market in the CPI, jobs, Fed decision and GDP series,
pulled from the public Kalshi API. Price is the midpoint of the best bid and ask on the last daily
snapshot before the cutoff, or the last trade when the spread was wider than 20 cents. Built by
Diego Sanchez with Python, DuckDB and Streamlit.
<a href="https://github.com/diegosanchez99916-lang/kalshi-calibration">Code on GitHub</a>.</div>
""", unsafe_allow_html=True)