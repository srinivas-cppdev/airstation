import os
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ---------- CONFIG ----------
st.set_page_config(page_title="AirStation Dashboard", layout="wide")
LOG_DIR = os.path.expanduser("~/airstation/logs")
REFRESH_INTERVAL = 30  # seconds

# ---------- AUTO REFRESH ----------
st_autorefresh = st.experimental_rerun  # not used
st_autorefresh = st.autorefresh(interval=REFRESH_INTERVAL * 1000, limit=None, key="air_refresh")

# ---------- LOAD DATA ----------
@st.cache_data(ttl=REFRESH_INTERVAL)
def load_data() -> pd.DataFrame:
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    paths = [
        os.path.join(LOG_DIR, f"{yesterday}.csv"),
        os.path.join(LOG_DIR, f"{today}.csv"),
    ]

    dfs = []
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            df = pd.read_csv(p, on_bad_lines="skip")
            if "timestamp" not in df.columns:
                continue
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df = df.dropna(subset=["timestamp"])
            dfs.append(df)
        except Exception as e:
            st.warning(f"⚠️ Could not read {p}: {e}")

    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs).sort_values("timestamp")
    cutoff = datetime.now() - timedelta(hours=24)
    df = df[df["timestamp"] >= cutoff].reset_index(drop=True)
    return df


df = load_data()

st.title("🌫️ AirStation Dashboard")
st.caption(f"Auto-refreshing every {REFRESH_INTERVAL}s — showing last 24 hours of data")

if df.empty:
    st.error("No recent CSV logs found in ~/airstation/logs/")
    st.stop()

# ---------- METRIC CARDS ----------
latest = df.iloc[-1].to_dict()

def metric_card(col, label, key, unit=""):
    val = latest.get(key)
    if val is None:
        col.metric(label, "—")
    else:
        col.metric(label, f"{val:.1f} {unit}")

c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
metric_card(c1, "Temperature (°C)", "temperature_C", "°C")
metric_card(c2, "Humidity (%)", "humidity_pct", "%")
metric_card(c3, "CO₂ (MH-Z19)", "co2_ppm", "ppm")
metric_card(c4, "eCO₂ (ENS160)", "eCO2_ppm", "ppm")
metric_card(c5, "Pressure (hPa)", "pressure_hPa", "hPa")
metric_card(c6, "TVOC (ppb)", "TVOC_ppb", "ppb")
metric_card(c7, "AQI", "AQI", "")

st.divider()

# ---------- TIME-SERIES CHART ----------
param_map = {
    "temperature_C": ("Temperature (°C)", "#ff7f0e"),
    "humidity_pct": ("Humidity (%)", "#1f77b4"),
    "co2_ppm": ("CO₂ (MH-Z19) (ppm)", "#2ca02c"),
    "eCO2_ppm": ("eCO₂ (ENS160) (ppm)", "#17becf"),
    "pressure_hPa": ("Pressure (hPa)", "#9467bd"),
    "TVOC_ppb": ("TVOC (ppb)", "#8c564b"),
    "AQI": ("AQI", "#e377c2"),
}

visible = st.multiselect(
    "Select parameters to plot",
    list(param_map.keys()),
    default=["temperature_C", "humidity_pct", "co2_ppm"],
    format_func=lambda k: param_map[k][0],
)

fig = go.Figure()
for k in visible:
    if k in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df[k],
                mode="lines",
                name=param_map[k][0],
                line=dict(color=param_map[k][1]),
            )
        )

fig.update_layout(
    title="Environmental Trends (Last 24 h)",
    xaxis_title="Time",
    yaxis_title="Value",
    template="plotly_dark",
    height=500,
    legend=dict(orientation="h", y=-0.2),
    margin=dict(t=60, l=50, r=20, b=80),
)

st.plotly_chart(fig, use_container_width=True)

# ---------- DATA TABLE ----------
st.subheader("Recent Data (last 100 rows)")
st.dataframe(df.tail(100).sort_values("timestamp", ascending=False))

# ---------- FOOTER ----------
st.caption("Data source: ~/airstation/logs/*.csv — refreshed every 30 s")
