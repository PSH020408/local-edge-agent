"""Answer examples for the repository, taken from live run reports, with private names replaced.

    python scripts/export_examples.py logs/device_runs/run_A.md logs/device_runs/run_B.md \
        --map logs/home/redact.json --out docs/examples/network.md

Every answer is copied as the agent gave it; only names are changed. The map (private, in logs/) lists the
replacements, e.g. {"curi6 5G": "Home-A-5G", "MyPhoneName": "iPhone"}; matching ignores case. Lines of the card
that name a Wi-Fi network not in the map (a neighbour's) are left out, and IP addresses are removed. When a case
is in several reports, the latest report wins.
"""

from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASE = re.compile(r"\n## (\w+) — (.*?)\n(.*?)(?=\n## |\Z)", re.S)
NETWORK_LINE = re.compile(r"^\s+(\S[^(]*?) \((?:2\.4|5) GHz ch \d+\)")


def redact(text: str, mapping: dict[str, str]) -> str:
    known = {v.lower() for v in mapping.values()}
    for old, new in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(r"(?<![A-Za-z0-9])" + re.escape(old) + r"(?![A-Za-z0-9])", new, text, flags=re.I)
    text = re.sub(r"\b\d{1,3}(\.\d{1,3}){3}\b", "<router>", text)
    lines = []
    for line in text.splitlines():
        m = NETWORK_LINE.match(line)
        if m and m.group(1).strip().lower() not in known:
            continue                                   # a neighbour's network
        lines.append(line)
    return "\n".join(lines)


def cases(report: Path) -> dict[str, dict]:
    text = report.read_text(encoding="utf-8")
    out = {}
    for cid, question, body in CASE.findall(text):
        answer = re.search(r"### Answer\n\n(.*?)(?=\n### |\Z)", body, re.S)
        timing = re.search(r"'total': ([\d.]+)", body)
        route = re.search(r"\*\*Route:\*\* (\w+)", body)
        out[cid] = {"question": question.strip(), "answer": answer.group(1).strip() if answer else "",
                    "seconds": float(timing.group(1)) if timing else None, "route": route.group(1) if route else "",
                    "run": report.stem}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reports", nargs="+", type=Path)
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "examples" / "network.md")
    ap.add_argument("--only", help="case ids in the order to show, e.g. N10,N11,N14")
    args = ap.parse_args()
    mapping = json.loads(args.map.read_text())
    merged: dict[str, dict] = {}
    for report in sorted(args.reports):
        merged.update(cases(report))
    notes = {c["id"]: c.get("note", "") for c in tomllib.loads((ROOT / "evals" / "device" / "cases.toml").read_text())["case"]}
    order = args.only.split(",") if args.only else sorted(merged)
    lines = ["# Network agent: answers from live runs", "",
             "Questions asked to the agent on the MacBook, answered from what it measured at that moment (Wi-Fi link,",
             "pings to the router and the internet, speed test, scan, Bluetooth). Copied from the run reports as given;",
             "only the names of the home's networks and devices are replaced, and neighbours' networks left out.",
             "The first block of each answer is the card built by code; the text after it is written by the local",
             "model (qwen3:4b-instruct) from the same measurements, with every number checked against them.", ""]
    for cid in order:
        c = merged.get(cid)
        if not c or not c["answer"]:
            continue
        lines += [f"## {redact(c['question'], mapping)}", "",
                  f"Route: {c['route']} · {c['seconds']:.0f} s · case {cid}, {c['run']}" + (f" · {notes[cid]}" if notes.get(cid) else ""), "",
                  "```text", redact(c["answer"], mapping), "```", ""]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.out.relative_to(ROOT)} ({len(order)} cases)")


if __name__ == "__main__":
    main()
