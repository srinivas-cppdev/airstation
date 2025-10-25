"""Capture periodic readings from BMP180, MH-Z19, and optional AHTx0 humidity sensor.

Features:
 - Robust error handling (per-sensor) so one failure doesn't stop logging
 - Fallback mock CO2 value if MH-Z19 read fails (optional)
 - Automatic CSV header creation
 - Derived dew point (simple approximate formula assuming fixed RH)
 - Configurable interval via INTERVAL_SECONDS constant
 - Timestamp in ISO 8601 format for easier parsing

CSV Columns:
 timestamp, temperature_C, pressure_hPa, altitude_m, humidity_percent, dew_point_C, co2_ppm, co2_source, errors

Notes:
 - Dew point uses Magnus formula when humidity available; otherwise a crude fallback approximation.
 - co2_source is 'sensor' or 'mock'.
 - errors contains semicolon-separated sensor error messages (empty if none).
 - Adjust bmp.sea_level_pressure to your local reference for accurate altitude.
 - Local time enabled by USE_LOCAL_TIME; set False to revert to UTC timestamps.
 - You must have freed /dev/serial0 from serial-getty for MH-Z19.
"""

import time
import csv
from datetime import datetime, timezone
import math
import board
import busio
import bmp180
from typing import Optional
import traceback

INTERVAL_SECONDS = 60
LOG_FILE = "env_log.csv"
ASSUMED_RH = 50  # % relative humidity fallback if humidity sensor absent
USE_LOCAL_TIME = True  # When True, log local (tz-aware) time instead of UTC
USE_MAGNUS_DEWPOINT = True  # Use Magnus formula for dew point if True
ENABLE_AHTX0 = True  # Attempt to read humidity via AHTx0 sensor

# State for humidity sensor
_aht = None  # AHTx0 instance (lazy init)
USE_CO2_MOCK_ON_FAIL = True

###############################################################################
# BMP180 Lazy/Resilient Initialization
###############################################################################
_bmp: Optional[bmp180.BMP180] = None
_i2c: Optional[busio.I2C] = None

def init_bmp(max_attempts: int = 3, delay: float = 2.0) -> Optional[bmp180.BMP180]:
    """Attempt to initialize BMP180 sensor with retries.

    Returns sensor instance or None if not found.
    Logs failures but does not raise, so the script can continue.
    """
    global _bmp, _i2c
    if _bmp is not None:
        return _bmp
    try:
        if _i2c is None:
            _i2c = busio.I2C(board.SCL, board.SDA)
    except Exception as e:  # Bus could be disabled or not exported yet
        print(f"[BMP180] Failed to acquire I2C bus: {e}")
        return None

    for attempt in range(1, max_attempts + 1):
        try:
            _bmp = bmp180.BMP180(_i2c)
            _bmp.sea_level_pressure = 1013.25  # hPa reference
            print(f"[BMP180] Initialized successfully on attempt {attempt}.")
            return _bmp
        except ValueError as ve:
            # Typical 'No I2C device at address: 0x77'
            print(f"[BMP180] Attempt {attempt}/{max_attempts}: {ve}")
        except Exception as e:
            print(f"[BMP180] Unexpected init error (attempt {attempt}/{max_attempts}): {e}")
            traceback.print_exc(limit=1)
        time.sleep(delay)

    print("[BMP180] Sensor not detected after retries. Will log blanks for BMP data.")
    return None

def read_bmp():
    """Return dict with BMP180 readings or raise exception if sensor present.

    If sensor is missing, raise RuntimeError to be caught by caller.
    """
    if _bmp is None:
        raise RuntimeError("BMP180 not initialized")
    return {
        "temperature_C": _bmp.temperature,
        "pressure_hPa": _bmp.pressure,
        "altitude_m": _bmp.altitude,
    }

def approximate_dew_point(temp_c: float, rh: float) -> float:
    """Return dew point in °C given temperature (°C) and relative humidity (%).

    Magnus formula implementation for better accuracy by default:
        gamma = (a * T)/(b + T) + ln(RH/100)
        dew = (b * gamma)/(a - gamma)

    Falls back to a simple linear approximation if math domain errors occur.
    """
    try:
        if USE_MAGNUS_DEWPOINT:
            if rh <= 0:
                return float('nan')
            a = 17.62
            b = 243.12
            gamma = (a * temp_c) / (b + temp_c) + math.log(rh/100.0)
            return (b * gamma) / (a - gamma)
    except Exception:
        # Fallback linear approximation (rough)
        return temp_c - ((100 - rh) / 5.0)
    # If Magnus disabled
    return temp_c - ((100 - rh) / 5.0)

def init_aht():
    """Lazy init for AHTx0 humidity sensor; returns instance or None if unavailable."""
    global _aht, _i2c
    if not ENABLE_AHTX0:
        return None
    if _aht is not None:
        return _aht
    try:
        if _i2c is None:
            _i2c = busio.I2C(board.SCL, board.SDA)
        from adafruit_ahtx0 import AHTx0  # type: ignore
        _aht = AHTx0(_i2c)
        print("[AHTx0] Humidity sensor initialized.")
        return _aht
    except Exception as e:
        print(f"[AHTx0] Init failed: {e}")
        return None

def read_mhz19():
    """Attempt to read MH-Z19 CO2 ppm; return dict with co2_ppm and source."""
    try:
        import os
        import mh_z19  # import locally to allow script execution even if missing
        # mh_z19.read() auto-detects serial; library version here doesn't accept serial_device kw.
        # Allow user to force device via env MHZ19_DEVICE using low-level helper if provided.
        forced = os.getenv("MHZ19_DEVICE")
        if forced and hasattr(mh_z19, "read"):
            # Library doesn't expose param, but may respect environment or internal config; try plain read.
            data = mh_z19.read()
        else:
            data = mh_z19.read()
        if isinstance(data, dict) and "co2" in data:
            return {"co2_ppm": data["co2"], "co2_source": "sensor"}
        raise ValueError(f"Unexpected mh_z19 response: {data!r}")
    except Exception as e:
        if USE_CO2_MOCK_ON_FAIL:
            # Deterministic-ish mock based on current minute
            minute = int(datetime.utcnow().strftime('%M'))
            mock_val = 450 + (minute % 30) * 10  # cycles within a plausible band
            return {"co2_ppm": mock_val, "co2_source": "mock", "error": str(e)}
        else:
            return {"co2_ppm": "", "co2_source": "error", "error": str(e)}

def ensure_csv_header(path: str):
    header = [
        "timestamp",
        "temperature_C",
        "pressure_hPa",
        "altitude_m",
        "humidity_percent",
        "dew_point_C",
        "co2_ppm",
        "co2_source",
        "errors",
    ]
    need_header = False
    try:
        with open(path, "r", newline="") as f:
            first = f.readline()
            if not first.strip():
                need_header = True
    except FileNotFoundError:
        need_header = True
    if need_header:
        with open(path, "a", newline="") as f:
            csv.writer(f).writerow(header)

ensure_csv_header(LOG_FILE)

print(f"Logging BMP180 + MH-Z19 data every {INTERVAL_SECONDS}s → {LOG_FILE}")
print("Press Ctrl+C to stop.\n")

# Attempt BMP init early (non-fatal if missing)
init_bmp()

def log_row(row):
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow(row)

# -------------------------------
# Create CSV with header (if new)
# -------------------------------
def format_console(ts, bmp_data, co2_ppm, co2_src, humidity, dew_point, errors):
    """Format a single console line, tolerating missing/invalid numeric values.

    Any non-numeric / empty string value is rendered as '---' with its unit.
    This prevents format exceptions like: Unknown format code 'f' for object of type 'str'.
    """

    def _fmt_num(v, unit, fmt=".1f"):
        # Accept int/float directly; attempt parse if non-empty string; else placeholder
        try:
            if isinstance(v, (int, float)):
                return f"{v:{fmt}}{unit}"
            if v in ("", None):
                return f"---{unit}"
            # Try to coerce (e.g., numeric string)
            coerced = float(v)
            return f"{coerced:{fmt}}{unit}"
        except Exception:
            return f"---{unit}"

    err_display = f" ERRORS={errors}" if errors else ""
    temp_str = _fmt_num(bmp_data.get('temperature_C'), "°C")
    pres_str = _fmt_num(bmp_data.get('pressure_hPa'), "hPa")
    alt_str = _fmt_num(bmp_data.get('altitude_m'), "m")
    hum_str = _fmt_num(humidity, "%")
    dew_str = _fmt_num(dew_point, "°C")
    co2_str = f"{co2_ppm}ppm" if isinstance(co2_ppm, (int, float)) else "---ppm"

    return f"{ts} | T={temp_str} P={pres_str} Alt={alt_str} RH={hum_str} Dew={dew_str} CO₂={co2_str} [{co2_src}]" + err_display

# -------------------------------
# Main logging loop
# -------------------------------
def scan_i2c_addresses(max_addr: int = 0x77):
    """Lightweight scan using current busio.I2C; returns list of detected addresses.

    Only used for diagnostics if BMP read fails repeatedly. Avoids external deps.
    """
    if _i2c is None:
        return []
    found = []
    for addr in range(0x03, max_addr + 1):  # Skip reserved lower addresses
        try:
            # Zero-length write strategy to probe; may raise OSError on NACK
            _i2c.writeto(addr, b"", stop=True)
            found.append(addr)
        except Exception:
            continue
    return found

while True:
    try:
        errors = []
        # BMP180
        try:
            bmp_data = read_bmp()
        except Exception as e:
            bmp_data = {"temperature_C": "", "pressure_hPa": "", "altitude_m": ""}
            errors.append(f"bmp180:{e}")
            # If sensor missing, attempt a one-off re-init and optionally scan
            if "not initialized" in str(e).lower():
                if init_bmp(max_attempts=1):
                    try:
                        bmp_data = read_bmp()
                        # Remove previous error if recovery succeeded
                        errors = [er for er in errors if not er.startswith("bmp180:")]
                    except Exception as e2:
                        errors.append(f"bmp180_recover:{e2}")
                else:
                    detected = scan_i2c_addresses()
                    if detected:
                        errors.append("i2c_scan:" + ",".join(f"0x{a:02X}" for a in detected))
                    else:
                        errors.append("i2c_scan:none")

        # Humidity (attempt AHTx0)
        humidity_rh = ""  # percent
        aht = init_aht()
        if aht is not None:
            try:
                humidity_rh = aht.relative_humidity  # already in %
            except Exception as e:
                errors.append(f"ahtx0:{e}")

        # Dew point (only if temp available)
        if isinstance(bmp_data.get("temperature_C"), (int, float)):
            rh_for_dp = humidity_rh if isinstance(humidity_rh, (int, float)) else ASSUMED_RH
            dew_point = approximate_dew_point(bmp_data["temperature_C"], rh_for_dp)
        else:
            dew_point = ""

        # MH-Z19
        co2_info = read_mhz19()
        if "error" in co2_info:
            errors.append(f"mh_z19:{co2_info['error']}")

        # Timestamp: local or UTC (always ISO 8601, tz-aware if local)
        if USE_LOCAL_TIME:
            timestamp = datetime.now().astimezone().isoformat()
        else:
            timestamp = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()

        log_row([
            timestamp,
            bmp_data["temperature_C"],
            bmp_data["pressure_hPa"],
            bmp_data["altitude_m"],
            humidity_rh,
            dew_point,
            co2_info.get("co2_ppm"),
            co2_info.get("co2_source"),
            ";".join(errors),
        ])

        # Safe console line (handles missing numeric values without raising formatting errors)
        print(
            format_console(
                timestamp,
                bmp_data,
                co2_info.get("co2_ppm"),
                co2_info.get("co2_source"),
                humidity_rh,
                dew_point,
                ";".join(errors),
            )
        )

        time.sleep(INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\nLogging stopped by user.")
        break
    except Exception as e:
        # Catch-all for unexpected top-level loop errors
        print(f"Fatal loop error: {e}")
        time.sleep(5)

