import board, busio
import adafruit_ahtx0

i2c = busio.I2C(board.SCL, board.SDA)
aht = adafruit_ahtx0.AHTx0(i2c, address=0x38)  # AHT21 is compatible

print("Temperature: %.2f °C" % aht.temperature)
print("Humidity:    %.2f %%RH" % aht.relative_humidity)

