"""Memory: size, how much is available, what holds it, compression and swap.

macOS keeps unused memory filled with file caches on purpose, so "free" memory is always small
(here 0.3 GB of 24 GB) and says little. What shows a shortage:

- the available percentage that `memory_pressure` reports (free plus memory that can be reclaimed),
- memory held by the compressor (macOS compresses memory before it swaps),
- swap: space used on the SSD, and the swap-in / swap-out counters. The counters only grow since
  start-up; the diagnosis looks at how fast they grow between samples, not at their size.

`vm_stat` counts pages; the page size is in its first line (16 KB on Apple silicon).
"""

from __future__ import annotations

import re

from ..readings import Reading, now, reading

_MB = 1024 * 1024


def _pages(name: str, text: str) -> int | None:
    found = re.search(rf'^"?{re.escape(name)}"?:\s+(\d+)\.?\s*$', text, re.M)
    return int(found.group(1)) if found else None


def parse_vm_stat(text: str, time: str | None = None) -> list[Reading]:
    time = time or now()
    size = re.search(r"page size of (\d+) bytes", text)
    page = int(size.group(1)) if size else None

    def as_bytes(name: str):
        count = _pages(name, text)
        return count * page if count is not None and page else None

    return [
        reading("memory.free", as_bytes("Pages free"), "bytes", time),
        reading("memory.wired", as_bytes("Pages wired down"), "bytes", time),
        reading("memory.app", as_bytes("Anonymous pages"), "bytes", time),
        reading("memory.file_cache", as_bytes("File-backed pages"), "bytes", time),
        reading("memory.compressed", as_bytes("Pages occupied by compressor"), "bytes", time),
        reading("memory.swapins", _pages("Swapins", text), "count", time),
        reading("memory.swapouts", _pages("Swapouts", text), "count", time),
    ]


def parse_pressure(text: str, time: str | None = None) -> list[Reading]:
    time = time or now()
    found = re.search(r"memory free percentage:\s*(\d+)%", text)
    return [reading("memory.available", int(found.group(1)) if found else None, "%", time)]


def parse_sysctl(text: str, time: str | None = None) -> list[Reading]:
    time = time or now()
    total = re.search(r"hw\.memsize:\s*(\d+)", text)
    swap = re.search(r"vm\.swapusage:\s*total = ([\d.]+)M\s+used = ([\d.]+)M", text)
    return [
        reading("memory.total", int(total.group(1)) if total else None, "bytes", time),
        reading("memory.swap_total", round(float(swap.group(1)) * _MB) if swap else None, "bytes", time),
        reading("memory.swap_used", round(float(swap.group(2)) * _MB) if swap else None, "bytes", time),
    ]


def read(shell) -> list[Reading]:
    time = now()
    out = {name: shell.run(name) for name in ("vm_stat", "memory_pressure", "sysctl")}
    text = {name: o.text if o.ok else "" for name, o in out.items()}
    return parse_sysctl(text["sysctl"], time) + parse_vm_stat(text["vm_stat"], time) + parse_pressure(text["memory_pressure"], time)
