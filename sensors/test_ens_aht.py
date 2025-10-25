import time
import board
import busio

# ENS160 and AHTx0 drivers
from adafruit_ens160 import ENS160
from adafruit_ahtx0 import AHTx0

i2c = busio.I2C(board.SCL, board.SDA)

# ENS160 init
try:
    ens = ENS160(i2c, address=0x52)   # your address is 0x52
    #ens = ENS160(i2c)
    print("ENS160 detected")
except Exception as e:
    ens = None
    print("ENS160 init failed:", e)

# AHTx0 (AHT21) init
try:
    aht = AHTx0(i2c)
    print("AHTx0 detected")
except Exception as e:
    aht = None
    print("AHTx0 init failed:", e)

time.sleep(1.0)

for _ in range(5):
    if aht is not None:
        try:
            print(f"AHT temp={aht.temperature:.2f} C  RH={aht.relative_humidity:.2f} %")
            # Tell ENS160 about current ambient T/RH for compensation
            if ens is not None:
                ens.temperature_compensation = aht.temperature
                ens.humidity_compensation = aht.relative_humidity
        except Exception as e:
            print("AHT read error:", e)

    if ens is not None:
        try:
            # ENS160 buffers; check `new_data_available` to fetch fresh sample
            if ens.new_data_available:
                data = ens.read_all_sensors()
            else:
                # fallback to properties if available
                data = {
                    "AQI": ens.AQI,
                    "TVOC": ens.TVOC,
                    "eCO2": ens.eCO2,
                }
            print("ENS read:", data)
        except Exception as e:
            print("ENS read error:", e)

    time.sleep(2.0)

