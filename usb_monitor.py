"""
USB Device Control & Monitoring Framework
==========================================
A lightweight Windows USB event detection and alerting utility.

Features:
  - Monitors USB device connections/disconnections using WMI.
  - Logs all events with timestamps to usb_activity.log.
  - Checks newly connected devices against an allowlist.
  - Flags unauthorized devices with a recommended action.
  - Requires Administrator privileges for full device visibility.

Usage:
  Run directly:        python usb_monitor.py
  Run as admin:        run_as_admin.bat
"""

import ctypes
import json
import logging
import os
import sys
import time
from datetime import datetime

LOG_FILE = "usb_activity.log"
ALLOWLIST_FILE = "allowlist.json"
SCAN_INTERVAL = 2  # seconds between each scan cycle

BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║        USB DEVICE CONTROL & MONITORING FRAMEWORK            ║
║                  Windows Security Tool                       ║
╚══════════════════════════════════════════════════════════════╝
"""


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(log_file: str = LOG_FILE) -> logging.Logger:
    """Configure and return the module logger."""
    logger = logging.getLogger("usb_monitor")
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler – always INFO and above
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(formatter)

    # Console handler – INFO and above
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


logger = setup_logging()


# ---------------------------------------------------------------------------
# Allowlist helpers
# ---------------------------------------------------------------------------

def load_allowlist(path: str = ALLOWLIST_FILE) -> list:
    """Load approved device IDs from *path*.

    The file is a JSON array of device-ID prefix strings (case-insensitive).
    Returns an empty list if the file is missing or malformed.
    """
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return [str(entry).upper() for entry in data]
        logger.warning("allowlist.json must contain a JSON array – ignoring.")
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load allowlist: %s", exc)
    return []


def is_authorized(device_id: str, allowlist: list) -> bool:
    """Return True when *device_id* matches any prefix in *allowlist*."""
    upper_id = device_id.upper()
    return any(upper_id.startswith(prefix) for prefix in allowlist)


# ---------------------------------------------------------------------------
# Admin privilege check
# ---------------------------------------------------------------------------

def is_admin() -> bool:
    """Return True when the current process has Administrator privileges."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except AttributeError:
        # Non-Windows platform – used during testing
        return False


# ---------------------------------------------------------------------------
# WMI helpers
# ---------------------------------------------------------------------------

def get_usb_devices(wmi_instance) -> dict:
    """Query WMI and return a dict of USB-related PnP devices.

    Keys are DeviceID strings; values are dicts with 'name', 'device_id',
    and 'status' keys.
    """
    devices = {}
    try:
        for device in wmi_instance.Win32_PnPEntity():
            device_id = device.DeviceID or ""
            if "USB" in device_id.upper():
                devices[device_id] = {
                    "device_id": device_id,
                    "name": device.Name or "Unknown Device",
                    "status": device.Status or "Unknown",
                }
    except Exception as exc:  # noqa: BLE001
        logger.error("WMI query error: %s", exc)
    return devices


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

def handle_connected(device_info: dict, allowlist: list) -> None:
    """Log and report a newly connected device."""
    device_id = device_info["device_id"]
    name = device_info["name"]

    if is_authorized(device_id, allowlist):
        logger.info("[CONNECTED][AUTHORIZED]   %s  |  %s", name, device_id)
    else:
        logger.warning(
            "[CONNECTED][UNAUTHORIZED] %s  |  %s  |  RECOMMENDATION: review and block if unknown",
            name,
            device_id,
        )


def handle_disconnected(device_info: dict) -> None:
    """Log a disconnected device."""
    logger.info(
        "[DISCONNECTED]            %s  |  %s",
        device_info["name"],
        device_info["device_id"],
    )


# ---------------------------------------------------------------------------
# Core monitoring loop
# ---------------------------------------------------------------------------

def monitor(wmi_factory=None, allowlist: list | None = None) -> None:
    """Run the USB monitoring loop.

    *wmi_factory* is a zero-argument callable that returns a WMI instance.
    It can be injected for testing without a real WMI connection.
    When *None*, the ``wmi`` module is imported and used.

    *allowlist* may be supplied directly (e.g. for tests); otherwise it is
    loaded from ``allowlist.json``.
    """
    if wmi_factory is None:
        import wmi as _wmi  # Windows-only import; deferred so tests can run on Linux

        wmi_factory = _wmi.WMI

    if allowlist is None:
        allowlist = load_allowlist()

    print(BANNER)

    # --- Admin check -------------------------------------------------------
    if is_admin():
        logger.info("Running with Administrator privileges.")
    else:
        logger.warning(
            "Not running as Administrator – some devices may be invisible. "
            "Use run_as_admin.bat for full access."
        )

    logger.info("Log file  : %s", os.path.abspath(LOG_FILE))
    logger.info("Allowlist : %d approved device prefix(es) loaded.", len(allowlist))
    logger.info("Scan interval: %d second(s).", SCAN_INTERVAL)

    # --- Initialise WMI ----------------------------------------------------
    try:
        wmi_instance = wmi_factory()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to initialise WMI: %s", exc)
        sys.exit(1)

    # --- Baseline ----------------------------------------------------------
    logger.info("Establishing baseline …")
    previous_devices = get_usb_devices(wmi_instance)
    logger.info("Baseline: %d USB device(s) currently connected.", len(previous_devices))
    logger.info("Monitoring started – press Ctrl+C to stop.\n")

    # --- Scan loop ---------------------------------------------------------
    try:
        while True:
            time.sleep(SCAN_INTERVAL)
            try:
                current_devices = get_usb_devices(wmi_instance)
            except Exception as exc:  # noqa: BLE001
                logger.error("Scan error: %s – continuing.", exc)
                continue

            for device_id, info in current_devices.items():
                if device_id not in previous_devices:
                    handle_connected(info, allowlist)

            for device_id, info in previous_devices.items():
                if device_id not in current_devices:
                    handle_disconnected(info)

            previous_devices = current_devices

    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    monitor()
