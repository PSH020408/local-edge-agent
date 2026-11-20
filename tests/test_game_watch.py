"""Game watch: spikes relative to the usual ping, where they came from, and the verdict (no Mac needed)."""

import random
import unittest

from agent.device import game_watch as gw


def session(minutes=3, base=12.0, router_base=3.0, wifi_at=(), beyond_at=(), lost_at=(), hz=10, seed=1):
    """Pings at `hz`; spikes of 45 -> 50 -> 23 ms (the pattern seen in play) at the given seconds."""
    rng = random.Random(seed)
    internet, router = gw.Series(), gw.Series()
    for k in range(int(minutes * 60 * hz)):
        t = k / hz
        i, r = base + rng.uniform(-1.5, 2.5), router_base + rng.uniform(-0.5, 1.0)
        for start in (*wifi_at, *beyond_at):
            if start <= t < start + 0.3:
                i = (45.0, 50.0, 23.0)[min(2, round((t - start) * hz))]
                if start in wifi_at:
                    r = i - base + router_base
        internet.add(t, None if any(s <= t < s + 0.1 for s in lost_at) else i)
        router.add(t, r)
    return internet, router


class GameWatchTests(unittest.TestCase):
    def test_parse_ping_lines(self):
        self.assertEqual(gw.parse_line("64 bytes from 1.1.1.1: icmp_seq=7 ttl=57 time=11.482 ms"), (7, 11.482))
        self.assertEqual(gw.parse_line("Request timeout for icmp_seq 8"), (8, None))
        self.assertIsNone(gw.parse_line("PING 1.1.1.1 (1.1.1.1): 56 data bytes"))

    def test_spikes_are_relative_to_the_usual_ping(self):
        internet, _ = session(wifi_at=(40, 100), beyond_at=(150,))
        events = gw.spikes(internet)
        self.assertEqual(len(events), 3)
        self.assertTrue(all(e.peak_ms == 50.0 for e in events))
        self.assertTrue(all(30 <= e.rise_ms <= 40 for e in events))     # +35 ms over the usual 12-15 ms

    def test_a_45_ms_spike_is_missed_by_a_50_ms_limit(self):
        internet, _ = session(wifi_at=(40,))
        times = [ms for _, ms in internet.samples]
        self.assertEqual(sum(t > 50 for t in times), 0)                   # the old absolute rule saw nothing
        self.assertEqual(len(gw.spikes(internet)), 1)

    def test_where_each_spike_came_from(self):
        internet, router = session(wifi_at=(40, 100), beyond_at=(150,))
        events = gw.spikes(internet)
        awdl = [(float(t), 30 <= t <= 50 or 105 <= t <= 106) for t in range(180)]   # woken twice; the second wake seen 5 s late
        gw.attribute(events, router, awdl=awdl)
        self.assertEqual([e.segment for e in events], ["wifi", "wifi", "beyond router"])
        self.assertEqual([e.awdl for e in events], [True, True, False])
        s = gw.summary(internet, events)
        self.assertEqual((s["on_wifi"], s["beyond_router"], s["with_awdl_active"]), (2, 1, 2))
        self.assertIn("AWDL off", gw.explain(s))

    def test_verdicts(self):
        calm, _ = session(minutes=6)
        self.assertEqual(gw.summary(calm, gw.spikes(calm))["verdict"], "smooth")
        some, _ = session(minutes=3, wifi_at=(40, 100))
        self.assertEqual(gw.summary(some, gw.spikes(some))["verdict"], "occasional")
        many, _ = session(minutes=2, wifi_at=tuple(range(35, 120, 8)))
        self.assertEqual(gw.summary(many, gw.spikes(many))["verdict"], "spiky")

    def test_lost_replies_count_as_spikes(self):
        internet, _ = session(lost_at=(60,))
        events = gw.spikes(internet)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].lost, 1)
        self.assertIsNone(events[0].rise_ms)


if __name__ == "__main__":
    unittest.main()
