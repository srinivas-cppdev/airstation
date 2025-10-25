import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from typing import List, Dict, Any, Tuple

# ==============================
# CONFIG
# ==============================
# Synchronized with FIREBASE_BASE_URL from log_uploader.py
FIREBASE_URL = "https://iot-sensors-pi-78113-default-rtdb.europe-west1.firebasedatabase.app/" 
# Synchronized with SENSOR_ID from log_uploader.py
SENSOR_IDS = ["raspi_4b"]  

# Configuration for how to display each metric (Title and Unit)
METRIC_CONFIGS: Dict[str, Tuple[str, str]] = {
    "temperature_C": ("Temperature", "°C"),
    "humidity_pct": ("Humidity", "%"),
    "AQI": ("AQI", "Index"),
    "TVOC_ppb": ("TVOC", "ppb"),
    "eCO2_ppm": ("eCO₂ (ENS160)", "ppm"), # Renamed title to clarify
    "co2_ppm": ("CO₂ (MH-Z19)", "ppm"),
    "pressure_hPa": ("Pressure", "hPa"),
    "altitude_m": ("Altitude", "m"),
}

# Fields that should be included in the multiselect for plotting
DEFAULT_FIELDS: List[str] = list(METRIC_CONFIGS.keys())

st.set_page_config(page_title="Srini's Airstation", layout="wide")
st.title("🌡️ Srini's Home Information")

# ==============================
# FUNCTIONS
# ==============================
@st.cache_data(ttl=30)
def fetch_data(sensor_id):
    """Fetches and processes all sensor data for a given sensor ID."""
    url = f"{FIREBASE_URL}/{sensor_id}.json"
    
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            st.error(f"Failed to fetch data from Firebase (Status: {res.status_code})")
            return pd.DataFrame()
        
        data = res.json() or {}
        
        records = []
        # Flatten the batches back into a single list of records
        for batch_key, batch_list in data.items():
            if isinstance(batch_list, list):
                records.extend(batch_list)
            else:
                records.append(batch_list)


        df = pd.DataFrame(records)
        
        if not df.empty:
            # FIX: Use format='mixed' and errors='coerce' for robust timestamp parsing.
            df["timestamp"] = pd.to_datetime(df["timestamp"], format='mixed', errors='coerce')
            df.dropna(subset=['timestamp'], inplace=True)
            
            df = df.sort_values("timestamp")
            
            # --- FIXED: Now prioritizes co2_ppm (MH-Z19) over eCO2_ppm (ENS160) ---
            df['CO2_Primary'] = df.get('co2_ppm', pd.Series(dtype=float)).combine_first(df['eCO2_ppm'])
            
        return df

    except requests.exceptions.RequestException as e:
        st.error(f"Network Error: Could not connect to Firebase. {e}")
        return pd.DataFrame()

def normalize(series: pd.Series) -> pd.Series:
    """Simple normalization for visual comparability."""
    series = pd.to_numeric(series, errors='coerce').dropna()
    if series.empty or series.nunique() <= 1:
        return series
    # Normalize to 0-100 range
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

    # Latest values
    latest: Dict[str, Any] = df.iloc[-1].to_dict()
    
    # ----------------------------------------------------
    # DYNAMIC METRIC DISPLAY (NEW)
    # ----------------------------------------------------
    
    # Identify all numeric, relevant metrics from the latest reading
    display_metrics: List[Tuple[str, float]] = []
    
    for key, (title, unit) in METRIC_CONFIGS.items():
        value = latest.get(key)
        
        # Check if value is not missing (NaN) and is numeric
        if pd.notna(value) and isinstance(value, (int, float)):
            # Special formatting for certain values
            if key in ["eCO2_ppm", "co2_ppm", "AQI", "TVOC_ppb"]:
                formatted_value = f"{value:.0f}"
            else:
                formatted_value = f"{value:.2f}"

            display_metrics.append((title, formatted_value, unit))

    if display_metrics:
        # Create columns based on the number of available metrics (up to 6 columns)
        num_metrics = len(display_metrics)
        cols = st.columns(min(num_metrics, 6))
        
        for i, (title, value, unit) in enumerate(display_metrics):
            if i < len(cols):
                cols[i].metric(title, f"{value} {unit}")
    else:
        st.info("No current numeric sensor readings available for display.")

    st.markdown("---")
    
    # ----------------------------------------------------
    # PLOTTING LOGIC
    # ----------------------------------------------------
    
    available_fields = [f for f in DEFAULT_FIELDS if f in df.columns]
    
    # Add the primary CO2 metric if it was created
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
        title=f"Combined Sensor Readings (Normalized for comparison)",
        xaxis_title="Timestamp",
        yaxis_title="Normalized Scale (0–100)",
        hovermode="x unified",
        legend_title="Variables",
        height=400,
        template="plotly_white"
    )

    st.plotly_chart(fig, use_container_width=True)
    st.markdown("---")

