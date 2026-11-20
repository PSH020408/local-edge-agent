"""Experiment C1: which Continuity feature wakes AWDL and makes the Wi-Fi latency spike.

    sudo -v
    python scripts/continuity_test.py                 # 6 rounds of 3 minutes, about 20 minutes
    python scripts/continuity_test.py --minutes 2
    python scripts/continuity_test.py --feature widgets --repeat 2   # off, on, off, on: one feature, repeated

Rounds: all off, then each feature on alone (AirDrop, Handoff, iPhone widgets and mirroring, AirPlay Receiver),
then all off again. Before each round the script says what to switch in System Settings > General > AirDrop &
Handoff and waits for Enter. During a round, use the iPhone as usual (Discord, switching apps, copying text).
AWDL is left alone (not forced down), sampled every 0.5 s; the router and an internet server are pinged
20 times a second (10 without sudo). Settings are read before each round, so the keys that change with each
switch are recorded too (agent/device/sources/continuity.py).
Results: logs/continuity/c1_<time>.json and a table.
"""

from __future__ import annotations

import argparse
import json
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
from agent.device.shell import LiveShell  # noqa: E402
from agent.device.sources import continuity  # noqa: E402
from game_watch import Pinger  # noqa: E402
from wifi_walk import router_ip, sudo_n  # noqa: E402

ROUNDS = [
    ("all off", "AirDrop: 없음, Handoff: 끔, iPhone 위젯: 끔, AirPlay 수신 모드: 끔"),
    ("airdrop", "AirDrop만 '연락처만'으로 켜기 (나머지 셋은 끈 채로)"),
    ("handoff", "AirDrop은 '없음'으로 되돌리고, Handoff만 켜기"),
    ("widgets", "Handoff는 끄고, iPhone 위젯만 켜기"),
    ("airplay", "iPhone 위젯은 끄고, AirPlay 수신 모드만 켜기"),
    ("all off again", "AirPlay 수신 모드도 끄기 (넷 다 꺼진 상태)"),
]


def run_round(minutes: float, interval: float, use_sudo: bool, gateway: str) -> dict:
    router, internet = Pinger(gateway, interval, use_sudo), Pinger("1.1.1.1", interval, use_sudo)
    stop, awdl, packets = threading.Event(), [], []

    def sample():
        while not stop.wait(0.5):
            awdl.append((time.time(), bool(awdl_active(subprocess.run(["ifconfig", "awdl0"], capture_output=True, text=True).stdout))))
            count = continuity.awdl_packets(subprocess.run(["netstat", "-I", "awdl0"], capture_output=True, text=True).stdout)
            if count is not None:
                packets.append((time.time(), count))

    router.start(); internet.start()
    threading.Thread(target=sample, daemon=True).start()
    end = time.monotonic() + minutes * 60
    while time.monotonic() < end:
        left = int(end - time.monotonic())
        print(f"\r  측정 중 ... {left // 60}:{left % 60:02d} 남음 (폰을 평소처럼 쓰세요)  ", end="", flush=True)
        time.sleep(1)
    stop.set(); router.stop(); internet.stop()
    time.sleep(0.3)
    print()
    events = gw.spikes(internet.series)
    gw.attribute(events, router.series, awdl=awdl)
    s = gw.summary(internet.series, events)
    r_ms = sorted(ms for _, ms in router.series.samples if ms is not None)
    base = statistics.median(r_ms) if r_ms else None
    span = packets[-1][0] - packets[0][0] if len(packets) > 1 else 0
    s.update(awdl_packets_per_s=round((packets[-1][1] - packets[0][1]) / span, 1) if span else None,
             awdl_wakes=continuity.awdl_wakes(awdl), awdl_active_share=round(sum(a for _, a in awdl) / max(1, len(awdl)), 3),
             router_median_ms=round(base, 1) if base else None,
             router_p99_ms=round(r_ms[int(0.99 * (len(r_ms) - 1))], 1) if r_ms else None,
             router_max_ms=round(r_ms[-1], 1) if r_ms else None,
             router_risen=sum(ms > base + gw.RISE_MS for ms in r_ms) if r_ms else None,
             router_late_percent=round(100 * sum(ms > base + gw.RISE_MS for ms in r_ms) / len(r_ms), 1) if r_ms else None)
    return {"summary": s, "spikes": [{**e.__dict__, "rise_ms": e.rise_ms} for e in events], "awdl": awdl, "awdl_packets": packets,
            "internet": internet.series.samples, "router": router.series.samples}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minutes", type=float, default=3.0)
    ap.add_argument("--feature", choices=list(continuity.FEATURES), help="test one feature: off, on, off, on ...")
    ap.add_argument("--repeat", type=int, default=2, help="pairs for --feature (default 2)")
    args = ap.parse_args()
    rounds = ROUNDS
    if args.feature:
        name = continuity.FEATURES_KO[args.feature]
        rounds = [("off", f"{name} 끄기 (나머지 셋도 끈 채로)"), (args.feature, f"{name}만 켜기")] * args.repeat
    use_sudo = sudo_n("true").returncode == 0
    interval = 0.05 if use_sudo else 0.1
    gateway = router_ip()
    if not gateway:
        sys.exit("No router: join the Wi-Fi first.")
    shell = LiveShell()
    print(f"C1: {len(rounds)} rounds of {args.minutes:g} min, {1 / interval:.0f} pings/s. 설정 위치: {continuity.SETTINGS_PATH_KO}\n")
    record = {"time": datetime.now().isoformat(timespec="seconds"), "minutes": args.minutes, "interval_s": interval, "rounds": []}
    previous = None
    for key, instruction in rounds:
        input(f"[{key}] {instruction}\n  설정을 바꿨으면 Enter ")
        use_sudo = sudo_n("true").returncode == 0           # the password may have expired while waiting
        interval = 0.05 if use_sudo else 0.1
        dumps = continuity.read(shell)
        changed = continuity.diff(previous, dumps) if previous is not None else []
        previous = dumps
        result = run_round(args.minutes, interval, use_sudo, gateway)
        s = result["summary"]
        print(f"  AWDL packets/s {s['awdl_packets_per_s']}, spikes {s['spikes']}, late {s['router_late_percent']}%, "
              f"router p99 {s['router_p99_ms']} ms, max {s['router_max_ms']} ms\n")
        record["rounds"].append({"round": key, "settings_read": continuity.features(dumps), "changed_keys": changed, **result})

    print(f"{'round':14} {'AWDL pkt/s':>10} {'late %':>7} {'spikes':>7} {'per min':>7} {'router p99':>10} {'router max':>10}")
    for r in record["rounds"]:
        s = r["summary"]
        print(f"{r['round']:14} {str(s['awdl_packets_per_s']):>10} {s['router_late_percent']:>6}% {s['spikes']:>7} {s['spikes_per_min']:>7} "
              f"{s['router_p99_ms']:>9} ms {s['router_max_ms']:>9} ms")
    print("\nSettings keys that changed at each switch:")
    for r in record["rounds"][1:]:
        keys = ", ".join(f"{d}.{k}: {a} -> {b}" for d, k, a, b in r["changed_keys"][:6]) or "none found"
        print(f"  {r['round']:14} {keys}")
    out = ROOT / "logs" / "continuity" / f"c1_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, default=str))
    print(f"\nSaved: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
