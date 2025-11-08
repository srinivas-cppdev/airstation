#!/usr/bin/env python3
"""
capture.py — Fault-tolerant multi-sensor logger for AirStation
--------------------------------------------------------------
Collects data from multiple I2C sensors:
  - AHT21: temperature, humidity
  - ENS160: AQI, eCO2, TVOC, raw T/H
  - BMP180: pressure, altitude
  - MH-Z19: CO2 (UART)
Displays summary on OLED (SSD1306 128x32)
Logs data to CSV and pushes it in real-time to Firebase RTDB.

Author: Nivas
"""

import os, csv, time, datetime, json, traceback
from pathlib import Path
import board, busio
from typing import Dict, Any, Optional

# Sensor modules
import bmp180
import mh_z19

# Adafruit CircuitPython drivers
from adafruit_ens160 import ENS160
from adafruit_ahtx0 import AHTx0
from adafruit_ssd1306 import SSD1306_I2C

from PIL import Image, ImageDraw, ImageFont
import requests


# ---------------- CONFIGURATION ----------------
LOG_INTERVAL = 30  # seconds
CSV_DIR = "/home/nivas/airstation/logs"

# --- Firebase Real-time Configuration ---
FIREBASE_URL = "https://iot-sensors-pi-78113-default-rtdb.europe-west1.firebasedatabase.app/"
SENSOR_ID = "raspi_4b"
USE_FIREBASE = True
# -----------------------------------------------

I2C_BUS_ID = 1
ADDR_AHT21 = 0x38
ADDR_ENS160 = 0x52
ADDR_BMP180 = 0x77
ADDR_OLED = 0x3C
# -----------------------------------------------


# ------------------------------------------------
# Firebase Push
# ------------------------------------------------
def send_realtime_data(data: Dict[str, Any]) -> None:
    """Send one record to Firebase Realtime Database."""
    if not USE_FIREBASE:
        return
    url = f"{FIREBASE_URL}/{SENSOR_ID}.json"
    try:
        response = requests.post(url, json=data, timeout=5)
        response.raise_for_status()
        if response.status_code == 200:
            print(f"✅ Firebase Success: Data posted for {SENSOR_ID}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Firebase Error posting data: {e}")


# ------------------------------------------------
# Sensor Classes
# ------------------------------------------------
class AHT21Sensor:
    def __init__(self, i2c_bus):
        try:
            self.sensor = AHTx0(i2c_bus, address=ADDR_AHT21)
            self.present = True
        except Exception:
            self.present = False
            self.sensor = None

    def read(self):
        if not self.present:
            return {"aht21_present": False}
        try:
            return {
                "aht21_present": True,
                "temperature_C": round(self.sensor.temperature, 2),
                "humidity_pct": round(self.sensor.relative_humidity, 2)
            }
        except Exception as e:
            return {"aht21_present": True, "aht21_error": str(e)}


class ENS160Sensor:
    def __init__(self, i2c_bus):
        try:
            self.sensor = ENS160(i2c_bus, address=ADDR_ENS160)
            self.present = True
        except Exception:
            self.present = False
            self.sensor = None

    def read(self):
        if not self.present:
            return {"ens160_present": False}
        try:
            return {
                "ens160_present": True,
                "AQI": self.sensor.AQI,
                "TVOC_ppb": self.sensor.TVOC,
                "eCO2_ppm": self.sensor.eCO2,
            }
        except Exception as e:
            return {"ens160_present": True, "ens160_error": str(e)}


class BMP180Sensor:
    def __init__(self, i2c_bus):
        try:
            self.sensor = bmp180.BMP180(i2c_bus)
            self.sensor.sea_level_pressure = 1013.25
            self.present = True
        except Exception:
            self.present = False
            self.sensor = None

    def read(self):
        if not self.present:
            return {"bmp180_present": False}
        try:
            t = self.sensor.temperature
            p = self.sensor.pressure
            a = self.sensor.altitude
            return {
                "bmp180_present": True,
                "temperature_C": round(t, 2),
                "pressure_hPa": round(p, 2),
                "altitude_m": round(a, 2)
            }
        except Exception as e:
            return {"bmp180_present": True, "bmp180_error": str(e)}


class MHZ19Sensor:
    def __init__(self):
        self.present = True

    def read(self):
        if not self.present:
            return {"mhz19_present": False}
        try:
            data = mh_z19.read()
            if isinstance(data, dict) and "co2" in data:
                return {"mhz19_present": True, "co2_ppm": data["co2"]}
            return {"mhz19_present": True, "mhz19_error": "Invalid response"}
        except Exception as e:
            self.present = False
            return {"mhz19_present": True, "mhz19_error": str(e)}


# ------------------------------------------------
# Utilities
# ------------------------------------------------
def _try_load_ttf(size: int) -> Optional[ImageFont.FreeTypeFont]:
    """Try common TTF font paths and return a loaded ImageFont or None."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return None


# ------------------------------------------------
# Data Logger
# ------------------------------------------------
class DataLogger:
    def __init__(self, directory=CSV_DIR):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def log_csv(self, data):
        fname = self.directory / f"{datetime.date.today()}.csv"
        newfile = not fname.exists()
        data_to_log = {k: v for k, v in data.items() if k != "errors"}

        base_fields = [
            "timestamp",
            "aht21_present", "temperature_C", "humidity_pct",
            "ens160_present", "AQI", "TVOC_ppb", "eCO2_ppm",
            "bmp180_present", "pressure_hPa", "altitude_m",
            "mhz19_present", "co2_ppm",
        ]

        err_fields = sorted([k for k in data_to_log.keys() if k.endswith("_error")])
        fieldnames = base_fields + err_fields
        unique_fields = []
        for f in fieldnames:
            if f not in unique_fields:
                unique_fields.append(f)
        for k in data_to_log.keys():
            if k not in unique_fields:
                unique_fields.append(k)

        with open(fname, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=unique_fields, restval="", extrasaction="ignore")
            if newfile:
                writer.writeheader()
            writer.writerow(data_to_log)


# ------------------------------------------------
# OLED Display Manager
# ------------------------------------------------
class DisplayManager:
    def __init__(self, i2c_bus):
        try:
            self.oled = SSD1306_I2C(128, 32, i2c_bus, addr=ADDR_OLED)
            font_ttf = _try_load_ttf(14)
            self.font = font_ttf if font_ttf else ImageFont.load_default()
            self.available = True
        except Exception as e:
            print(f"OLED init error: {e}")
            self.available = False

    def show_summary(self, t, h, co2, from_ens=False):
        """Display temperature, humidity, and CO₂/eCO₂ on OLED."""
        if not self.available:
            return
        try:
            self.oled.fill(0)
            image = Image.new("1", (self.oled.width, self.oled.height))
            draw = ImageDraw.Draw(image)

            def fmt_t(val):
                return f"{val:4.1f}°C" if val is not None else "---"

            def fmt_h(val):
                return f"{val:4.1f}%" if val is not None else "---"

            def fmt_co2(val):
                return f"{val:4.0f} ppm" if (val is not None and val > 0) else "---ppm"

            t_str = fmt_t(t)
            h_str = fmt_h(h)
            co2_str = fmt_co2(co2)
            label = "eCO₂" if from_ens else "CO₂"

            line1 = f"{t_str}     {h_str}"
            line2 = f"{label}: {co2_str}"

            bbox1 = draw.textbbox((0, 0), line1, font=self.font)
            w1 = bbox1[2] - bbox1[0]
            x1 = (128 - w1) // 2

            bbox2 = draw.textbbox((0, 0), line2, font=self.font)
            w2 = bbox2[2] - bbox2[0]
            x2 = (128 - w2) // 2

            draw.text((x1, 0), line1, font=self.font, fill=255)
            draw.text((x2, 17), line2, font=self.font, fill=255)

            self.oled.image(image)
            self.oled.show()
        except Exception as e:
            print("OLED error:", e)


# ------------------------------------------------
# Main Loop
# ------------------------------------------------
def main():
    try:
        i2c_bus = busio.I2C(board.SCL, board.SDA)
    except Exception as e:
        print(f"I2C init failed: {e}")
        i2c_bus = None

    aht21 = AHT21Sensor(i2c_bus)
    ens160 = ENS160Sensor(i2c_bus)
    bmp180_s = BMP180Sensor(i2c_bus)
    mhz19 = MHZ19Sensor()

    sensors = [aht21, ens160, bmp180_s, mhz19]
    display = DisplayManager(i2c_bus)
    logger = DataLogger()

    while True:
        readings = {"timestamp": datetime.datetime.now().isoformat(timespec="seconds")}
        errors = []

        for s in sensors:
            try:
                d = s.read()
                readings.update(d)
                if any(k.endswith("_error") for k in d.keys()):
                    errors.append(str(d))
            except Exception as e:
                msg = f"{type(s).__name__} catastrophic: {e}"
                readings[f"{type(s).__name__}_error"] = msg
                errors.append(msg)

        if errors:
            readings["errors"] = "; ".join(errors)

        try:
            # 1. Log to CSV
            logger.log_csv(readings)

            # 2. Firebase
            send_realtime_data(readings)

            # 3. Display
            t = readings.get("temperature_C")
            h = readings.get("humidity_pct")

            co2 = readings.get("co2_ppm")
            from_ens = False
            if co2 is None or co2 <= 0:
                co2 = readings.get("eCO2_ppm")
                from_ens = True

            display.show_summary(t, h, co2, from_ens)
            print(json.dumps(readings, indent=2))
        except Exception:
            print("Logging/Display error:", traceback.format_exc())

        time.sleep(LOG_INTERVAL)


if __name__ == "__main__":
    main()

