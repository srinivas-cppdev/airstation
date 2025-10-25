import time
import os
import board
import busio
import bmp180

# Initialize I2C and sensor
i2c = busio.I2C(board.SCL, board.SDA)
bmp = bmp180.BMP180(i2c)
bmp.sea_level_pressure = 1013.25  # Adjust to your local sea-level pressure

def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')

while True:
    # Read sensor data
    temperature = bmp.temperature
    pressure = bmp.pressure
    altitude = bmp.altitude

    # Derived pressure conversions
    pressure_mmHg = pressure * 0.75006
    pressure_atm = pressure / 1013.25

    # Estimated dew point (assuming 50% RH)
    humidity = 50
    dew_point = temperature - ((100 - humidity) / 5)

    # Clear screen and display fresh data
    clear_screen()
    print("=========================================")
    print("         BMP180 SENSOR READINGS          ")
    print("=========================================")
    print(f"Temperature       : {temperature:8.2f} °C")
    print(f"Pressure (hPa)    : {pressure:8.2f} hPa")
    print(f"Pressure (mmHg)   : {pressure_mmHg:8.2f} mmHg")
    print(f"Pressure (atm)    : {pressure_atm:8.4f} atm")
    print(f"Altitude          : {altitude:8.2f} m")
    print(f"Estimated Dew Pt. : {dew_point:8.2f} °C")
    print("-----------------------------------------")
    print(f"Last Update: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("Refreshing every 5 seconds...")

    time.sleep(5)

