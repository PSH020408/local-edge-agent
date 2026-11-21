"""Network choice: SNR and SINR with the CCA rule, the expected rate, and the decision (no Mac needed)."""

import json
import unittest
from pathlib import Path

from agent.device import network, wifi_choice as wc
from tests.test_network import AWDL_OFF, WDUTIL, shell


def net(ssid, rssi, channel=44, band="5", width=80):
    return {"ssid": ssid, "rssi_dbm": rssi, "channel": channel, "band_ghz": band, "width_mhz": width}


class SinrTests(unittest.TestCase):
    def test_strong_cochannel_network_shares_airtime_not_noise(self):
        q = wc.sinr(-56, -92, [-59])            # walk 2, living area: AP-B heard at -59 dBm on the same channel
        self.assertEqual(q["snr"], 36.0)
        self.assertEqual(q["sinr"], 36.0)       # above -82 dBm: CSMA/CA, the radios take turns
        self.assertEqual(q["shared"], 1)
        self.assertLess(q["sinr_worst"], 5)     # if it were added to the noise: about 3 dB

    def test_weak_cochannel_network_adds_to_noise(self):
        q = wc.sinr(-79, -94, [-83])            # walk 2, entry: AP-B at -83 dBm, below the CCA level
        self.assertEqual(q["shared"], 0)
        self.assertAlmostEqual(q["sinr"], 3.7, delta=0.2)
        self.assertEqual(q["sinr"], q["sinr_worst"])

    def test_expected_rate_follows_the_measured_table(self):
        self.assertEqual(wc.expected_rate(40), 433.0)
        self.assertEqual(wc.expected_rate(27.5), 325.0)
        self.assertLess(wc.expected_rate(12), 60)
        self.assertEqual(wc.expected_rate(0), 0.0)
        self.assertAlmostEqual(wc.expected_rate(40, 40, "2.4"), 150.0, delta=1)   # 64-QAM 5/6 at 40 MHz


class DecisionTests(unittest.TestCase):
    def test_room_c_switches_to_its_own_router(self):
        # walk 2, point 18: own router at -68 dBm, the router in that room at -44 dBm
        scan = [net("Home-A-5G", -68), net("Home-B-5G", -87), net("Home-C-5G", -44, 149), net("Home-C-2.4G", -42, 2, "2.4", 40)]
        choice = wc.decide(wc.candidates(scan, -94, current="Home-A-5G"))
        self.assertEqual(choice.action, "switch")
        self.assertEqual(choice.best.ssid, "Home-C-5G")

    def test_near_own_router_stays(self):
        scan = [net("Home-A-5G", -38), net("Home-B-5G", -72)]
        self.assertEqual(wc.decide(wc.candidates(scan, -93, current="Home-A-5G")).action, "stay")

    def test_close_call_asks_for_a_test(self):
        scan = [net("Home-A-5G", -62), net("Home-B-5G", -59), net("Home-C-5G", -60, 149)]   # walk 2, point 8
        choice = wc.decide(wc.candidates(scan, -92, current="Home-A-5G"))
        self.assertEqual(choice.action, "try")

    def test_only_known_networks_and_unnamed_interferers(self):
        scan = [net("Home-A-5G", -50), net("neighbour", -40, 149), net("", -60)]
        cands = wc.candidates(scan, -93, known={"Home-A-5G"}, current="Home-A-5G")
        self.assertEqual([(c.ssid, c.saved) for c in cands], [("neighbour", False), ("Home-A-5G", True)])
        self.assertEqual(cands[1].shared, 1)    # the unnamed network on channel 44
        self.assertEqual(wc.decide(cands).action, "stay")      # a stronger network that is not saved is not advised

    def test_wifi_direct_is_interference_not_a_choice(self):
        scan = [net("Home-A-2.4G", -48, 1, "2.4", 40), net("DIRECT-18 C56x Series", -60, 1, "2.4", 20)]
        cands = wc.candidates(scan, -93, current="Home-A-2.4G")
        self.assertEqual([c.ssid for c in cands], ["Home-A-2.4G"])
        self.assertEqual(cands[0].shared, 1)

    def test_unknown_current_network_only_ranks(self):
        self.assertEqual(wc.decide(wc.candidates([net("Home-C-5G", -50, 149)], -93)).action, "rank")

    def test_preferred_list(self):
        text = "Preferred networks on en0:\n\tHome-A-5G\n\tHome-C-5G\n\tCafe Free\n"
        self.assertEqual(wc.parse_preferred(text), {"Home-A-5G", "Home-C-5G", "Cafe Free"})


class AgentTests(unittest.TestCase):
    def test_which_wifi_question(self):
        scan = "\n".join(json.dumps(n) for n in [net("Home-A-5G", -68), net("Home-C-5G", -44, 149), net("neighbour", -30, 1, "2.4", 20)])
        wd = WDUTIL.format(rssi=-68, cca=1, mcs=6) + "    SSID : Home-A-5G\n"
        sh = shell(rssi=-68, awdl=AWDL_OFF, extra={"wifi_scan": scan, "wdutil": wd,
                                                   "preferred": "Preferred networks on en0:\n\tHome-A-5G\n\tHome-C-5G\n"})
        q = "여기서 어떤 와이파이 쓰는 게 좋아?"
        r = network.report(network.measure(sh, "wifi_helper", q), q)
        self.assertIn("network_switch", r.codes())
        self.assertIn("SINR", r.facts["network 'Home-C-5G'"])
        self.assertNotIn("network 'neighbour'", r.facts)


if __name__ == "__main__":
    unittest.main()
