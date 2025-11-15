import streamlit as st
import pyrebase4 as pyrebase
from datetime import datetime, timedelta
import pandas as pd

# --------------------------------------------------------
# Firebase Configuration (same as your capture.py)
# --------------------------------------------------------
config = {
    "apiKey": "AIzaSyD-NL6Wc-udbLK9XCIGgJrcLnJlRaN8zK4",
    "authDomain": "iot-sensors-pi-78113.firebaseapp.com",
    "databaseURL": "https://iot-sensors-pi-78113-default-rtdb.europe-west1.firebasedatabase.app/",
    "projectId": "iot-sensors-pi-78113",
    "storageBucket": "iot-sensors-pi-78113.appspot.com",
    "messagingSenderId": "287682873861",
    "appId": "1:287682873861:web:78423629da9a6edf83d552",
}

# --------------------------------------------------------
# Initialize Pyrebase + DB
# --------------------------------------------------------
@st.cache_resource
def init_firebase():
    firebase = pyrebase.initialize_app(config)
    return firebase.database()

db = init_firebase()


# --------------------------------------------------------
# Fetch ONLY last 1 day of sensor readings
# --------------------------------------------------------
@st.cache_data(ttl=60)
def fetch_last_day():
    cutoff_ts = int((datetime.utcnow() - timedelta(days=1)).timestamp())

    # Query only where timestamp >= cutoff
    snapshot = (
        db.child("airstation")
        .order_by_child("timestamp")
        .start_at(cutoff_ts)
        .get()
    )

    if not snapshot.each():
        return pd.DataFrame()

    rows = []
    for item in snapshot.each():
        data = item.val()
        if "timestamp" in data:
            data["timestamp"] = datetime.utcfromtimestamp(data["timestamp"])
            rows.append(data)

    df = pd.DataFrame(rows)
    df = df.sort_values("timestamp")
    return df


# --------------------------------------------------------
# Streamlit UI
# --------------------------------------------------------
st.set_page_config(page_title="AirStation Dashboard", layout="wide")
st.title("AirStation Dashboard (Optimized – Pyrebase)")

st.markdown(
    """
    **This dashboard loads only the last 24 hours of sensor data.**  
    Auto-refresh disabled to prevent Firebase download spikes.  
    Click refresh anytime to update data.
    """
)

# Manual refresh
if st.button("🔄 Refresh Latest Data"):
    st.cache_data.clear()
    df = fetch_last_day()
else:
    df = fetch_last_day()

# --------------------------------------------------------
# Display Data
# --------------------------------------------------------
if df.empty:
    st.warning("No sensor data found in the last 24 hours.")
else:
    st.success(f"Loaded **{len(df)}** readings from the last 24 hours.")
    st.dataframe(df, use_container_width=True)

    st.header("Charts")

    numeric_cols = [
        c for c in df.columns
        if c not in ("timestamp", "device_id")
    ]

    for col in numeric_cols:
        st.subheader(col)
        st.line_chart(df.set_index("timestamp")[col], height=250)
