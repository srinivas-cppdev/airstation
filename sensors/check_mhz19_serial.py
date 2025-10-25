"""Minimal raw serial test for MH-Z19 sensor.

This bypasses the mh_z19 library to check if we can:
 1. Open the UART device
 2. Send the standard read command
 3. Receive 9 bytes and verify checksum

Reference command: FF 01 86 00 00 00 00 00 79
Response format: 9 bytes -> 0: 0xFF, 1: 0x86, 2: high CO2, 3: low CO2, last: checksum

Checksum = (0xFF - (sum(bytes[1:8]) % 256) + 1) & 0xFF

Run:
  python sensors/check_mhz19_serial.py        (non-root test)
  sudo python sensors/check_mhz19_serial.py   (if permission denied)
"""

import time
import sys

DEVICE_CANDIDATES = ["/dev/serial0", "/dev/ttyS0", "/dev/ttyAMA0"]
READ_CMD = bytes([0xFF, 0x01, 0x86, 0, 0, 0, 0, 0, 0x79])
TIMEOUT = 2.0


def open_port():
    import serial
    for dev in DEVICE_CANDIDATES:
        try:
            ser = serial.Serial(dev, baudrate=9600, timeout=TIMEOUT)
            print(f"Opened {dev}")
            return ser
        except Exception as e:
            print(f"Failed {dev}: {e}")
    raise SystemExit("No serial device opened.")


def compute_checksum(payload: bytes) -> int:
    return (0xFF - (sum(payload[1:8]) % 256) + 1) & 0xFF


def main():
    try:
        ser = open_port()
    except SystemExit as e:
        print(e)
        sys.exit(1)

    # Flush input
    ser.reset_input_buffer()

    print("Sending read command...")
    ser.write(READ_CMD)
    ser.flush()

    data = ser.read(9)
    print(f"Raw bytes ({len(data)}):", data)
    if len(data) != 9:
        print("Did not receive 9 bytes - check wiring / sensor warm-up (needs ~3min).")
        sys.exit(2)

    if data[0] != 0xFF or data[1] != 0x86:
        print("Unexpected header bytes.")

    co2 = data[2] * 256 + data[3]
    expected_checksum = compute_checksum(data)
    if data[-1] != expected_checksum:
        print(f"Checksum mismatch: got {data[-1]:02X} expected {expected_checksum:02X}")
    else:
        print("Checksum OK.")

    print(f"CO2 ppm: {co2}")
    ser.close()


if __name__ == "__main__":
    main()
