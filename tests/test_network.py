"""Network agent: measurement parsed from recorded-style outputs, and the diagnosis per scenario (no Mac needed)."""

import json
import random
import tempfile
import unittest
from pathlib import Path

from agent.device import network
from agent.device.router import route
from agent.device.shell import FixtureShell

ROUTE = "   route to: default\ndestination: default\n    gateway: 192.168.0.1\n  interface: en0\n"
AWDL_ON = "awdl0: flags=8943<UP,BROADCAST,RUNNING,PROMISC,SIMPLEX,MULTICAST> mtu 1500\n\tstatus: active\n"
AWDL_OFF = "awdl0: flags=8802<BROADCAST,SIMPLEX,MULTICAST> mtu 1500\n\tstatus: inactive\n"
WDUTIL = "WIFI\n    RSSI : {rssi} dBm\n    CCA : {cca} %\n    Noise : -94 dBm\n    Tx Rate : 433.0 Mbps\n    MCS Index : {mcs}\n    NSS : 1\n    Channel : 5g44/80\n"


def ping_text(times, sent):
    lines = [f"64 bytes from 1.1.1.1: icmp_seq={i} ttl=64 time={t:.3f} ms" for i, t in enumerate(times) if t is not None]
    return "\n".join(lines) + f"\n\n--- ping statistics ---\n{sent} packets transmitted, {len(lines)} packets received\n"


def series(base, n, spike_share=0.0, loss=0.0, seed=1):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        if rng.random() < loss:
            out.append(None)
        elif rng.random() < spike_share:
            out.append(base + rng.uniform(60, 150))
        else:
            out.append(base + rng.uniform(-0.5, 1.5))
    return out


def watch(rssi, noise=-94, n=50):
    return "\n".join(json.dumps({"t": i, "rssi_dbm": rssi, "noise_dbm": noise, "tx_mbps": 433.0, "phy": 5, "channel": 44,
                                 "band_ghz": "5", "width_mhz": 80, "power_on": True}) for i in range(n))


def shell(rssi=-46, router=None, internet=None, awdl=AWDL_ON, dns=8, cca=2, mcs=9, noise=-94, extra=None, n=50):
    overrides = {"route": ROUTE, "awdl": awdl, "wifi_watch": watch(rssi, noise) if rssi else "",
                 "ping_router": ping_text(router or series(3.6, n), n), "ping_internet": ping_text(internet or series(12, n, seed=2), n),
                 "dns_0": f";; Query time: {dns} msec", "dns_1": f";; Query time: {dns} msec",
                 "wdutil": WDUTIL.format(rssi=rssi, cca=cca, mcs=mcs)}
    overrides.update(extra or {})
    folder = tempfile.mkdtemp()
    return FixtureShell(Path(folder), overrides=overrides)


def diagnose(question, **kw):
    m = network.measure(shell(**kw), "wifi_helper", question)
    return network.report(m, question)


class DiagnosisTests(unittest.TestCase):
    def test_awdl_spikes_named(self):
        r = diagnose("와이파이 왜 이렇게 느려?", router=series(3.6, 50, 0.1), internet=series(12, 50, 0.1, seed=2))
        self.assertIn("awdl_spikes", r.codes())
        self.assertEqual(r.facts["AWDL (AirDrop, Handoff)"], "active")

    def test_spikes_without_awdl_have_no_cause(self):
        r = diagnose("Why is my Wi-Fi slow?", awdl=AWDL_OFF, router=series(3.6, 50, 0.1), internet=series(12, 50, 0.1, seed=2))
        self.assertIn("wifi_spikes", r.codes())
        self.assertNotIn("awdl_spikes", r.codes())

    def test_clean_link_is_fine(self):
        r = diagnose("Is my internet ok?", awdl=AWDL_OFF)
        self.assertEqual(r.codes(), ["network_ok"])

    def test_weak_signal_and_loss_on_the_wifi_segment(self):
        r = diagnose("와이파이 괜찮아?", rssi=-79, noise=-92, router=series(4, 50, loss=0.08), internet=series(14, 50, loss=0.08, seed=2), awdl=AWDL_OFF)
        self.assertIn("signal_low", r.codes())
        self.assertIn("wifi_loss", r.codes())
        self.assertNotIn("internet_problem", r.codes())

    def test_problem_beyond_the_router(self):
        r = diagnose("인터넷이 자꾸 끊겨", awdl=AWDL_OFF, internet=series(150, 50, loss=0.1, seed=3))
        self.assertIn("internet_problem", r.codes())
        self.assertFalse({"wifi_loss", "awdl_spikes", "wifi_spikes"} & set(r.codes()))

    def test_not_connected(self):
        r = diagnose("Why is the Wi-Fi not working?", rssi=None)
        self.assertEqual(r.codes(), ["no_wifi"])

    def test_dns_slow(self):
        self.assertIn("dns_slow", diagnose("웹페이지가 늦게 열려 인터넷 문제야?", awdl=AWDL_OFF, dns=250).codes())

    def test_game_verdicts(self):
        bad = diagnose("온라인 게임 해도 돼?", router=series(3.6, 150, 0.08), internet=series(12, 150, 0.08, seed=2), n=150)
        self.assertIn("use_care", bad.codes())
        self.assertIn("Turning AirDrop", next(f.advice for f in bad.findings if f.code == "use_care"))
        good = diagnose("온라인 게임 해도 돼?", awdl=AWDL_OFF, n=150)
        self.assertIn("use_yes", good.codes())

    def test_call_measures_30_seconds(self):
        m = network.measure(shell(n=150), "wifi_helper", "화상 통화 괜찮을까?")
        self.assertEqual(m.seconds, 30.0)
        self.assertEqual(network.measure(shell(), "wifi_helper", "와이파이 어때?").seconds, 10.0)

    def test_speed_and_load(self):
        nq = json.dumps({"dl_throughput": 200e6, "ul_throughput": 150e6, "responsiveness": 300.0, "base_rtt": 12.0})
        r = diagnose("인터넷 속도 어때? 4K 스트리밍 돼?", awdl=AWDL_OFF, extra={"networkquality": nq})
        self.assertEqual(r.facts["download"], "200.0 Mb/s")
        self.assertIn("latency_under_load", r.codes())
        self.assertIn("4K streaming: yes.", [f.title for f in r.findings])

    def test_bluetooth_signal(self):
        bt = json.dumps({"SPBluetoothDataType": [{"device_connected": [{"Speaker": {"device_minorType": "Speaker", "device_rssi": "-84"}}]}]})
        r = diagnose("블루투스 스피커 신호 괜찮아?", awdl=AWDL_OFF, extra={"bluetooth": bt})
        self.assertIn("bt_weak", r.codes())

    def test_usual_values(self):
        m = network.measure(shell(router=series(40, 50)), "wifi_helper", "와이파이 평소보다 느린가?")
        r = network.report(m, "와이파이 평소보다 느린가?", {"router_median": 3.6, "rssi": -46.6})
        self.assertIn("worse_than_usual", r.codes())


class RouteTests(unittest.TestCase):
    def test_network_questions(self):
        for q in ["와이파이 왜 이렇게 느려?", "롤 할 때 핑 괜찮아?", "온라인 게임 해도 돼?", "인터넷이 자꾸 끊겨",
                  "Why is my Wi-Fi slow?", "Is my internet connection good enough for a video call?", "블루투스 이어폰 신호 괜찮아?"]:
            self.assertEqual(route(q).topic, "network", q)

    def test_not_network(self):
        self.assertEqual(route("Can I play a demanding game now?").topic, "performance")
        self.assertEqual(route("쇼핑하다가 맥이 느려졌어").topic, "performance")
        self.assertIsNone(route("Explain how Wi-Fi works").topic)


if __name__ == "__main__":
    unittest.main()
