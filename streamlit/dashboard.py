import streamlit as st
import pyrebase
import pandas as pd
import time
from datetime import datetime

# --- 1. FIREBASE INITIALIZATION & SECRETS ---
# Reads secrets securely from Streamlit Cloud's secrets manager

try:
    # 1. Read the configuration you saved in Streamlit Cloud under [firebase]
    firebase_config = dict(st.secrets['firebase'])
    
    # 2. Initialize the Firebase App
    firebase = pyrebase.initialize_app(firebase_config)
    
    # 3. Get the Realtime Database reference
    db = firebase.database()

except KeyError:
    st.error("Error: Firebase configuration not found in Streamlit Secrets. Please ensure you have a [firebase] section.")
    st.stop()
except Exception as e:
    st.error(f"Failed to initialize Firebase: {e}")
    st.stop()


# --- 2. OPTIMIZED DATA FETCHING FUNCTION ---
# Uses caching and server-side limiting to reduce data download/load time

@st.cache_data(ttl=60) # Cache data for 60 seconds (1 minute)
def load_data(data_path="airstation_readings", limit=200):
    """
    Fetches the latest 'limit' records from Firebase using server-side ordering/limiting.
    """
    st.info(f"Fetching data from Firebase (limited to last {limit} records)...")
    try:
        # Optimization: Use limit_to_last() for server-side filtering
        data = (
            db.child(data_path)
            .order_by_key()  # Orders by the time-based push ID
            .limit_to_last(limit)
            .get()
            .val()
        )
        
        if not data:
            return pd.DataFrame()
            
        # Convert dictionary of records (Firebase Push IDs are keys) into a DataFrame
        df = pd.DataFrame.from_dict(data, orient='index')
        
        # --- Data Cleaning and Formatting (Adjust as needed for your keys) ---
        
        # Convert all relevant columns to numeric, coercing errors to NaN
        numeric_cols = ['pm25', 'pm10', 'temp', 'humidity'] # Adjust this list
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # If your data has a 'timestamp' column, convert it to datetime
        if 'timestamp' in df.columns:
             # Assuming timestamp is stored as seconds since epoch (unit='s')
             df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', errors='coerce')
             df = df.sort_values('timestamp').set_index('timestamp')
        
        return df

    except Exception as e:
        st.error(f"Error loading data from Firebase: {e}")
        return pd.DataFrame()


# --- 3. STREAMLIT DASHBOARD LAYOUT ---

st.set_page_config(
    page_title="AirStation Realtime Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("AirStation Realtime Data Dashboard 💨")

# Sidebar for controls
with st.sidebar:
    st.header("Data Controls")
    
    # User can select how many data points to view
    data_limit = st.slider(
        "Recent data points to display:",
        min_value=50,
        max_value=1000,
        value=200,
        step=50
    )
    
    # Button to clear the cache and force a new data download
    if st.button("Force Data Refresh 🔄"):
        st.cache_data.clear()
        st.experimental_rerun()
    
    st.markdown("---")
    st.markdown("Data is automatically refreshed every **60 seconds**.")


# Main content area
data_path = "airstation_readings" # Verify this is your actual Firebase Realtime DB node name
df_data = load_data(data_path, data_limit)

if df_data.empty:
    st.warning("No data found or fetching failed. Check your Firebase path and data structure.")
else:
    # Display the latest snapshot
    latest_reading = df_data.iloc[-1].fillna('N/A')
    
    st.subheader("Latest Readings")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("PM2.5", f"{latest_reading.get('pm25', 0):.2f} µg/m³")
    col2.metric("PM10", f"{latest_reading.get('pm10', 0):.2f} µg/m³")
    col3.metric("Temperature", f"{latest_reading.get('temp', 0):.1f} °C")
    col4.metric("Humidity", f"{latest_reading.get('humidity', 0):.1f} %")

    st.markdown("---")
    st.subheader(f"Time-series Trends (Last {len(df_data)} points)")
    
    # Create a line chart for PM values
    chart_cols = [col for col in ['pm25', 'pm10'] if col in df_data.columns]
    if chart_cols:
        st.line_chart(df_data[chart_cols])
    
    # Display the raw data table
    st.markdown("---")
    st.subheader(f"Raw Data Table")
    st.dataframe(df_data, use_container_width=True)
