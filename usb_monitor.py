import wmi
import time
import datetime
import os
import ctypes
import sys

# --- CONFIGURATION ---
LOG_FILE = "usb_activity_log.txt"

# ALLOWLIST: Add the Device IDs of your "Safe" USB drives here.
# You will see the ID in the logs when you first plug it in.
ALLOWED_DEVICES = [
    "VID_XXXX&PID_XXXX"  # Replace with real ID after first run
]

def log_alert(message):
    """Saves alerts to file and prints them"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{timestamp}] {message}"
    print(full_msg)
    with open(LOG_FILE, "a") as f:
        f.write(full_msg + "\n")

def is_admin():
    """Check if script is running with admin privileges"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def get_usb_devices():
    """Scans for currently connected USB Mass Storage devices"""
    devices = []
    try:
        c = wmi.WMI()
        # Query for USB devices - handle various device types
        for item in c.Win32_PnPEntity():
            try:
                if item.Name and ("USB" in item.Name or "Mobile" in item.Name or "Phone" in item.Name):
                    devices.append((item.DeviceID, item.Name))
            except Exception as e:
                # Skip devices that can't be accessed
                continue
    except Exception as e:
        log_alert(f"WARNING: WMI query error: {str(e)}")
        log_alert("Trying alternate device detection method...")
        try:
            # Fallback: Try querying just USB devices
            c = wmi.WMI()
            for item in c.Win32_USBControllerDevice():
                devices.append((str(item), "USB Device"))
        except:
            pass
    
    return devices

def monitor_usb():
    print("="*50)
    print(" USB Device Control & Monitoring Agent")
    print("="*50)
    
    # Check for admin privileges
    if not is_admin():
        print("[!] WARNING: Not running as Administrator!")
        print("[*] Some USB devices may not be detected.")
        print("[*] Attempting to continue anyway...\n")
        log_alert("Script started without admin privileges")
    else:
        print("[+] Running with admin privileges\n")
        log_alert("Script started with admin privileges")
    
    print("[*] Monitoring for USB connections...")
    log_alert("Monitoring started")

    # Create Initial Baseline (What is plugged in right now?)
    try:
        previous_devices = set()
        initial_devices = get_usb_devices()
        for device_info in initial_devices:
            if isinstance(device_info, tuple):
                previous_devices.add(device_info[0])
            else:
                previous_devices.add(device_info)
        print(f"[*] Found {len(previous_devices)} existing USB device(s)")
    except Exception as e:
        print(f"[!] Error during initialization: {e}")
        log_alert(f"Initialization error: {e}")
        return

    while True:
        try:
            time.sleep(2) # Poll every 2 seconds
            current_device_list = get_usb_devices()
            current_devices = set()
            
            for device_info in current_device_list:
                if isinstance(device_info, tuple):
                    current_devices.add(device_info[0])
                else:
                    current_devices.add(device_info)

            # Check for NEW connections
            new_devices = current_devices - previous_devices
            for device_id in new_devices:
                # Basic parsing to extract a cleaner ID (Optional)
                clean_id = device_id.split("\\")[-1] if "\\" in device_id else device_id
                
                log_alert(f"EVENT: USB Device Connected! -> ID: {clean_id}")

                # Security Check
                is_allowed = False
                for allowed in ALLOWED_DEVICES:
                    if allowed in device_id:
                        is_allowed = True
                        break
                
                if is_allowed:
                    log_alert(f"STATUS: Device is AUTHORIZED (In Allowlist).")
                else:
                    log_alert(f"ALERT: UNAUTHORIZED DEVICE DETECTED! Blocking recommended.")

            # Check for REMOVED connections
            removed_devices = previous_devices - current_devices
            for device_id in removed_devices:
                 log_alert(f"EVENT: USB Device Disconnected -> ID: {device_id}")

            # Update state
            previous_devices = current_devices

        except Exception as e:
            print(f"[!] Error in monitoring loop: {e}")
            log_alert(f"Monitoring loop error: {e}")
            time.sleep(5)  # Wait before retrying

# --- MAIN LOOP ---
if __name__ == "__main__":
    monitor_usb()