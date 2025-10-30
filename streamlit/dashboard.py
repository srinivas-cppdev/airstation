# ---------------------------------------------------------------
# dashboard.py — Streamlit Air Quality Dashboard (Final, Fixed)
# ---------------------------------------------------------------

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# ---------------------------------------------------------------
# PAGE CONFIGURATION
# ---------------------------------------------------------------
st.set_page_config(
    page_title="Air Quality Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("🌤️ Air Quality Monitoring Dashboard")
st.caption("Interactive visualization of temperature, humidity, CO₂, AQI and more")

# ---------------------------------------------------------------
# AUTO-REFRESH (every 30 seconds)
# ---------------------------------------------------------------
st_autorefresh(interval=30 * 1000, key="data_refresh")

# ---------------------------------------------------------------
# LOAD DATA  (Replace with your live source)
# ---------------------------------------------------------------
date_rng = pd.date_range(end=datetime.now(), periods=500, freq="5min")
df = pd.DataFrame({
    "timestamp": date_rng,
    "temperature": 25 + 3 * np.sin(np.linspace(0, 10, len(date_rng))),
    "humidity": 60 + 10 * np.cos(np.linspace(0, 8, len(date_rng))),
    "co2_primary": 400 + 20 * np.random.randn(len(date_rng)),
    "AQI": 50 + 10 * np.sin(np.linspace(0, 6, len(date_rng))),
    "eco2_ppm": 410 + 15 * np.cos(np.linspace(0, 5, len(date_rng)))
})
df["timestamp"] = pd.to_datetime(df["timestamp"])
df = df.sort_values("timestamp")

# ---------------------------------------------------------------
# SIDEBAR CONTROLS
# ---------------------------------------------------------------
st.sidebar.header("🔧 Controls")

# --- Time Range Selection ---
time_range = st.sidebar.selectbox(
    "Show data for:",
    ("Last 1 Hour", "Last 12 Hours", "Last 24 Hours", "Yesterday", "Entire Period"),
    index=1,
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

# --- Metric Selection (Dynamic) ---
numeric_cols = [
    col for col in df.columns
    if pd.api.types.is_numeric_dtype(df[col]) and col.lower() != "timestamp"
]

metrics = st.sidebar.multiselect(
    "Select parameters to display:",
    options=numeric_cols,
    default=[m for m in ["temperature", "humidity", "co2_primary"] if m in numeric_cols][:3]
        or numeric_cols[:3],
)

# ---------------------------------------------------------------
# NORMALIZE for visual comparison (but keep actual hover values)
# ---------------------------------------------------------------
df_norm = df.copy()
for col in metrics:
    df_norm[f"{col}_norm"] = (df[col] - df[col].min()) / (df[col].max() - df[col].min())

# ---------------------------------------------------------------
# PLOT (using Plotly Graph Objects for full hover control)
# ---------------------------------------------------------------
fig = go.Figure()

for col in metrics:
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df_norm[f"{col}_norm"],
            mode="lines",
            name=col.capitalize(),
            line=dict(width=3),
            hovertemplate=(
                f"<b>{col.capitalize()}</b><br>"
                "Time: %{x|%Y-%m-%d %H:%M:%S}<br>"
                f"Value: %{customdata:.2f}<extra></extra>"
            ),
            customdata=df[col],  # actual (un-normalized) values
        )
    )

fig.update_layout(
    title="📊 Air Quality Trends",
    xaxis_title="Time",
    yaxis_title="Normalized Scale (0–1)",
    hovermode="closest",  # independent hover tooltips
    margin=dict(l=10, r=10, t=50, b=20),
    legend_title_text="Parameters",
    template="plotly_white",
    autosize=True,
)

st.plotly_chart(
    fig,
    use_container_width=True,
    config={"displayModeBar": True, "scrollZoom": True, "responsive": True},
)

# ---------------------------------------------------------------
# LATEST READINGS (Blink + Timestamp)
# ---------------------------------------------------------------
latest = df.iloc[-1]

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

st.markdown("### 🌡️ Latest Sensor Readings (auto-updated every 30 s)")
cols = st.columns(len(metrics))
for i, col in enumerate(metrics):
    cols[i].markdown(f"<div class='blink'>{col.capitalize()}: {latest[col]:.2f}</div>",
                     unsafe_allow_html=True)

last_update = latest["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
st.markdown(
    f"<p style='text-align:right; font-size:0.9em; color:gray;'>⏱️ Last updated at: {last_update}</p>",
    unsafe_allow_html=True,
)

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
    unsafe_allow_html=True,
)
