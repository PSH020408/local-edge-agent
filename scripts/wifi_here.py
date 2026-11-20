"""Which Wi-Fi is best at this place, and what each one can carry: join the strong networks in turn, measure
everything on each, and compare them side by side.

    sudo -v
    python scripts/wifi_here.py --label "Room C" --quick     # the joined network measured, the others predicted
    python scripts/wifi_here.py --label "Room C"             # join and measure the strong networks (about 1 min each)

For each network: signal -> SNR (SINR) -> modulation (MCS) -> link rate; download and upload; the usual ping, spikes
of 20 ms or more and where they start; a verdict for games, calls, messaging, 4K and the time for 10 GB
(agent/device/network.py). The others heard here are ranked from the scan first (agent/device/wifi_choice.py);
networks expected to be much worse than the best are not joined. At the end the Mac stays on the recommended
network (or goes back with --return). Each join drops the connection for a few seconds: not during a call.
Results: logs/home/here_<label>_<time>.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent.device import network, wifi_choice  # noqa: E402
from agent.device.shell import LiveShell  # noqa: E402
from agent.device.sources import wifi  # noqa: E402
from wifi_trial import join, wifi_device  # noqa: E402
from wifi_walk import AwdlOff, sudo_n  # noqa: E402

FULL_QUESTION = "여기서 어떤 와이파이 쓰는 게 좋고 뭐 할 수 있어?"          # scan + every use + speed test
MEASURE_QUESTION = "online game, video call, messaging, 4k stream, download speed"   # every use + speed, no scan
USES = ["game", "video_call", "messaging", "streaming", "download"]
SCORE = {"yes": 2, "with care": 1, "not now": 0, "not measured": 0}


def row(name: str, m: network.Measurement, joined: bool = True) -> dict:
    link = [s for s in m.link if s.get("rssi_dbm")]
    d, t, it = m.driver or {}, m.throughput or {}, m.internet or {}
    signal = round(sum(s["rssi_dbm"] for s in link) / len(link), 1) if link else None
    noise = link[0].get("noise_dbm") if link else None
    verdicts = {u: network._verdict(u, m) for u in USES}
    return {"ssid": name, "joined": joined, "signal": signal, "snr": round(signal - noise, 1) if signal and noise else None,
            "mcs": d.get("mcs"), "modulation": wifi_choice.modulation(d.get("mcs")), "link": d.get("tx_mbps") or (link[0].get("tx_mbps") if link else None),
            "band": link[0].get("band_ghz") if link else None, "channel": link[0].get("channel") if link else None,
            "down": t.get("down_mbps"), "up": t.get("up_mbps"), "ping": it.get("median_ms"), "spikes": it.get("rise_events"),
            "loss": it.get("loss_percent"), "where": network._rise_where(m),
            "verdicts": {u: v for u, (v, _) in verdicts.items()}, "why": {u: w for u, (_, w) in verdicts.items()},
            "ten_gb_min": network.transfer_minutes(10, t.get("down_mbps"))}


def score(r: dict) -> tuple:
    return (sum(SCORE[r["verdicts"][u]] for u in USES), -(r["spikes"] or 0), r["down"] or 0)


def table(rows: list[dict]) -> str:
    mark = network.VERDICT_MARK
    head = f"{'와이파이':12} {'신호':>6} {'SNR':>4} {'변조 (MCS)':18} {'링크':>5} {'다운/업 Mb/s':>12} {'핑':>4} {'스파이크':>6}  게임 화상 메신저 4K  10GB"
    lines = [head, "-" * len(head)]
    for r in rows:
        mod = f"{r['modulation']} ({int(r['mcs'])})" if r["mcs"] is not None else "-"
        speed = f"{r['down']:.0f}/{r['up']:.0f}" if r["down"] is not None else "-"
        v = r["verdicts"]
        lines.append(f"{r['ssid'][:12]:12} {r['signal'] or 0:>6.0f} {r['snr'] or 0:>4.0f} {mod:18} {r['link'] or 0:>5.0f} {speed:>12} "
                     f"{r['ping'] or 0:>4.0f} {r['spikes'] or 0:>6}   {mark[v['game']]}   {mark[v['video_call']]}   {mark[v['messaging']]}   "
                     f"{mark[v['streaming']]}  {r['ten_gb_min']}분")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default="here")
    ap.add_argument("--quick", action="store_true", help="measure the joined network only; predict the others")
    ap.add_argument("--max", type=int, default=3, help="networks to measure at most, the joined one included")
    ap.add_argument("--return", dest="go_back", action="store_true", help="go back to the starting network at the end")
    ap.add_argument("--awdl", choices=["leave", "off"], default="leave", help="keep AWDL down while measuring")
    args = ap.parse_args()

    if sudo_n("true").returncode != 0:
        sys.exit("Run `sudo -v` first (modulation and the network's name come from wdutil).")
    shell, helper, device = LiveShell(), str(wifi.helper(ROOT)), wifi_device()
    awdl = AwdlOff() if args.awdl == "off" else None
    if awdl:
        awdl.__enter__()
    try:
        print("지금 연결된 와이파이 측정 중 (약 1분: 핑 30초, 속도 테스트, 주변 스캔) ...", flush=True)
        m0 = network.measure(shell, helper, FULL_QUESTION)
        r0 = network.report(m0, FULL_QUESTION)
        print("\n" + r0.card + "\n", flush=True)
        start = (m0.driver or {}).get("ssid")
        rows = [row(start or "joined", m0)]
        first = m0.link[0] if m0.link else {}
        cands = wifi_choice.candidates(m0.scan, first.get("noise_dbm") or -93, first.get("width_mhz") or 80, m0.known or None, start)
        record = {"label": args.label, "time": datetime.now().isoformat(timespec="seconds"), "start": start,
                  "candidates": [{**c.__dict__, "mcs": c.mcs} for c in cands], "card": r0.card}
        if not args.quick and cands:
            best_rate = max(c.rate for c in cands)
            todo = [c for c in cands if not c.current and c.rate >= 0.5 * best_rate and c.sinr >= 15][:max(0, args.max - 1)]
            on = start
            for c in todo:
                print(f"- {c.ssid}: 연결 중 ...", flush=True)
                ok, seconds, text = join(device, c.ssid)
                if not ok:
                    print(f"  연결 실패: {text[:100]}")
                    continue
                on = c.ssid
                print(f"  {seconds:.0f}초 만에 연결, 측정 중 (약 1분) ...", flush=True)
                m = network.measure(shell, helper, MEASURE_QUESTION)
                rows.append(row(c.ssid, m))
            print("\n" + table(rows))
            best = max(rows, key=score)
            print(f"\n추천: {best['ssid']} (게임 {network.VERDICT_KO[best['verdicts']['game']]}, 화상회의 "
                  f"{network.VERDICT_KO[best['verdicts']['video_call']]}, 4K {network.VERDICT_KO[best['verdicts']['streaming']]}, "
                  f"10 GB 약 {best['ten_gb_min']}분)")
            for u, ko in (("game", "게임"), ("download", "큰 파일")):
                top = max(rows, key=lambda r: (SCORE[r["verdicts"][u]], -(r["spikes"] or 0) if u == "game" else (r["down"] or 0)))
                if top["ssid"] != best["ssid"] and SCORE[top["verdicts"][u]] > SCORE[best["verdicts"][u]]:
                    print(f"  {ko}만 보면: {top['ssid']}")
            target = start if args.go_back else best["ssid"]
            if target and target != on:
                print(f"{target}에 다시 연결 ...", flush=True)
                ok, _, text = join(device, target)
                if not ok:
                    print(f"  연결 실패 ({text[:80]}): Wi-Fi 메뉴에서 {target}을 선택하세요.")
            record["recommended"] = best["ssid"]
        record["rows"] = rows
    finally:
        if awdl:
            awdl.__exit__(None, None, None)
    out = ROOT / "logs" / "home" / f"here_{re.sub(r'[^A-Za-z0-9]+', '-', args.label).strip('-')}_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, default=str))
    print(f"Saved: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
