"""Continuity settings: reading them, which changed, AWDL wakes, and the agent's advice before a game."""

import unittest

from agent.device import network
from agent.device.sources import continuity
from tests.test_network import AWDL_ON, series, shell

SHARING = '{\n    DiscoverableMode = "Contacts Only";\n    SidebarShowsAirDrop = 1;\n}\n'
ACTIVITY_ON = "{\n    ActivityAdvertisingAllowed = 1;\n    ActivityReceivingAllowed = 1;\n}\n"
ACTIVITY_OFF = "{\n    ActivityAdvertisingAllowed = 0;\n    ActivityReceivingAllowed = 0;\n}\n"
CONTROL = '{\n    AirplayReceiverEnabled = 1;\n    "NSStatusItem Visible WiFi" = 1;\n    Nested =     {\n        a = 1;\n    };\n}\n'


class ContinuityTests(unittest.TestCase):
    def test_parse_and_features(self):
        dumps = {"sharingd": continuity.parse_defaults(SHARING), "useractivityd": continuity.parse_defaults(ACTIVITY_ON),
                 "controlcenter": continuity.parse_defaults(CONTROL), "chronod": {"remoteWidgetsEnabled": "1"}}
        self.assertEqual(dumps["controlcenter"]["NSStatusItem Visible WiFi"], "1")
        self.assertNotIn("Nested", dumps["controlcenter"])
        self.assertEqual(continuity.features(dumps), {"airdrop": True, "airdrop_everyone": False, "handoff": True, "widgets": True, "airplay": True})
        off = {"sharingd": {"DiscoverableMode": "Off"}, "useractivityd": continuity.parse_defaults(ACTIVITY_OFF), "controlcenter": {}}
        self.assertEqual(continuity.features(off), {"airdrop": False, "airdrop_everyone": False, "handoff": False, "widgets": None, "airplay": None})

    def test_diff_finds_the_switched_key(self):
        before = {"useractivityd": continuity.parse_defaults(ACTIVITY_OFF)}
        after = {"useractivityd": continuity.parse_defaults(ACTIVITY_ON)}
        self.assertEqual(continuity.diff(before, after)[0], ("useractivityd", "ActivityAdvertisingAllowed", "0", "1"))

    def test_awdl_packet_counter(self):
        text = ("Name  Mtu   Network       Address            Ipkts Ierrs     Ibytes    Opkts Oerrs     Obytes  Coll\n"
                "awdl0 1500  <Link#14>   aa:bb:cc:dd:ee:ff      120     0      34000      345     0      56000     0\n")
        self.assertEqual(continuity.awdl_packets(text), 465)
        plain = ("Name       Mtu   Network       Address            Ipkts Ierrs    Opkts Oerrs  Coll\n"
                 "awdl0      1484  <Link#13>   aa:bb:cc:dd:ee:ff     5000     0     7000     0     0\n")
        self.assertEqual(continuity.awdl_packets(plain), 12000)
        self.assertIsNone(continuity.awdl_packets("netstat: interface awdl0 does not exist"))

    def test_awdl_wakes(self):
        timeline = [(0, False), (1, True), (2, True), (3, False), (4, True), (5, False)]
        self.assertEqual(continuity.awdl_wakes(timeline), 2)

    def test_airdrop_everyone_is_named(self):
        sh = shell(awdl=AWDL_ON, n=300, internet=series(4, 300, 0.25, seed=2), router=series(3, 300, 0.25, seed=2), extra={
            "defaults_sharingd": '{\n    DiscoverableMode = Everyone;\n}\n', "defaults_useractivityd": ACTIVITY_OFF,
            "defaults_controlcenter": "", "defaults_chronod": "", "defaults_screencontinuity": ""})
        q = "롤 지금 해도 돼?"
        r = network.report(network.measure(sh, "wifi_helper", q), q)
        self.assertIn("airdrop_everyone", r.codes())
        self.assertIn("늦게 온 핑", r.card)
        self.assertIn("AirDrop '모든 사람'", r.card)

    def test_agent_advises_before_a_game(self):
        sh = shell(awdl=AWDL_ON, n=300, internet=series(8, 300, 0.05, seed=2), router=series(3, 300, 0.05, seed=2), extra={
            "defaults_sharingd": SHARING, "defaults_useractivityd": ACTIVITY_ON, "defaults_controlcenter": CONTROL,
            "defaults_chronod": "", "defaults_screencontinuity": ""})
        q = "롤 지금 해도 돼?"
        r = network.report(network.measure(sh, "wifi_helper", q), q)
        self.assertIn("awdl_game_advice", r.codes())
        self.assertIn("--awdl off", next(f.advice for f in r.findings if f.code == "awdl_game_advice"))
        self.assertIn("Handoff", r.facts["Continuity features on"])
        self.assertIn("켜진 연속성 기능: AirDrop, Handoff, AirPlay 수신 모드", r.card)
        self.assertIn("game_watch.py --awdl off", r.card)


if __name__ == "__main__":
    unittest.main()
