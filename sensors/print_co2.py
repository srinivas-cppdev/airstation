"""Print CO2 concentration from an MH-Z19 sensor.

Falls back to a mock value if:
 - The mh_z19 library is missing
 - Serial port cannot be opened (permission / not present)
 - Any other exception occurs while reading.

Usage: python print_co2.py
"""

from datetime import datetime

def _read_real():
	import mh_z19  # local import so fallback works if missing
	return mh_z19.read()

def _read_mock():
	# Provide a simple deterministic-ish mock so logs are readable
	# (Could import mock_sensors if desired, kept lightweight here.)
	ts = int(datetime.utcnow().timestamp())
	pseudo = 400 + (ts % 800)  # cycles between 400-1199
	return {"co2": pseudo, "source": "mock"}

def read_co2():
	try:
		data = _read_real()
		# mh_z19.read() returns dict like {'co2': 815}
		if not isinstance(data, dict) or 'co2' not in data:
			raise ValueError(f"Unexpected mh_z19 response: {data!r}")
		data["source"] = "sensor"
		return data
	except ModuleNotFoundError:
		return _read_mock()
	except Exception as e:  # SerialException, permission errors, etc.
		# Provide context in output, but still return mock value
		mock = _read_mock()
		mock["error"] = str(e)
		return mock

if __name__ == "__main__":
	reading = read_co2()
	ts = datetime.utcnow().isoformat()
	print({"timestamp": ts, **reading})

