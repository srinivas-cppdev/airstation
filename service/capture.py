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

import os, csv, time, datetime, json, serial, traceback
from pathlib import Path
import board, busio
from typing import Dict, Any

# Modules used in sensor_health.py and are working:
import bmp180  # For BMP180
import mh_z19  # For MH-Z19

# Adafruit CircuitPython imports
from adafruit_ens160 import ENS160 
from adafruit_ahtx0 import AHTx0 
from adafruit_ssd1306 import SSD1306_I2C 

from PIL import Image, ImageDraw, ImageFont
import requests


# ---------------- CONFIGURATION ----------------
LOG_INTERVAL = 30  # seconds
CSV_DIR = "/home/nivas/airstation/logs" 

# --- Firebase Real-time Configuration (NEW) ---
FIREBASE_URL = "https://iot-sensors-pi-78113-default-rtdb.europe-west1.firebasedatabase.app/"
SENSOR_ID = "raspi_4b"
USE_FIREBASE = True 
# ------------------------------------------------

I2C_BUS_ID = 1 
ADDR_AHT21 = 0x38
ADDR_ENS160 = 0x52
ADDR_BMP180 = 0x77
ADDR_OLED = 0x3C
# ------------------------------------------------


# ------------------------------------------------
# Firebase Real-time Push Function
# ------------------------------------------------

def send_realtime_data(data: Dict[str, Any]) -> None:
    """
    Sends a single sensor data record to the Firebase Realtime Database.
    This replaces the local API push for real-time logging.
    """
    if not USE_FIREBASE:
        return
        
    # Firebase POST request structure: BASE_URL/SENSOR_ID.json
    # This creates a unique timestamp-based key under the SENSOR_ID node.
    url = f"{FIREBASE_URL}/{SENSOR_ID}.json"
    
    try:
        # Use POST for a new record, sending the data dictionary as JSON payload
        # Timeout is set to 5 seconds to prevent the main loop from hanging
        response = requests.post(url, json=data, timeout=5)
        response.raise_for_status() # Raises an exception for 4xx or 5xx status codes
        
        # Success check (Firebase returns 200 OK)
        if response.status_code == 200:
            print(f"✅ Firebase Success: Data posted for {SENSOR_ID}")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Firebase Error posting data: {e}")


# ------------------------------------------------
# Individual Sensor Modules (Unchanged)
# ------------------------------------------------

class AHT21Sensor:
    def __init__(self, i2c_bus):
        self.i2c_bus = i2c_bus
        if self.i2c_bus is None:
            self.present = False
            self.sensor = None
            return
        try:
            self.sensor = AHTx0(self.i2c_bus, address=ADDR_AHT21)
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
        self.i2c_bus = i2c_bus
        if self.i2c_bus is None:
            self.present = False
            self.sensor = None
            return
        try:
            self.sensor = ENS160(self.i2c_bus, address=ADDR_ENS160)
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
        self.i2c_bus = i2c_bus
        if self.i2c_bus is None:
            self.present = False
            self.sensor = None
            return
        try:
            self.sensor = bmp180.BMP180(self.i2c_bus)
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
                co2 = data["co2"]
                return {"mhz19_present": True, "co2_ppm": co2}
            return {"mhz19_present": True, "mhz19_error": "Invalid response or key missing"}
        except Exception as e:
            self.present = False 
            return {"mhz19_present": True, "mhz19_error": str(e)}


# ------------------------------------------------
# Support Classes
# ------------------------------------------------

class DataLogger:
    def __init__(self, directory=CSV_DIR):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def log_csv(self, data):
        fname = self.directory / f"{datetime.date.today()}.csv"
        newfile = not fname.exists()
        
        # Exclude temporary fields like 'errors' for CSV logging
        data_to_log = {k: v for k, v in data.items() if k != "errors"}
        
        # --- Define custom field order ---
        base_fieldnames = [
            "timestamp",
            # AHT21
            "aht21_present", "temperature_C", "humidity_pct",
            # ENS160
            "ens160_present", "AQI", "TVOC_ppb", "eCO2_ppm",
            # BMP180
            "bmp180_present", "pressure_hPa", "altitude_m",
            # MHZ19
            "mhz19_present", "co2_ppm",
        ]

        error_fields = sorted([k for k in data_to_log.keys() if k.endswith("_error")])
        
        fieldnames = base_fieldnames + error_fields
        
        # Filter out duplicates and ensure all keys in data_to_log are in fieldnames
        unique_fieldnames = []
        for f in fieldnames:
            if f not in unique_fieldnames:
                unique_fieldnames.append(f)
        
        # Add any unexpected keys not defined in the base list
        for k in data_to_log.keys():
            if k not in unique_fieldnames:
                unique_fieldnames.append(k)
        
        
        with open(fname, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=unique_fieldnames, restval="", extrasaction="ignore")
            if newfile:
                writer.writeheader()
            writer.writerow(data_to_log)



class DisplayManager:
    def __init__(self, i2c_bus):
        self.i2c_bus = i2c_bus
        if self.i2c_bus is None:
            self.available = False
            return
        try:
            self.oled = SSD1306_I2C(128, 32, self.i2c_bus, addr=ADDR_OLED)
            self.font = ImageFont.load_default()
            self.available = True
        except Exception:
            self.available = False

    def show_summary(self, t, h, co2):
        if not self.available:
            return
        try:
            self.oled.fill(0)
            image = Image.new("1", (self.oled.width, self.oled.height))
            draw = ImageDraw.Draw(image)
            
            t_str = f"{t:4.1f}\u00B0C" if t else "---"
            h_str = f"{h:4.1f}%" if h else "---"
            co2_str = f"{co2:4.0f}ppm" if co2 and co2 > 0 else "---ppm"
            
            # Use draw.textbbox() for Pillow compatibility
            line1 = f"{t_str}     {h_str}"
            line2 = f"CO2: {co2_str}"
            
            bbox1 = draw.textbbox((0, 0), line1, font=self.font)
            w1 = bbox1[2] - bbox1[0]
            center_x1 = (128 - w1) // 2
            draw.text((center_x1, 2), line1, font=self.font, fill=255)
            
            bbox2 = draw.textbbox((0, 0), line2, font=self.font)
            w2 = bbox2[2] - bbox2[0]
            center_x2 = (128 - w2) // 2
            draw.text((center_x2, 17), line2, font=self.font, fill=255)

            self.oled.image(image)
            self.oled.show()
        except Exception as e:
            print("OLED error:", e)


# ------------------------------------------------
# Main Daemon Logic
# ------------------------------------------------

def main():
    i2c_bus = None
    try:
        i2c_bus = busio.I2C(board.SCL, board.SDA)
    except Exception as e:
        print(f"I2C Bus initialization failed: {e}. I2C sensors will be disabled.")
    
    aht21_sensor = AHT21Sensor(i2c_bus)
    ens160_sensor = ENS160Sensor(i2c_bus)
    bmp180_sensor = BMP180Sensor(i2c_bus)
    mhz19_sensor = MHZ19Sensor()
    
    sensors = [aht21_sensor, ens160_sensor, bmp180_sensor, mhz19_sensor]
    
    display = DisplayManager(i2c_bus)
    logger = DataLogger()

    while True:
        readings = {"timestamp": datetime.datetime.now().isoformat(timespec="seconds")}
        errors = []

        for s in sensors:
            try:
                sensor_data = s.read()
                readings.update(sensor_data)
                
                error_key = f"{type(s).__name__}_error"
                if error_key in sensor_data:
                    errors.append(f"{type(s).__name__} failed: {sensor_data[error_key]}")

            except Exception as e:
                msg = f"{type(s).__name__} failed catastrophically: {e}"
                readings[f"{type(s).__name__}_catastrophic_error"] = msg
                errors.append(msg)

        if errors:
            readings["errors"] = "; ".join(errors)

        try:
            # 1. Log to CSV
            logger.log_csv(readings)
            
            # 2. Log in Real-Time to Firebase (NEW)
            send_realtime_data(readings)

            # 3. Update Display
            t = readings.get("temperature_C")
            h = readings.get("humidity_pct")
            co2 = readings.get("co2_ppm") or readings.get("eCO2_ppm")
            
            display.show_summary(t, h, co2)

            print(json.dumps(readings, indent=2))
        except Exception:
            print("Logging/Display error:", traceback.format_exc())

        time.sleep(LOG_INTERVAL)


if __name__ == "__main__":
    main()

