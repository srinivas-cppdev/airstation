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
    template="plotly_white_
