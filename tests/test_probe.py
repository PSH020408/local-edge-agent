"""Offline tests for scripts/probe_device.py: identifiers are removed before outputs become fixtures."""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("probe_device", ROOT / "scripts" / "probe_device.py")
probe = importlib.util.module_from_spec(spec)
sys.modules["probe_device"] = probe
spec.loader.exec_module(probe)


class ScrubTests(unittest.TestCase):
    def test_plist_serial_numbers_are_removed_and_values_kept(self):
        text = ("<key>BatterySerialNumber</key>\n\t<string>F8Y1234ABCD</string>\n"
                "<key>CycleCount</key>\n\t<integer>312</integer>\n"
                "<key>Serial</key><string>D86ABC</string>")
        clean = probe.scrub(text)
        self.assertNotIn("F8Y1234ABCD", clean)
        self.assertNotIn("D86ABC", clean)
        self.assertIn("<integer>312</integer>", clean)

    def test_json_identifiers_uuids_macs_and_names_are_removed(self):
        text = ('{"serial_number" : "C02XYZ", "platform_UUID" : "1234ABCD-1111-2222-3333-444455556666",\n'
                ' "device_address" : "AA:BB:CC:DD:EE:FF", "chip_type" : "Apple M4 Pro",\n'
                ' "path" : "/Users/jules/Library", "_name" : "JulesMacBookPro"}')
        clean = probe.scrub(text, user="jules", host="JulesMacBookPro")
        for secret in ("C02XYZ", "1234ABCD-1111", "AA:BB:CC", "jules", "JulesMacBookPro"):
            self.assertNotIn(secret, clean)
        self.assertIn("Apple M4 Pro", clean)

    def test_ioreg_text_identifiers_are_removed(self):
        clean = probe.scrub('| "IOPlatformSerialNumber" = "C02ABC"\n| "Device Utilization %" = 37')
        self.assertNotIn("C02ABC", clean)
        self.assertIn('"Device Utilization %" = 37', clean)


class ProcessNameTests(unittest.TestCase):
    """Process lists show which applications run on the machine; fixtures keep only the numbers."""

    def test_ps_lines_keep_numbers_and_lose_names(self):
        text = "  12.5  1.2 /Applications/Some Chat.app/Contents/MacOS/Some Chat\n   0.0  0.1 /usr/sbin/cfprefsd\n"
        clean = probe.anonymize_processes(text)
        self.assertNotIn("Some Chat", clean)
        self.assertIn("12.5  1.2 process-1", clean)
        self.assertIn("0.0  0.1 process-2", clean)

    def test_top_rows_and_sleep_reasons(self):
        text = ("PID    COMMAND         %CPU POWER\n14907  Some Editor     3.1  12.4\n14906  Some Editor     0.0  0.0\n"
                " sleep                1 (sleep prevented by sharingd, Some App, powerd)\n")
        clean = probe.anonymize_processes(text)
        self.assertNotIn("Some", clean)
        self.assertIn("14907  process-1     3.1  12.4", clean)
        self.assertIn("14906  process-1     0.0  0.0", clean)
        self.assertIn("(sleep prevented by REMOVED)", clean)
        self.assertIn("PID    COMMAND         %CPU POWER", clean)

    def test_battery_manufacturing_data_is_removed(self):
        text = "<key>MfgData</key>\n<data>\nAAECAwQ=\n</data>\n<key>DateOfFirstUse</key><integer>123</integer>"
        clean = probe.scrub(text)
        self.assertNotIn("AAECAwQ=", clean)
        self.assertNotIn("<integer>123</integer>", clean)

    def test_a_scrubbed_plist_still_parses(self):
        import plistlib
        text = plistlib.dumps([{"Serial": "F8Y123", "MfgData": b"\x01\x02", "DateOfFirstUse": 12345, "CycleCount": 286}]).decode()
        data = plistlib.loads(probe.scrub(text).encode())[0]
        self.assertEqual((data["Serial"], data["MfgData"], data["DateOfFirstUse"], data["CycleCount"]), ("REMOVED", b"", 0, 286))


class RunTests(unittest.TestCase):
    def test_states(self):
        ok = probe.run(probe.Probe("echo", "test", [sys.executable, "-c", "print('CycleCount 3')"], r"CycleCount"))
        self.assertEqual(ok["state"], "available")
        missing = probe.run(probe.Probe("echo", "test", [sys.executable, "-c", "print('nothing')"], r"CycleCount"))
        self.assertEqual(missing["state"], "missing")
        absent = probe.run(probe.Probe("x", "test", ["no-such-command-xyz"], r"."))
        self.assertEqual(absent["state"], "no command")
        rights = probe.run(probe.Probe("x", "test", [sys.executable, "-c",
                                                     "import sys; print('sudo: a password is required'); sys.exit(1)"], r"."))
        self.assertEqual(rights["state"], "needs rights")

    def test_bluetooth_and_wifi_are_never_fixtures(self):
        names = {p.name: p.fixture for p in probe.PROBES}
        self.assertFalse(names["bluetooth"])
        self.assertFalse(names["wifi"])


if __name__ == "__main__":
    unittest.main()
