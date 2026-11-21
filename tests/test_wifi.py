"""Wi-Fi readings: parsers and the statistics that decide how long to measure (no Mac needed)."""

import math
import random
import unittest

from agent.device.sources import wifi

WDUTIL = """
WIFI
    Op Mode              : STA
    RSSI                 : -44 dBm
    CCA                  : 12 %
    Noise                : -94 dBm
    Tx Rate              : 433.0 Mbps
    Security             : WPA2 Personal
    PHY Mode             : 11ac
    MCS Index            : 9
    Guard Interval       : 400
    NSS                  : 1
    Channel              : 5g44/80
"""

PING = """PING 192.168.1.1 (192.168.1.1): 56 data bytes
64 bytes from 192.168.1.1: icmp_seq=0 ttl=64 time=3.000 ms
64 bytes from 192.168.1.1: icmp_seq=1 ttl=64 time=101.900 ms
64 bytes from 192.168.1.1: icmp_seq=3 ttl=64 time=5.100 ms
Request timeout for icmp_seq 2

--- 192.168.1.1 ping statistics ---
4 packets transmitted, 3 packets received, 25.0% packet loss
"""


class ParserTests(unittest.TestCase):
    def test_wdutil(self):
        r = wifi.parse_wdutil(WDUTIL)
        self.assertEqual((r["rssi_dbm"], r["noise_dbm"], r["cca_percent"], r["nss"], r["mcs"]), (-44, -94, 12, 1, 9))
        self.assertEqual((r["band_ghz"], r["channel"], r["width_mhz"]), ("5", 44, 80))
        self.assertEqual(r["tx_mbps"], 433.0)

    def test_ping_by_sequence(self):
        p = wifi.parse_ping(PING)
        self.assertEqual(p["sent"], 4)
        self.assertEqual(sorted(p["replies"]), [0, 1, 3])
        s = wifi.latency_stats(list(p["replies"].values()), p["sent"])
        self.assertEqual(s["loss_percent"], 25.0)
        self.assertAlmostEqual(s["spike_share"], 1 / 3, places=3)
        self.assertEqual(s["max_ms"], 101.9)

    def test_helper_lines(self):
        r = wifi.parse_lines('noise\n{"rssi_dbm": -48, "phy": 5, "channel": 44}\n')
        self.assertEqual(r, [{"rssi_dbm": -48, "phy": "802.11ac", "channel": 44}])


class MeasuringTimeTests(unittest.TestCase):
    def test_update_period_from_held_values(self):
        # sampled at 10 Hz, value changes every 0.5 s
        samples = [(i / 10, -48 - (i // 5) % 2) for i in range(100)]
        self.assertAlmostEqual(wifi.update_period(samples), 0.5, places=2)

    def test_correlation_time_of_held_noise(self):
        random.seed(1)
        held = []
        for _ in range(200):
            held += [random.gauss(-50, 3)] * 5          # a new independent value every 5 samples
        tau = wifi.correlation_time(held, 0.1)
        self.assertTrue(0.2 <= tau <= 0.6, tau)

    def test_seconds_for_mean(self):
        # sigma 3 dB, independent readings every 2*0.5 s: (1.96*3)^2 = 34.6 readings
        self.assertAlmostEqual(wifi.seconds_for_mean(3, 0.5), 34.6, places=1)

    def test_window_spread_shrinks_with_length(self):
        random.seed(2)
        series = [(i * 0.2, random.gauss(10, 3)) for i in range(300)]
        rows = wifi.window_spread(series, [5, 30], lambda v: sum(v) / len(v))
        self.assertGreater(rows[0]["worst_error"], rows[1]["worst_error"])
        self.assertEqual(rows[1]["windows"], 1)

    def test_percentile(self):
        self.assertEqual(wifi.percentile([1, 2, 3, 4, 5], 0.5), 3)
        self.assertTrue(math.isclose(wifi.percentile([0, 10], 0.95), 9.5))


if __name__ == "__main__":
    unittest.main()


class BluetoothTests(unittest.TestCase):
    TEXT = ('{"SPBluetoothDataType": [{"device_connected": [{"Mouse X": {"device_minorType": "Mouse", "device_rssi": "-53"}},'
            ' {"Speaker Y ": {"device_minorType": "Speaker", "device_rssi": "-61"}}, {"Keys": {"device_minorType": "Keyboard"}}]}]}')

    def test_parse_and_pick(self):
        from agent.device.sources import bluetooth
        devices = bluetooth.parse(self.TEXT)
        self.assertEqual([d["rssi_dbm"] for d in devices], [-53, -61, None])
        self.assertEqual(bluetooth.pick(devices)["name"], "Speaker Y")
        self.assertEqual(bluetooth.pick(devices, "mouse")["rssi_dbm"], -53)
        self.assertIsNone(bluetooth.pick(bluetooth.parse("not json")))


class HomeBeaconTests(unittest.TestCase):
    def test_strongest_per_home_network(self):
        nets = [{"ssid": "Home-A-5G", "rssi_dbm": -40, "band_ghz": "5", "channel": 44}, {"ssid": "Home-A-5G", "rssi_dbm": -55, "band_ghz": "5", "channel": 44},
                {"ssid": "Home-C-5G", "rssi_dbm": -69, "band_ghz": "5", "channel": 149}, {"ssid": "SK_WiFi", "rssi_dbm": -60, "band_ghz": "2.4"},
                {"ssid": "", "rssi_dbm": -30, "band_ghz": "2.4"}]
        b = wifi.home_beacons(nets, "Home-")
        self.assertEqual(sorted(b), ["home-a-5g", "home-c-5g"])   # keys in lower case
        self.assertEqual(b["home-a-5g"]["rssi_dbm"], -40)

    def test_ble_lines_and_windows(self):
        from agent.device.sources import ble
        self.assertEqual(ble.parse("t=100.5 rssi=-37 id=ABCD1234 name=MyiPhone"), (100.5, -37, "ABCD1234", "MyiPhone"))
        m = ble.BleMonitor("myiphone", command=["true"])
        m.heard = [(100.0, -40), (105.0, -42), (111.0, -50), (106.0, 127)]
        self.assertEqual(m.window(99, 110), [-40, -42])
        self.assertEqual(ble.summary([-40, -42, -44]), {"ble": -42.0, "ble_packets": 3})
