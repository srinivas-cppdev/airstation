import csv
import requests
import time
import sys
from typing import Dict, Any, List

# --- Configuration ---
# NOTE: Updated Firebase Realtime Database URL
FIREBASE_BASE_URL = "https://iot-sensors-pi-78113-default-rtdb.europe-west1.firebasedatabase.app/" 
# Updated sensor identifier
SENSOR_ID = "raspi_4b"
# Maximum number of log entries to send in a single HTTP POST request
BATCH_SIZE = 500
# --- End Configuration ---

def send_batch_to_firebase(url: str, sensor_id: str, batch_data: List[Dict[str, Any]]):
    """
    Sends a batch of formatted sensor data points as a single POST request 
    to a Firebase Realtime Database-style endpoint.
    
    The POST request will append a new unique ID for each item in the batch.
    """
    
    if not batch_data:
        print("⚠️ Warning: Attempted to send an empty batch.")
        return

    # Construct the full URL: e.g., https://<BASE_URL>/<SENSOR_ID>.json
    full_url = f"{url}/{sensor_id}.json"
    
    # We send the list of dictionaries as the JSON payload.
    batch_size = len(batch_data)
    first_timestamp = batch_data[0].get('timestamp', 'N/A')
    last_timestamp = batch_data[-1].get('timestamp', 'N/A')
    
    print(f"📦 Sending batch of {batch_size} records (from {first_timestamp} to {last_timestamp})...")

    try:
        # We include a small timeout to prevent hanging forever
        response = requests.post(full_url, json=batch_data, timeout=10)
        
        # Firebase RTDB returns a 200 status code on success
        if response.status_code == 200:
            print(f"✅ Success: Batch of {batch_size} records sent.")
        else:
            print(f"❌ Error ({response.status_code}): Could not send batch.")
            print(f"Response text: {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Connection Error: Failed to connect or timed out. {e}")

def process_log_file(filepath: str, base_url: str, sensor_id: str):
    """
    Opens the CSV log file, processes it row by row, collects rows into batches,
    and sends the batches to the Firebase endpoint.
    """

    current_batch: List[Dict[str, Any]] = []
    # Initialize reader to None outside the try/except scope for safety, 
    # though strictly, it's not needed if all use is inside the 'with' block.
    # The true fix is ensuring the exception block catches the right error.

    try:
        print(f"Starting to process file: {filepath}...")
        
        # Use a nested try-except specifically for file opening
        try:
            # Use csv.DictReader to easily access columns by header name
            with open(filepath, mode='r', newline='') as file:
                reader = csv.DictReader(file)
    
                # Iterate over each row (which is treated as a dictionary)
                for i, row in enumerate(reader):
                    data: Dict[str, Any] = {}
                    # row_number is the actual line number in the CSV (1-based index)
                    row_number = i + 2
    
                    # --- Data Processing and Conversion ---
                    is_valid_row = True
                    for key, value in row.items():
                        
                        # Add the crucial check from the previous fix attempt
                        if key is None:
                            print(f"⚠️ Warning on row {row_number}: Skipping column with a blank header.")
                            continue
                            
                        # 1. Skip columns ending in '_present' (e.g., 'aht21_present')
                        if key.endswith('_present'):
                            continue

                        # 2. 'timestamp' is kept as a string
                        if key == 'timestamp':
                            data[key] = value
                            continue

                        # 3. Attempt to convert all other values to float for numerical storage
                        try:
                            # Convert empty strings to None, otherwise convert to float
                            if value is None or value.strip() == '':
                                data[key] = None
                            else:
                                data[key] = float(value)
                        except ValueError:
                            # Handle cases where expected numerical data is invalid
                            print(f"Skipping row {row_number}: Non-numeric value '{value}' found for column '{key}'.")
                            is_valid_row = False
                            break      # Stop processing this row keys

                    # --- Batching Logic ---
                    if is_valid_row and data:
                        current_batch.append(data)

                        # If the batch is full, send it and reset
                        if len(current_batch) >= BATCH_SIZE:
                            send_batch_to_firebase(base_url, sensor_id, current_batch)
                            current_batch = []
                            # time.sleep(0.5)

            # --- Send Final (Partial) Batch ---
            if current_batch:
                print("Sending final partial batch...")
                send_batch_to_firebase(base_url, sensor_id, current_batch)
            
        except FileNotFoundError:
            # Re-raise or handle the FileNotFoundError separately for clarity
            raise

    except FileNotFoundError:
        print(f"\n🛑 Error: File not found at '{filepath}'. Please check the path.")
        
    except Exception as e:
        # This catch-all should be the last resort
        print(f"\n🛑 An unexpected error occurred: {e}")

# --- Example Usage ---
if __name__ == "__main__":
    
    # Check if a file path was provided as a command-line argument
    if len(sys.argv) < 2:
        print("Usage: python3 log_uploader.py <path/to/logfile.csv>")
        sys.exit(1) # Exit with an error code

    # The file path is the first argument after the script name (sys.argv[1])
    LOG_FILEPATH = sys.argv[1]
    
    # Run the processing function
    process_log_file(LOG_FILEPATH, FIREBASE_BASE_URL, SENSOR_ID)
    print("\nProcessing complete.")

