import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="Kalshi Calibration", layout="wide")

@st.cache_data
def load():
    return pd.read_csv(Path(__file__).parent / "snapshots.csv")

df = load()
all_types = sorted(df["event_type"].unique())

st.title("Are Kalshi economics markets calibrated?")
st.write("When a Kalshi market says 70%, does the event actually happen about 70% of the time? "
         "This compares each market's price before close to what really happened, using every "
         "settled Kalshi CPI, jobs, Fed and GDP contract from July 2021 to October 2026.")

with st.sidebar:
    st.header("Filters")
    types = st.multiselect("Event type", all_types, default=all_types)
    days = st.radio("Price taken this many days before close", [1, 7, 30], horizontal=True)
    n_bins = st.slider("Number of price buckets", 5, 20, 10)

f = df[df["event_type"].isin(types) & (df["days"] == days)]
if f.empty:
    st.warning("Pick at least one event type.")
    st.stop()

bins = np.linspace(0, 1, n_bins + 1)
labels = [f"{a*100:.0f}-{b*100:.0f}%" for a, b in zip(bins[:-1], bins[1:])]
f = f.assign(bucket=pd.cut(f["price"], bins, labels=labels, include_lowest=True))
cal = (f.groupby("bucket", observed=True)
         .agg(contracts=("outcome", "size"), avg_price=("price", "mean"), hit_rate=("outcome", "mean"))
         .reset_index())
ece = (cal["contracts"] * (cal["avg_price"] - cal["hit_rate"]).abs()).sum() / cal["contracts"].sum()

c1, c2, c3 = st.columns(3)
c1.metric("Contracts", f"{len(f):,}")
c2.metric("Brier score", f"{f['sq_err'].mean():.3f}", help="0 = perfect, 0.25 = coin flip. Lower is better.")
c3.metric("Avg calibration error", f"{ece*100:.1f} pts", help="Average gap between price and how often it happened.")

left, right = st.columns([3, 2])
with left:
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], "--", color="gray", label="Perfect calibration")
    ax.plot(cal["avg_price"], cal["hit_rate"], alpha=0.5)
    ax.scatter(cal["avg_price"], cal["hit_rate"], s=cal["contracts"] * 2 + 10, alpha=0.7,
               label="Price bucket (bigger = more contracts)")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Market price (implied probability)")
    ax.set_ylabel("How often it actually happened")
    ax.legend(loc="upper left")
    st.pyplot(fig)
with right:
    st.subheader("By price bucket")
    st.dataframe(pd.DataFrame({
        "Bucket": cal["bucket"].astype(str),
        "Contracts": cal["contracts"],
        "Avg price (%)": (cal["avg_price"] * 100).round(1),
        "Happened (%)": (cal["hit_rate"] * 100).round(1),
    }), hide_index=True)

st.subheader("Accuracy by event type (Brier score)")
tbl = (df[df["event_type"].isin(types)]
       .pivot_table(index="event_type", columns="days", values="sq_err", aggfunc="mean").round(3))
tbl.columns = [f"{d} day(s) before close" for d in tbl.columns]
st.dataframe(tbl)

st.caption("Price = midpoint of the best bid and ask on the last daily snapshot before the cutoff, "
           "or the last trade if the spread was wider than 20 cents. Data from the Kalshi public API.")