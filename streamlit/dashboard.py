import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta

# ==============================
# CONFIG
# ==============================
FIREBASE_URL = "https://iot-sensors-pi-78113-default-rtdb.europe-west1.firebasedatabase.app/"
SENSOR_IDS = ["raspi_4b"]

METRIC_CONFIGS: Dict[str, Tuple[str, str]] = {
    "temperature_C": ("Temperature", "°C"),
    "humidity_pct": ("Humidity", "%"),
    "AQI": ("AQI", "Index"),
    "TVOC_ppb": ("TVOC", "ppb"),
    "eCO2_ppm": ("eCO₂ (ENS160)", "ppm"),
    "co2_ppm": ("CO₂ (MH-Z19)", "ppm"),
    "pressure_hPa": ("Pressure", "hPa"),
    "altitude_m": ("Altitude", "m"),
}
DEFAULT_FIELDS: List[str] = list(METRIC_CONFIGS.keys())

st.set_page_config(page_title="Srini's Airstation", layout="wide")
st.title("🌡️ Srini's Home Information")

# ==============================
# FUNCTIONS
# ==============================
@st.cache_data(ttl=30)
def fetch_data(sensor_id):
    url = f"{FIREBASE_URL}/{sensor_id}.json"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            st.error(f"Failed to fetch data from Firebase (Status: {res.status_code})")
            return pd.DataFrame()
        data = res.json() or {}
        records = []
        for batch_key, batch_list in data.items():
            if isinstance(batch_list, list):
                records.extend(batch_list)
            else:
                records.append(batch_list)

        df = pd.DataFrame(records)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"], format='mixed', errors='coerce')
            df.dropna(subset=['timestamp'], inplace=True)
            df = df.sort_values("timestamp")
            df['CO2_Primary'] = df.get('co2_ppm', pd.Series(dtype=float)).combine_first(df['eCO2_ppm'])
        return df

    except requests.exceptions.RequestException as e:
        st.error(f"Network Error: Could not connect to Firebase. {e}")
        return pd.DataFrame()

def normalize(series: pd.Series) -> pd.Series:
    series = pd.to_numeric(series, errors='coerce').dropna()
    if series.empty or series.nunique() <= 1:
        return series
    return (series - series.min()) / (series.max() - series.min()) * 100

# ==============================
# DASHBOARD
# ==============================
for sensor in SENSOR_IDS:
    st.markdown(f"## 📟 Source: `{sensor}`")
    df = fetch_data(sensor)
    
    if df.empty:
        st.warning("No data found yet or connection failed.")
        st.markdown("---")
        continue

    latest: Dict[str, Any] = df.iloc[-1].to_dict()

    # Metric display
    display_metrics: List[Tuple[str, float]] = []
    for key, (title, unit) in METRIC_CONFIGS.items():
        value = latest.get(key)
        if pd.notna(value) and isinstance(value, (int, float)):
            if key in ["eCO2_ppm", "co2_ppm", "AQI", "TVOC_ppb"]:
                formatted_value = f"{value:.0f}"
            else:
                formatted_value = f"{value:.2f}"
            display_metrics.append((title, formatted_value, unit))

    if display_metrics:
        cols = st.columns(min(len(display_metrics), 6))
        for i, (title, value, unit) in enumerate(display_metrics):
            if i < len(cols):
                cols[i].metric(title, f"{value} {unit}")
    else:
        st.info("No current numeric sensor readings available for display.")

    st.markdown("---")

    # ----------------------------------------------------
    # TIME RANGE SELECTOR  ✅ NEW FEATURE
    # ----------------------------------------------------
    time_options = ["1 hr", "6 hrs", "12 hrs", "24 hrs", "Yesterday", "Entire period"]
    selected_range = st.radio(
        "Select time range:", time_options, horizontal=True, index=2, key=f"time_{sensor}"
    )

    now = df["timestamp"].max()
    if selected_range == "1 hr":
        start_time = now - timedelta(hours=1)
        df = df[df["timestamp"] >= start_time]
    elif selected_range == "6 hrs":
        start_time = now - timedelta(hours=6)
        df = df[df["timestamp"] >= start_time]
    elif selected_range == "12 hrs":
        start_time = now - timedelta(hours=12)
        df = df[df["timestamp"] >= start_time]
    elif selected_range == "24 hrs":
        start_time = now - timedelta(hours=24)
        df = df[df["timestamp"] >= start_time]
    elif selected_range == "Yesterday":
        yesterday = (now - timedelta(days=1)).date()
        df = df[df["timestamp"].dt.date == yesterday]
    # "Entire period" keeps df as-is

    # ----------------------------------------------------
    # PLOTTING
    # ----------------------------------------------------
    available_fields = [f for f in DEFAULT_FIELDS if f in df.columns]
    if 'CO2_Primary' in df.columns and 'CO2_Primary' not in available_fields:
        available_fields.insert(0, 'CO2_Primary')
        
    selected_fields = st.multiselect(
        f"Select variables to display for {sensor}:",
        options=available_fields,
        default=[
            "temperature_C", 
            "humidity_pct", 
            "eCO2_ppm"
        ] if "eCO2_ppm" in available_fields else ["CO2_Primary"]
    )

    fig = go.Figure()
    for field in selected_fields:
        if pd.api.types.is_numeric_dtype(df[field]) and df[field].nunique() > 1:
            y_values = normalize(df[field])
            name_suffix = " (Normalized)"
        else:
            y_values = df[field]
            name_suffix = ""

        fig.add_trace(go.Scatter(
            x=df["timestamp"],
            y=y_values,
            mode="lines",
            name=field.replace('_', ' ').title() + name_suffix,
            hovertemplate=f"{field.replace('_', ' ')}: %{{y:.2f}}<br>%{{x|%H:%M:%S}}<extra></extra>"
        ))

    fig.update_layout(
        title=f"Combined Sensor Readings ({selected_range})",
        xaxis_title="Timestamp",
        yaxis_title="Normalized Scale (0–100)",
        hovermode="x unified",
        legend_title="Variables",
        height=400,
        template="plotly_white"
    )

    st.plotly_chart(fig, use_container_width=True)
    st.markdown("---")
