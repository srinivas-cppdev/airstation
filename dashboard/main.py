from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import pandas as pd
from datetime import datetime, timedelta
import os

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

LOG_DIR = os.path.expanduser("~/airstation/logs")

def get_latest_csv():
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(LOG_DIR, f"{today}.csv")

LOG_DIR = os.path.expanduser("~/airstation/logs")

def load_data():
    """Load data from today's and yesterday's CSV files, skipping malformed lines."""

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    paths = [
        os.path.join(LOG_DIR, f"{yesterday}.csv"),
        os.path.join(LOG_DIR, f"{today}.csv")
    ]

    dfs = []

    for p in paths:
        if not os.path.exists(p):
            continue

        try:
            # Skip malformed rows automatically
            df = pd.read_csv(p, on_bad_lines='skip')

            # Ensure timestamp column is valid datetime
            if "timestamp" not in df.columns:
                print(f"⚠️ Skipping file {p}: no timestamp column.")
                continue

            df["timestamp"] = pd.to_datetime(df["timestamp"], errors='coerce')
            df = df.dropna(subset=["timestamp"])  # drop rows with invalid timestamps

            dfs.append(df)

        except Exception as e:
            print(f"⚠️ Error reading {p}: {e}")

    if not dfs:
        return pd.DataFrame()

    # Merge and sort combined data
    df = pd.concat(dfs).sort_values("timestamp")

    # Filter to last 24 hours
    cutoff = datetime.now() - timedelta(hours=24)
    df = df[df["timestamp"] >= cutoff].reset_index(drop=True)

    return df

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    df = load_data()
    if df.empty:
        return templates.TemplateResponse("index.html", {"request": request, "latest": {}, "data": []})
    latest = df.iloc[-1].to_dict()
    data = df.tail(100).to_dict(orient="records")
    return templates.TemplateResponse("index.html", {"request": request, "latest": latest, "data": data})

@app.get("/api/latest")
async def api_latest():
    df = load_data()
    if df.empty:
        return JSONResponse({})
    latest = df.iloc[-1].to_dict()
    # Convert timestamp to string
    if isinstance(latest.get("timestamp"), pd.Timestamp):
        latest["timestamp"] = latest["timestamp"].isoformat()
    return JSONResponse(latest)

@app.get("/api/data")
async def api_data():
    df = load_data()
    if df.empty:
        return JSONResponse([])
    # Convert all timestamps to string
    df["timestamp"] = df["timestamp"].astype(str)
    return JSONResponse(df.to_dict(orient="records"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8888, reload=True)

