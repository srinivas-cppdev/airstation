import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime, timedelta
import pandas as pd

# --------------------------------------------------------
# Firebase Configuration (from your GitHub)
# --------------------------------------------------------
FIREBASE_URL = "https://iot-sensors-pi-78113-default-rtdb.europe-west1.firebasedatabase.app/"

SERVICE_ACCOUNT_FILE = "serviceAccountKey.json"   # ensure this is in your folder


# --------------------------------------------------------
# Firebase Initialization (Cached to avoid repeated sessions)
# --------------------------------------------------------
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_URL})
    return db.reference("/airstation")

airstation_ref = init_firebase()


# --------------------------------------------------------
# Fetch ONLY last 1 day of sensor readings (cached 60 sec)
# --------------------------------------------------------
@st.cache_data(ttl=60)
def fetch_last_day():
    """
    Fetches only last 24 hours of data based on the timestamp field
    stored inside each pushed record from capture.py.
    """
    cutoff_ts = int((datetime.utcnow() - timedelta(days=1)).timestamp())

    # Firebase query: /airstation where child "timestamp" >= cutoff
    snapshot = (
        airstation_ref
        .order_by_child("timestamp")
        .start_at(cutoff_ts)
        .get()
    )

    if not snapshot:
        return pd.DataFrame()

    rows = []
    for key, record in snapshot.items():
        if "timestamp" not in record:
            continue
        r = record.copy()
        # Convert UNIX timestamp (seconds) → Python datetime
        r["timestamp"] = datetime.utcfromtimestamp(r["timestamp"])
        rows.append(r)

    df = pd.DataFrame(rows)

    if not df.empty:
        df = df.sort_values("timestamp")

    return df


# --------------------------------------------------------
# Streamlit UI
# --------------------------------------------------------
st.set_page_config(page_title="AirStation Dashboard", layout="wide")
st.title("AirStation Dashboard (Optimized for Low Firebase Usage)")

st.markdown(
    """
    **This dashboard loads only the last 24 hours of sensor data.**  
    To avoid high Firebase download costs, auto-refresh is disabled.  
    Press the button below whenever you want updated readings.
    """
)

# Refresh button (clears cached data and reloads)
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
    st.success(f"Loaded **{len(df)}** records from the last 1 day.")

    st.dataframe(df, use_container_width=True)

    # --------------------------------------------------------
    # Charts
    # --------------------------------------------------------
    numeric_cols = [
        col for col in df.columns
        if col not in ("timestamp", "device_id")
    ]

    st.header("Charts")

    for col in numeric_cols:
        st.subheader(col)
        st.line_chart(df.set_index("timestamp")[col], height=250)
