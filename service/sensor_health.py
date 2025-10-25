"""Quick health check for connected sensors (BMP180, ENS160, MH-Z19) and I2C bus.

Run: python sensor_health.py
Outputs JSON with detected addresses, per-sensor status, and any errors.
"""
import json
import time
from datetime import datetime

import board
import busio

RESULT = {
    "timestamp": datetime.utcnow().isoformat(),
    "i2c_addresses": [],
    "bmp180": {},
    "ens160": {},
    "mh_z19": {},
    "errors": []
}

try:
    i2c = busio.I2C(board.SCL, board.SDA)
except Exception as e:
    RESULT["errors"].append(f"i2c_bus:{e}")
    print(json.dumps(RESULT, indent=2))
    raise SystemExit(1)

# Scan bus
while not i2c.try_lock():
    time.sleep(0.05)
try:
    RESULT["i2c_addresses"] = [f"0x{addr:02X}" for addr in i2c.scan()]
finally:
    i2c.unlock()

# BMP180
try:
    import bmp180
    bmp = bmp180.BMP180(i2c)
    bmp.sea_level_pressure = 1013.25
    RESULT["bmp180"] = {
        "present": True,
        "temperature_C": round(bmp.temperature, 2),
        "pressure_hPa": round(bmp.pressure, 2),
        "altitude_m": round(bmp.altitude, 2)
    }
except Exception as e:
    RESULT["bmp180"] = {"present": False, "error": str(e)}

# ENS160 (Air quality / TVOC) optional
try:
    import adafruit_ens160
    ens = adafruit_ens160.ENS160(i2c, 0x52)
    RESULT["ens160"] = {
        "present": True,
        "AQI": getattr(ens, "AQI", None),
        "TVOC_ppb": getattr(ens, "TVOC", None),
        "eCO2_ppm": getattr(ens, "eCO2", None),
        "temperature_C": getattr(ens, "temperature", None),
        "humidity_percent": getattr(ens, "relative_humidity", None)
    }
except Exception as e:
    RESULT["ens160"] = {"present": False, "error": str(e)}

# MH-Z19 CO2
try:
    import mh_z19
    data = mh_z19.read()
    if isinstance(data, dict) and "co2" in data:
        RESULT["mh_z19"] = {"present": True, "co2_ppm": data["co2"]}
    else:
        RESULT["mh_z19"] = {"present": True, "raw": data}
except Exception as e:
    RESULT["mh_z19"] = {"present": False, "error": str(e)}

print(json.dumps(RESULT, indent=2))
