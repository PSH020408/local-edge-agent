"""Two walks compared point by point: router on the floor against raised, or the Mac on 5 GHz against 2.4 GHz.

    python scripts/coverage_compare.py logs/home/walk_floor-5g_<time>.jsonl logs/home/walk_raised-5g_<time>.jsonl

Only points measured in both walks are compared (paired), so the rooms and distances are the same and the
difference is the condition. For each quantity: the mean difference (B - A), how many points rose, and a
one-sided sign test of "B is higher".
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYS = [("rssi", "link signal dBm"), ("snr", "SNR dB"), ("scan_5", "5 GHz beacon dBm"), ("scan_24", "2.4 GHz beacon dBm"),
        ("bt", "Bluetooth dBm"), ("nss", "spatial streams"), ("mcs", "MCS"), ("tx_mbps", "link rate Mb/s"),
        ("p95", "router p95 ms"), ("down", "download Mb/s")]


def load(path: str) -> dict:
    rows = [json.loads(l) for l in (ROOT / path).read_text(encoding="utf-8").splitlines()]
    out = {}
    for r in rows:
        if "id" in r:
            r["p95"] = r.get("latency", {}).get("p95_ms")
            r["down"] = (r.get("throughput") or {}).get("down_mbps")
            out[r["id"]] = r
    return out


def sign_test(wins: int, n: int) -> float:
    """P(at least `wins` of n by chance), ties left out."""
    return sum(math.comb(n, k) for k in range(wins, n + 1)) / 2 ** n if n else 1.0


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    a, b = load(sys.argv[1]), load(sys.argv[2])
    common = [pid for pid in a if pid in b]
    name_a, name_b = (a[common[0]].get("condition", "A"), b[common[0]].get("condition", "B")) if common else ("A", "B")
    lines = [f"# {name_b} against {name_a}", "", f"{len(common)} points measured in both.", "",
             "| Quantity | Points | Mean A | Mean B | Mean B − A | Points higher in B | Sign test p |", "|---|---|---|---|---|---|---|"]
    for key, label in KEYS:
        pairs = [(a[p][key], b[p][key]) for p in common if a[p].get(key) is not None and b[p].get(key) is not None]
        if not pairs:
            continue
        diffs = [y - x for x, y in pairs]
        nonzero = [d for d in diffs if d != 0]
        wins = sum(d > 0 for d in nonzero)
        lines.append(f"| {label} | {len(pairs)} | {statistics.fmean(x for x, _ in pairs):.1f} | {statistics.fmean(y for _, y in pairs):.1f} | "
                     f"{statistics.fmean(diffs):+.1f} | {wins} of {len(nonzero)} | {sign_test(wins, len(nonzero)):.3f} |")
    lines += ["", "| Point | Distance m | Walls | " + " | ".join(f"{l} A / B" for _, l in KEYS[:2] + KEYS[5:8] + KEYS[9:]) + " |",
              "|---|---|---|" + "---|" * len(KEYS[:2] + KEYS[5:8] + KEYS[9:])]
    for p in common:
        cells = [f"{a[p].get(k)} / {b[p].get(k)}" for k, _ in KEYS[:2] + KEYS[5:8] + KEYS[9:]]
        lines.append(f"| {p} | {a[p]['distance_m']} | {a[p]['walls']} | " + " | ".join(cells) + " |")
    out = ROOT / "logs" / "home" / f"compare_{name_a}_vs_{name_b}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines) + f"\n\nSaved: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
