"""Tests for usb_monitor.py core logic (no WMI / Windows required)."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Add repo root to path so we can import usb_monitor
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import usb_monitor


class TestLoadAllowlist(unittest.TestCase):
    def test_loads_valid_json_array(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fh:
            json.dump(["USB\\VID_046D&PID_C52B", "USB\\VID_1234"], fh)
            path = fh.name
        try:
            result = usb_monitor.load_allowlist(path)
            self.assertEqual(result, ["USB\\VID_046D&PID_C52B", "USB\\VID_1234"])
        finally:
            os.unlink(path)

    def test_entries_are_uppercased(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fh:
            json.dump(["usb\\vid_046d&pid_c52b"], fh)
            path = fh.name
        try:
            result = usb_monitor.load_allowlist(path)
            self.assertEqual(result, ["USB\\VID_046D&PID_C52B"])
        finally:
            os.unlink(path)

    def test_returns_empty_list_when_file_missing(self):
        result = usb_monitor.load_allowlist("/nonexistent/path/allowlist.json")
        self.assertEqual(result, [])

    def test_returns_empty_list_on_malformed_json(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fh:
            fh.write("not valid json {{{")
            path = fh.name
        try:
            result = usb_monitor.load_allowlist(path)
            self.assertEqual(result, [])
        finally:
            os.unlink(path)

    def test_returns_empty_list_when_json_is_not_array(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as fh:
            json.dump({"key": "value"}, fh)
            path = fh.name
        try:
            result = usb_monitor.load_allowlist(path)
            self.assertEqual(result, [])
        finally:
            os.unlink(path)


class TestIsAuthorized(unittest.TestCase):
    ALLOWLIST = ["USB\\VID_046D&PID_C52B", "USB\\VID_1234"]

    def test_authorized_exact_prefix(self):
        self.assertTrue(
            usb_monitor.is_authorized("USB\\VID_046D&PID_C52B\\5&1AB2", self.ALLOWLIST)
        )

    def test_authorized_case_insensitive(self):
        self.assertTrue(
            usb_monitor.is_authorized("usb\\vid_046d&pid_c52b\\5&1AB2", self.ALLOWLIST)
        )

    def test_unauthorized_device(self):
        self.assertFalse(
            usb_monitor.is_authorized("USB\\VID_FFFF&PID_9999\\1", self.ALLOWLIST)
        )

    def test_empty_allowlist_always_unauthorized(self):
        self.assertFalse(usb_monitor.is_authorized("USB\\VID_046D&PID_C52B", []))


class TestGetUsbDevices(unittest.TestCase):
    def _make_device(self, device_id, name="Test Device", status="OK"):
        d = MagicMock()
        d.DeviceID = device_id
        d.Name = name
        d.Status = status
        return d

    def test_filters_usb_devices(self):
        pci_device = self._make_device("PCI\\VEN_8086&DEV_1234", "PCI Device")
        usb_device = self._make_device("USB\\VID_046D&PID_C52B\\5&1", "USB Mouse")
        usb_stor = self._make_device("USBSTOR\\DISK&VEN_SAN&PROD_DISK\\1", "USB Disk")

        wmi_instance = MagicMock()
        wmi_instance.Win32_PnPEntity.return_value = [pci_device, usb_device, usb_stor]

        result = usb_monitor.get_usb_devices(wmi_instance)

        self.assertIn("USB\\VID_046D&PID_C52B\\5&1", result)
        self.assertIn("USBSTOR\\DISK&VEN_SAN&PROD_DISK\\1", result)
        self.assertNotIn("PCI\\VEN_8086&DEV_1234", result)

    def test_handles_wmi_exception_gracefully(self):
        wmi_instance = MagicMock()
        wmi_instance.Win32_PnPEntity.side_effect = Exception("WMI unavailable")

        result = usb_monitor.get_usb_devices(wmi_instance)
        self.assertEqual(result, {})

    def test_device_info_keys(self):
        usb_device = self._make_device("USB\\VID_046D&PID_C52B\\1", "USB Mouse", "OK")
        wmi_instance = MagicMock()
        wmi_instance.Win32_PnPEntity.return_value = [usb_device]

        result = usb_monitor.get_usb_devices(wmi_instance)
        info = result["USB\\VID_046D&PID_C52B\\1"]
        self.assertIn("device_id", info)
        self.assertIn("name", info)
        self.assertIn("status", info)
        self.assertEqual(info["name"], "USB Mouse")


class TestHandleConnected(unittest.TestCase):
    AUTHORIZED_LIST = ["USB\\VID_046D&PID_C52B"]

    def test_authorized_device_logs_info(self):
        info = {"device_id": "USB\\VID_046D&PID_C52B\\5", "name": "USB Mouse"}
        with self.assertLogs("usb_monitor", level="INFO") as cm:
            usb_monitor.handle_connected(info, self.AUTHORIZED_LIST)
        self.assertTrue(any("[AUTHORIZED]" in line for line in cm.output))

    def test_unauthorized_device_logs_warning(self):
        info = {"device_id": "USB\\VID_FFFF&PID_9999\\5", "name": "Unknown USB"}
        with self.assertLogs("usb_monitor", level="WARNING") as cm:
            usb_monitor.handle_connected(info, self.AUTHORIZED_LIST)
        self.assertTrue(any("[UNAUTHORIZED]" in line for line in cm.output))


class TestHandleDisconnected(unittest.TestCase):
    def test_disconnect_logs_info(self):
        info = {"device_id": "USB\\VID_046D&PID_C52B\\5", "name": "USB Mouse"}
        with self.assertLogs("usb_monitor", level="INFO") as cm:
            usb_monitor.handle_disconnected(info)
        self.assertTrue(any("[DISCONNECTED]" in line for line in cm.output))


class TestMonitorLoop(unittest.TestCase):
    """Integration-style tests for the monitor() function using mocked WMI."""

    def _make_device_dict(self, device_id, name="Test Device"):
        return {"device_id": device_id, "name": name, "status": "OK"}

    def test_detects_new_device(self):
        scan_results = [
            {"USB\\VID_046D\\1": self._make_device_dict("USB\\VID_046D\\1")},
            {
                "USB\\VID_046D\\1": self._make_device_dict("USB\\VID_046D\\1"),
                "USB\\VID_FFFF\\2": self._make_device_dict("USB\\VID_FFFF\\2", "New USB"),
            },
        ]
        call_count = [0]

        def fake_get_devices(_wmi):
            result = scan_results[min(call_count[0], len(scan_results) - 1)]
            call_count[0] += 1
            return result

        wmi_instance = MagicMock()
        wmi_factory = MagicMock(return_value=wmi_instance)

        with (
            patch("usb_monitor.get_usb_devices", side_effect=fake_get_devices),
            patch("usb_monitor.time.sleep", side_effect=[None, KeyboardInterrupt]),
            patch("usb_monitor.is_admin", return_value=True),
            patch("usb_monitor.handle_connected") as mock_connected,
            patch("usb_monitor.handle_disconnected"),
        ):
            usb_monitor.monitor(wmi_factory=wmi_factory, allowlist=[])

        mock_connected.assert_called_once()
        called_info = mock_connected.call_args[0][0]
        self.assertEqual(called_info["device_id"], "USB\\VID_FFFF\\2")

    def test_detects_removed_device(self):
        scan_results = [
            {
                "USB\\VID_046D\\1": self._make_device_dict("USB\\VID_046D\\1"),
                "USB\\VID_FFFF\\2": self._make_device_dict("USB\\VID_FFFF\\2", "Remove Me"),
            },
            {"USB\\VID_046D\\1": self._make_device_dict("USB\\VID_046D\\1")},
        ]
        call_count = [0]

        def fake_get_devices(_wmi):
            result = scan_results[min(call_count[0], len(scan_results) - 1)]
            call_count[0] += 1
            return result

        wmi_instance = MagicMock()
        wmi_factory = MagicMock(return_value=wmi_instance)

        with (
            patch("usb_monitor.get_usb_devices", side_effect=fake_get_devices),
            patch("usb_monitor.time.sleep", side_effect=[None, KeyboardInterrupt]),
            patch("usb_monitor.is_admin", return_value=True),
            patch("usb_monitor.handle_connected"),
            patch("usb_monitor.handle_disconnected") as mock_disconnected,
        ):
            usb_monitor.monitor(wmi_factory=wmi_factory, allowlist=[])

        mock_disconnected.assert_called_once()
        called_info = mock_disconnected.call_args[0][0]
        self.assertEqual(called_info["device_id"], "USB\\VID_FFFF\\2")

    def test_scan_error_does_not_crash(self):
        """An exception during a scan cycle should be caught and loop continues."""
        call_count = [0]

        def fake_get_devices(_wmi):
            call_count[0] += 1
            if call_count[0] == 1:
                return {}  # baseline
            raise RuntimeError("WMI blip")

        wmi_factory = MagicMock(return_value=MagicMock())

        with (
            patch("usb_monitor.get_usb_devices", side_effect=fake_get_devices),
            patch("usb_monitor.time.sleep", side_effect=[None, KeyboardInterrupt]),
            patch("usb_monitor.is_admin", return_value=False),
        ):
            # Should not raise
            usb_monitor.monitor(wmi_factory=wmi_factory, allowlist=[])


if __name__ == "__main__":
    unittest.main()
