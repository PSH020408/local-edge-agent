"""Watch the connection while playing: every latency spike, and whether it came from the Wi-Fi or beyond it.

    sudo -v
    python scripts/game_watch.py --label lol                 # start before a game, Ctrl+C after it
    python scripts/game_watch.py --label lol --awdl off      # the same with AirDrop's radio (AWDL) kept down

Pings the router and an internet server at the same time, 20 times a second with sudo (10 without), samples the
AWDL state every second and the link signal every 2 seconds. A spike is a rise of 20 ms or more above the median
of the last 30 s (agent/device/game_watch.py). Each spike is printed when it happens; a summary comes at the end.
Results: logs/game/<label>_<time>.json.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent.device import game_watch as gw  # noqa: E402
from agent.device.network import awdl_active  # noqa: E402
from agent.device.sources import wifi  # noqa: E402
from wifi_walk import AwdlOff, router_ip, sudo_n  # noqa: E402


class Pinger(threading.Thread):
    def __init__(self, host: str, interval: float, use_sudo: bool, live=None):
        super().__init__(daemon=True)
        self.host, self.interval, self.live = host, interval, live
        self.command = (["sudo", "-n"] if use_sudo else []) + ["ping", "-i", str(interval), "-W", "1000", host]
        self.series, self.proc, self.start_time = gw.Series(), None, None

    def run(self):
        self.proc = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.start_time = time.time()
        for line in self.proc.stdout:
            got = gw.parse_line(line)
            if got:
                seq, ms = got
                t = self.start_time + seq * self.interval          # send time: ping sends on a fixed schedule
                self.series.add(t, ms)
                if self.live:
                    self.live(t, ms)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


class Live:
    """Prints a spike when it starts (rolling 30 s median, as in the final analysis)."""

    def __init__(self, rise: float, interval: float, router: Pinger | None):
        self.window = collections.deque(maxlen=int(gw.WINDOW_S / interval))
        self.rise, self.router, self.in_spike = rise, router, False

    def __call__(self, t: float, ms: float | None):
        base = statistics.median(self.window) if len(self.window) >= 20 else None
        high = base is not None and (ms is None or ms > base + self.rise)
        if high and not self.in_spike:
            r = self.router.series.samples[-1][1] if self.router and self.router.series.samples else None
            what = "lost" if ms is None else f"{ms:.0f} ms (+{ms - base:.0f})"
            print(f"  {datetime.fromtimestamp(t):%H:%M:%S} spike: internet {what}, router {r if r is None else round(r)} ms", flush=True)
        self.in_spike = high
        if ms is not None and not high:
            self.window.append(ms)


def sampler(stop: threading.Event, awdl: list, rssi: list, helper: Path | None):
    last_link = 0.0
    while not stop.wait(1):
        out = subprocess.run(["ifconfig", "awdl0"], capture_output=True, text=True).stdout
        state = awdl_active(out)
        awdl.append((time.time(), bool(state)))
        if helper and time.time() - last_link >= 2:
            last_link = time.time()
            rec = wifi.parse_lines(subprocess.run([str(helper), "link"], capture_output=True, text=True, timeout=10).stdout)
            if rec and rec[0].get("rssi_dbm"):
                rssi.append((time.time(), rec[0]["rssi_dbm"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default="game")
    ap.add_argument("--minutes", type=float, help="stop after this long (default: Ctrl+C)")
    ap.add_argument("--target", default="1.1.1.1", help="internet server to ping (default 1.1.1.1)")
    ap.add_argument("--rise", type=float, default=gw.RISE_MS, help="ms above the usual ping that counts as a spike")
    ap.add_argument("--awdl", choices=["leave", "off"], default="leave", help="keep AWDL down during the watch")
    args = ap.parse_args()

    use_sudo = sudo_n("true").returncode == 0
    interval = 0.05 if use_sudo else 0.1
    if args.awdl == "off" and not use_sudo:
        sys.exit("--awdl off needs `sudo -v` first.")
    try:
        helper = wifi.helper(ROOT)
    except Exception:  # noqa: BLE001 - the signal is optional
        helper = None
    gateway = router_ip()
    router = Pinger(gateway, interval, use_sudo) if gateway else None
    internet = Pinger(args.target, interval, use_sudo, Live(args.rise, interval, router))
    stop, awdl, rssi = threading.Event(), [], []
    print(f"Watching: router {gateway}, internet {args.target}, {1 / interval:.0f} pings/s each, spikes of +{args.rise:.0f} ms. "
          f"AWDL {'kept down' if args.awdl == 'off' else 'left as it is'}. Ctrl+C to stop.", flush=True)

    awdl_ctx = AwdlOff() if args.awdl == "off" else None
    if awdl_ctx:
        awdl_ctx.__enter__()
    try:
        for p in (router, internet):
            if p:
                p.start()
        threading.Thread(target=sampler, args=(stop, awdl, rssi, helper), daemon=True).start()
        end = time.monotonic() + args.minutes * 60 if args.minutes else None
        while end is None or time.monotonic() < end:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        for p in (router, internet):
            if p:
                p.stop()
        if awdl_ctx:
            awdl_ctx.__exit__(None, None, None)
        time.sleep(0.3)

    print("\nAnalysing ...", flush=True)
    events = gw.spikes(internet.series, args.rise)
    gw.attribute(events, router.series if router else gw.Series(), args.rise, awdl, rssi)
    s = gw.summary(internet.series, events)
    s["router_median_ms"] = round(statistics.median([ms for _, ms in router.series.samples if ms is not None]), 1) if router and router.series.samples else None
    print(gw.explain(s))
    out = ROOT / "logs" / "game" / f"{re.sub(r'[^A-Za-z0-9]+', '-', args.label)}_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "label": args.label, "target": args.target, "gateway": gateway, "interval_s": interval, "rise_ms": args.rise,
        "awdl_mode": args.awdl, "summary": s,
        "spikes": [{**e.__dict__, "rise_ms": e.rise_ms} for e in events],
        "internet": internet.series.samples, "router": router.series.samples if router else [],
        "awdl": awdl, "rssi": rssi}))
    print(f"Saved: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
