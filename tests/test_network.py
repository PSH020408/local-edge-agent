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


def watch(rssi, noise=-94, n=50, band="5"):
    return "\n".join(json.dumps({"t": i, "rssi_dbm": rssi, "noise_dbm": noise, "tx_mbps": 433.0, "phy": 5, "channel": 44 if band == "5" else 11,
                                 "band_ghz": band, "width_mhz": 80 if band == "5" else 20, "power_on": True}) for i in range(n))


def shell(rssi=-46, router=None, internet=None, awdl=AWDL_ON, dns=8, cca=2, mcs=9, noise=-94, extra=None, n=50, band="5"):
    overrides = {"route": ROUTE, "awdl": awdl, "wifi_watch": watch(rssi, noise, band=band) if rssi else "",
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
        self.assertEqual(r.facts["AWDL (AirDrop's radio)"], "active")

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
        # 300 pings: 30 s at 10 a second
        bad = diagnose("온라인 게임 해도 돼?", router=series(3.6, 300, 0.08), internet=series(12, 300, 0.08, seed=2), n=300)
        self.assertIn("use_care", bad.codes())          # spikes alone: "with care" until experiment G1 calibrates
        self.assertIn("Turning AirDrop", next(f.advice for f in bad.findings if f.code == "use_care"))
        lost = diagnose("온라인 게임 해도 돼?", awdl=AWDL_OFF, internet=series(12, 300, loss=0.05, seed=2), n=300)
        self.assertIn("use_not_now", lost.codes())
        good = diagnose("온라인 게임 해도 돼?", awdl=AWDL_OFF, n=300)
        self.assertIn("use_yes", good.codes())

    def test_game_counts_rises_relative_to_usual_ping(self):
        # usual 12 ms with two short jumps to 45-50 ms: no reply above 50 ms, still two rises that lose fights
        internet = series(12, 300, seed=2)
        internet[100:103] = [45.0, 50.0, 23.0]
        internet[200:202] = [47.0, 44.0]
        r = diagnose("롤 지금 해도 돼?", awdl=AWDL_OFF, internet=internet, n=300)
        self.assertIn("use_care", r.codes())
        self.assertIn("2 rises of 20 ms", r.facts["verdict for online games"])
        self.assertIn("beyond the router", r.facts["verdict for online games"])

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


class GameRouteTests(unittest.TestCase):
    def test_any_game_question_about_playing_goes_to_the_network(self):
        from agent.device.router import route
        for q in ("게임 해도 돼?", "지금 게임해도 괜찮아?", "배그 해도 돼?", "피파 온라인 해도 돼?", "메이플 해도 돼?",
                  "오버워치 렉 걸려", "Can I play games now?", "게임 중에 핑 튀어"):
            self.assertEqual(route(q).topic, "network", q)
            self.assertIn("game", network.uses_from_question(q), q)


class RouteTests(unittest.TestCase):
    def test_network_questions(self):
        for q in ["와이파이 왜 이렇게 느려?", "롤 할 때 핑 괜찮아?", "온라인 게임 해도 돼?", "인터넷이 자꾸 끊겨",
                  "Why is my Wi-Fi slow?", "Is my internet connection good enough for a video call?", "블루투스 이어폰 신호 괜찮아?"]:
            self.assertEqual(route(q).topic, "network", q)

    def test_not_network(self):
        self.assertEqual(route("Can I play a demanding game now?").topic, "performance")
        self.assertEqual(route("게임 돌려도 돼?").topic, "performance")         # running it: the Mac's load
        self.assertEqual(route("게임하면 발열 심해?").topic, "performance")
        self.assertEqual(route("쇼핑하다가 맥이 느려졌어").topic, "performance")
        self.assertIsNone(route("Explain how Wi-Fi works").topic)


if __name__ == "__main__":
    unittest.main()


class ConnectionCardTests(unittest.TestCase):
    """The connection card: radio chain, measurements, verdict per use, bottleneck, other networks."""

    def room_c(self, down=120e6, up=40e6):
        def net(ssid, rssi, channel=44, band="5", width=80):
            return {"ssid": ssid, "rssi_dbm": rssi, "channel": channel, "band_ghz": band, "width_mhz": width}
        scan = "\n".join(json.dumps(n) for n in [net("Home-A-5G", -69), net("Home-B-5G", -87), net("Home-C-5G", -44, 149)])
        internet, router = series(13, 300, seed=2), series(3.5, 300)
        internet[100:103], router[100:103] = [45.0, 50.0, 23.0], [36.0, 41.0, 12.0]
        nq = json.dumps({"dl_throughput": down, "ul_throughput": up, "responsiveness": 900.0, "base_rtt": 13.0})
        wd = WDUTIL.format(rssi=-69, cca=3, mcs=6).replace("433", "263") + "    SSID : Home-A-5G\n"
        sh = shell(rssi=-69, internet=internet, router=router, n=300, extra={
            "wifi_scan": scan, "wdutil": wd, "networkquality": nq, "preferred": "Preferred networks on en0:\n\tHome-A-5G\n\tHome-C-5G\n\tHome-B-5G\n"})
        q = "여기서 어떤 와이파이 쓰는 게 좋고 뭐 할 수 있어? 자세히"
        m = network.measure(sh, "wifi_helper", q)
        return m, network.report(m, q)

    def test_card_has_every_part(self):
        _, r = self.room_c()
        card = r.card
        self.assertIn("지금: Home-A-5G", card)
        self.assertIn("64-QAM 3/4 (MCS 6)", card)
        self.assertIn("다운 120 / 업 40 Mb/s", card)
        self.assertIn("스파이크 1회(와이파이 구간)", card)
        self.assertIn("게임 ⚠️", card)
        self.assertIn("화상회의 ✅", card)
        self.assertIn("10 GB 다운 약 11분", card)
        self.assertIn("병목: 와이파이 구간", card)
        self.assertIn('→ "Home-C-5G"로 바꾸면', card)

    def test_bottleneck_beyond_the_router(self):
        m = network.Measurement(router={"received": 100, "loss_percent": 0}, internet={"received": 100, "loss_percent": 0},
                                throughput={"down_mbps": 60.0, "up_mbps": 20.0})
        where, en, ko = network.bottleneck(m, 433.0, 40.0)
        self.assertEqual(where, "line")
        self.assertIn("소용없음", ko)
        self.assertEqual(network.bottleneck(m, 195.0, 18.0)[0], "wifi")

    def test_call_needs_upload_and_downloads_get_a_time(self):
        m = network.Measurement(seconds=30, internet={"received": 300, "median_ms": 12, "p95_ms": 15, "jitter_ms": 2,
                                                       "loss_percent": 0, "rise_events": 0, "rise_share": 0})
        m.throughput = {"down_mbps": 300.0, "up_mbps": 1.0}
        self.assertEqual(network._verdict("video_call", m)[0], "with care")       # 1 Mb/s up: below 1.5 Mb/s
        verdict, why = network._verdict("download", m)
        self.assertEqual(verdict, "yes")
        self.assertIn("10 GB in about 4.4 min down", why)
        self.assertEqual(network.transfer_minutes(10, 120), 11)


class RoomATests(unittest.TestCase):
    """The first real run (Room A, 2026-11-20): wdutil hid the name, AWDL was active, other routers not saved."""

    def test_name_hidden_awdl_active_unsaved_networks(self):
        def net(ssid, rssi, channel=44, band="5", width=80):
            return {"ssid": ssid, "rssi_dbm": rssi, "channel": channel, "band_ghz": band, "width_mhz": width}
        scan = "\n".join(json.dumps(n) for n in [net("Home-A-5G", -46), net("Home-B-5G", -83), net("Home-C-5G", -70, 149)])
        internet, router = series(8, 300, 0.2, seed=2), series(3, 300, 0.2, seed=2)
        nq = json.dumps({"dl_throughput": 194e6, "ul_throughput": 204e6, "responsiveness": 900.0, "base_rtt": 8.0})
        sh = shell(rssi=-50, awdl=AWDL_ON, internet=internet, router=router, n=300, extra={
            "wifi_scan": scan, "networkquality": nq, "wifi_link_named": None,
            "preferred": "Preferred networks on en0:\n\tHome-A-5G\n\tHome-A-2.4G\n"})
        q = "여기서 어떤 와이파이 쓰는 게 좋고 뭐 할 수 있어? 자세히"
        r = network.report(network.measure(sh, "wifi_helper", q), q)
        card = r.card
        self.assertIn("지금: Home-A-5G", card)                   # found by channel and signal
        self.assertNotIn("  Home-A-5G", card)                    # not listed again as another network
        self.assertIn("Home-C-5G (5 GHz ch 149)", card)
        self.assertIn("저장 안 됨", card)
        self.assertIn("원인: AirDrop 무선(AWDL)", card)
        self.assertIn("게임 ⚠️", card)
        self.assertIn("→ 지금 와이파이 유지", card)


class PlainCardTests(unittest.TestCase):
    """The default card is for anyone: no SNR, modulation or AWDL, and the advice in plain words."""

    def test_room_c_in_plain_words(self):
        m, _ = ConnectionCardTests().room_c()
        q = "여기서 어떤 와이파이 쓰는 게 좋고 뭐 할 수 있어?"
        card = network.report(m, q).card
        for jargon in ("SNR", "SINR", "QAM", "MCS", "AWDL", "병목", "링크"):
            self.assertNotIn(jargon, card)
        self.assertIn("와이파이: Home-A-5G · 신호 보통 · 인터넷 속도 받기 120 / 보내기 40 Mb/s", card)
        self.assertIn("게임 ⚠️ 가끔 끊길 수 있음", card)
        self.assertIn('추천: "Home-C-5G"로 바꾸면 더 빨라요', card)


class BluetoothCardTests(unittest.TestCase):
    BT = {"SPBluetoothDataType": [{"controller_properties": {"controller_state": "attrib_on", "controller_chipset": "BCM_4388C2"},
          "device_connected": [{"Mouse": {"device_minorType": "Mouse"}},
                               {"AirPods Pro": {"device_minorType": "Headphones", "device_batteryLevelLeft": "80%",
                                                "device_batteryLevelRight": "15%", "device_rssi": "-62"}}],
          "device_not_connected": [{"Speaker": {"device_minorType": "Speaker"}}, {"MyiPhone": {"device_rssi": "-53"}}]}]}

    def ask(self, q, bt, **kw):
        sh = shell(awdl=AWDL_OFF, extra={"bluetooth": json.dumps(bt)}, **kw)
        return network.report(network.measure(sh, "wifi_helper", q), q)

    def test_devices_battery_and_in_range(self):
        r = self.ask("에어팟 자꾸 끊겨", self.BT)
        self.assertIn("bt_battery_low", r.codes())
        self.assertIn("연결됨: Mouse (마우스), AirPods Pro (헤드폰, 배터리 왼쪽 80% · 오른쪽 15%)", r.card)
        self.assertIn("MyiPhone (기기, 근처에 있음)", r.card)
        self.assertIn("AirPods Pro 배터리가 부족해요", r.card)
        self.assertNotIn("게임", r.card)                      # a Bluetooth question gets a short card

    def test_bluetooth_off(self):
        bt = {"SPBluetoothDataType": [{"controller_properties": {"controller_state": "attrib_off"}}]}
        r = self.ask("블루투스 왜 안 돼?", bt)
        self.assertIn("bt_off", r.codes())
        self.assertIn("블루투스: 꺼져 있어요", r.card)

    def test_shared_band_on_2_4_ghz(self):
        r = self.ask("마우스가 버벅여 블루투스 문제야?", self.BT, band="2.4")
        self.assertIn("bt_shares_band", r.codes())
        self.assertIn("5 GHz 와이파이로 바꾸세요", r.card)


class LiveRunFixTests(unittest.TestCase):
    """Fixes after the live run of 2026-11-21 (N07, N08, N12)."""

    PAIRED = {"SPBluetoothDataType": [{"controller_properties": {"controller_state": "attrib_on"}, "device_connected": [],
              "device_not_connected": [{"Speaker": {"device_minorType": "Speaker"}}, {"Mouse": {"device_minorType": "Mouse"}}]}]}

    def ask(self, q, **kw):
        sh = shell(awdl=AWDL_ON, n=300, router=series(3, 300, 0.15, seed=3), extra={"bluetooth": json.dumps(self.PAIRED)}, **kw)
        return network.report(network.measure(sh, "wifi_helper", q), q)

    def test_airpods_not_paired(self):
        r = self.ask("에어팟 자꾸 끊겨")
        self.assertEqual(r.codes(), ["bt_not_paired"])            # no Wi-Fi spikes in a Bluetooth answer
        self.assertIn("에어팟: 이 맥에 페어링돼 있지 않아요", r.card)

    def test_speaker_paired_not_connected(self):
        r = self.ask("블루투스 스피커 신호 괜찮아?")
        self.assertIn("bt_not_connected", r.codes())
        self.assertIn("Speaker", r.findings[0].title)
        self.assertIn("스피커: 페어링돼 있지만 지금 연결 안 됨", r.card)
        self.assertNotIn("signal", r.facts)                    # the Wi-Fi signal is not offered as the speaker's

    def test_ping_question_gets_the_card(self):
        sh = shell(awdl=AWDL_ON)
        q = "핑 몇이야?"
        r = network.report(network.measure(sh, "wifi_helper", q), q)
        self.assertRegex(r.card, r"핑: 평소 \d+ ms")

    def test_no_handoff_in_the_advice(self):
        sh = shell(awdl=AWDL_ON, n=300, router=series(3, 300, 0.15, seed=3))
        q = "와이파이 왜 이렇게 느려?"
        r = network.report(network.measure(sh, "wifi_helper", q), q)
        self.assertFalse(any("Handoff off" in x.advice or "AirDrop and Handoff" in x.title for x in r.findings))
