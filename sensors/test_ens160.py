from ens160 import ENS160
import smbus2, time

bus = smbus2.SMBus(1)
ens = ENS160(i2c_dev=bus, address=0x52)   # your address is 0x52

ens.set_mode(ENS160.MODE_STANDARD)        # library API varies; some call it 'set_operating_mode'
time.sleep(0.2)

print("AQI: ", ens.get_aqi())
print("eCO2:", ens.get_eco2(), "ppm")
print("TVOC:", ens.get_tvoc(), "ppb")

