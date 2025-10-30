# ---------------------------------------------------------------
# dashboard.py — Streamlit Dashboard for Air Quality Visualization
# Features:
# - Auto-refresh every 30s
# - Selectable time range
# - Actual values on hover
# - Default metrics: Temp, Humidity, CO₂ Primary
# - Mobile-friendly layout
# - Latest readings with visual blink + last updated time
# ---------------------------------------------------------------

import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# ---------------------------------------------------------------
# PAGE CONFIGURATION
# ---------------------------------------------------------------
st.set_page_config(
    page_title="Air Quality Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.title("🌤️ Air Quality Monitoring Dashboard")
st.caption("Interactive visualization of temperature, humidity, and CO₂ trends over time")

# ---------------------------------------------------------------
# AUTO-REFRESH (every 30 seconds)
# ---------------------------------------------------------------
st_autorefresh(interval=30 * 1000, key="data_refresh")

# ---------------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------------
# TODO: Replace this section with your actual API or CSV data loading logic.
# Example:
# response = requests.get("https://api.example.com/airdata")
# df = pd.DataFrame(response.json())

# --- Demo Data (Remove when live data available) ---
date_rng = pd.date_range(end=datetime.now(), periods=500, freq="5min")
df = pd.DataFrame({
    "timestamp": date_rng,
    "temperature": 25 + 3 * np.sin(np.linspace(0, 10, len(date_rng))),
    "humidity": 60 + 10 * np.cos(np.linspace(0, 8, len(date_rng))),
    "co2_primary": 400 + 20 * np.random.randn(len(date_rng)),
})
# ---------------------------------------------------------------

df["timestamp"] = pd.to_datetime(df["timestamp"])
df = df.sort_values("timestamp")

# ---------------------------------------------------------------
# SIDEBAR CONTROLS
# ---------------------------------------------------------------
st.sidebar.header("🔧 Controls")

# --- Time Range Selection ---
st.sidebar.subheader("Time Range")
time_range = st.sidebar.selectbox(
    "Show data for:",
    ("Last 1 Hour", "Last 12 Hours", "Last 24 Hours", "Yesterday", "Entire Period"),
    index=1  # Default = Last 12 Hours
)

now = df["timestamp"].max()
if time_range == "Last 1 Hour":
    start_time = now - timedelta(hours=1)
elif time_range == "Last 12 Hours":
    start_time = now - timedelta(hours=12)
elif time_range == "Last 24 Hours":
    start_time = now - timedelta(hours=24)
elif time_range == "Yesterday":
    start_time = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0)
    now = start_time + timedelta(days=1)
else:
    start_time = df["timestamp"].min()

df = df[(df["timestamp"] >= start_time) & (df["timestamp"] <= now)]

# --- Metric Selection ---
metrics = st.sidebar.multiselect(
    "Select parameters to display:",
    options=["temperature", "humidity", "co2_primary"],
    default=["temperature", "humidity", "co2_primary"]
)

# ---------------------------------------------------------------
# NORMALIZATION (for chart scale only)
# ---------------------------------------------------------------
df_norm = df.copy()
for col in metrics:
    col_norm = f"{col}_norm"
    df_norm[col_norm] = (df[col] - df[col].min()) / (df[col].max() - df[col].min())

# ---------------------------------------------------------------
# CHART
# ---------------------------------------------------------------
plot_cols = [f"{col}_norm" for col in metrics]
fig = px.line(
    df_norm,
    x="timestamp",
    y=plot_cols,
    labels={"value": "Normalized Value", "timestamp": "Time"},
    title="📊 Air Quality Trends",
    hover_data={col: ':.2f' for col in metrics}
)

fig.update_layout(
    autosize=True,
    hovermode="x unified",
    margin=dict(l=10, r=10, t=50, b=20),
    legend_title_text="Parameters",
    template="plotly_white",
)
fig.update_traces(line=dict(width=3))

st.plotly_chart(fig, use_container_width=True, responsive=True)

# ---------------------------------------------------------------
# LATEST READINGS (with blink + timestamp)
# ---------------------------------------------------------------
latest = df.iloc[-1]

# CSS for blink effect
st.markdown("""
    <style>
    .blink {
        animation: blinker 1.2s ease-in-out 2;
        color: #2E86AB;
        font-weight: bold;
        font-size: 1.1em;
    }
    @keyframes blinker {
        50% { opacity: 0.4; }
    }
    </style>
""", unsafe_allow_html=True)

# Display current readings
st.markdown("### 🌡️ Latest Sensor Readings (auto-updated every 30 s)")
cols = st.columns(len(metrics))
for i, col in enumerate(metrics):
    value = f"{latest[col]:.2f}"
    cols[i].markdown(
        f"<div class='blink'>{col.capitalize()}: {value}</div>",
        unsafe_allow_html=True
    )

# Show last updated time
last_update = latest["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
st.markdown(f"<p style='text-align:right; font-size:0.9em; color:gray;'>⏱️ Last updated at: {last_update}</p>", unsafe_allow_html=True)

# ---------------------------------------------------------------
# DATA TABLE (optional)
# ---------------------------------------------------------------
with st.expander("📋 View Recent Data"):
    st.dataframe(df.tail(50), use_container_width=True)

# ---------------------------------------------------------------
# FOOTER
# ---------------------------------------------------------------
st.markdown(
    """
    <hr>
    <center>
    <small>Dashboard auto-refreshes every 30 seconds — built with ❤️ using <b>Streamlit</b> and <b>Plotly</b>.</small>
    </center>
    """,
    unsafe_allow_html=True
)
