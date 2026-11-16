"""CPU and GPU load: core counts, CPU use, load average, the busiest processes, GPU use.

- CPU use comes from `top`, which samples twice one second apart: the first sample is the average
  since start-up, so only the second one is "now".
- The busiest process comes from `ps` (about 30 ms, cheap enough for the background sampler);
  the energy ranking comes from `top -o power` (about 1.2 s, for questions only). Energy impact is
  a relative score macOS computes, not watts.
- GPU use comes from the graphics driver's statistics in the I/O registry, readable without rights.
"""

from __future__ import annotations

import re

from ..readings import Reading, now, reading


def _number(pattern: str, text: str, cast=float):
    found = re.search(pattern, text)
    return cast(found.group(1)) if found else None


def parse_sysctl(text: str, time: str | None = None) -> list[Reading]:
    time = time or now()
    load = re.search(r"vm\.loadavg:\s*\{\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)", text)
    return [
        reading("cpu.cores", _number(r"hw\.ncpu:\s*(\d+)", text, int), "count", time),
        reading("cpu.performance_cores", _number(r"hw\.perflevel0\.physicalcpu:\s*(\d+)", text, int), "count", time),
        reading("cpu.efficiency_cores", _number(r"hw\.perflevel1\.physicalcpu:\s*(\d+)", text, int), "count", time),
        reading("cpu.load_1m", float(load.group(1)) if load else None, "count", time),
        reading("cpu.load_5m", float(load.group(2)) if load else None, "count", time),
        reading("cpu.load_15m", float(load.group(3)) if load else None, "count", time),
    ]


def parse_top(text: str, time: str | None = None, keep: int = 3) -> list[Reading]:
    """CPU use (user + system) from the last sample, and the top processes by energy impact."""
    time = time or now()
    usage = re.findall(r"CPU usage:\s*([\d.]+)% user,\s*([\d.]+)% sys", text)
    readings = [reading("cpu.usage", round(float(usage[-1][0]) + float(usage[-1][1]), 2) if usage else None, "%", time)]
    last_table = text.rsplit("PID", 1)[-1] if "PID" in text else ""
    rows = re.findall(r"^\d+\s+(.+?)\s+([\d.]+)\s+([\d.]+)\s*$", last_table, re.M)
    for rank in range(1, keep + 1):
        name, cpu, energy = rows[rank - 1] if rank <= len(rows) else (None, None, None)
        readings += [
            reading(f"process.energy{rank}_name", name, "text", time),
            reading(f"process.energy{rank}_cpu", float(cpu) if cpu else None, "%", time),
            reading(f"process.energy{rank}_impact", float(energy) if energy else None, "score", time),
        ]
    return readings


def parse_ps(text: str, time: str | None = None) -> list[Reading]:
    """The busiest process now; above 100% means more than one core."""
    time = time or now()
    rows = [(float(m.group(1)), m.group(2).strip().rsplit("/", 1)[-1])
            for m in re.finditer(r"^\s*([\d.]+)\s+[\d.]+\s+(\S.*)$", text, re.M)]
    cpu, name = max(rows) if rows else (None, None)
    total = round(sum(c for c, _ in rows), 1) if rows else None  # % of one core, summed over processes
    return [reading("process.max_cpu", cpu, "%", time), reading("process.max_cpu_name", name, "text", time),
            reading("process.total_cpu", total, "%", time)]


def parse_gpu(text: str, time: str | None = None) -> list[Reading]:
    time = time or now()
    return [
        reading("gpu.usage", _number(r'"Device Utilization %"\s*=\s*(\d+)', text, int), "%", time),
        reading("gpu.renderer_usage", _number(r'"Renderer Utilization %"\s*=\s*(\d+)', text, int), "%", time),
        reading("gpu.tiler_usage", _number(r'"Tiler Utilization %"\s*=\s*(\d+)', text, int), "%", time),
        reading("gpu.memory_in_use", _number(r'"In use system memory"\s*=\s*(\d+)', text, int), "bytes", time),
        reading("gpu.cores", _number(r'"gpu-core-count"\s*=\s*(\d+)', text, int), "count", time),
    ]


def read(shell) -> list[Reading]:
    """Fast readings for the background sampler (sysctl, ps, the GPU registry: under 0.1 s)."""
    time = now()
    out = {name: shell.run(name) for name in ("sysctl", "ps_cpu", "gpu_ioreg")}
    text = {name: o.text if o.ok else "" for name, o in out.items()}
    return parse_sysctl(text["sysctl"], time) + parse_ps(text["ps_cpu"], time) + parse_gpu(text["gpu_ioreg"], time)


def read_top(shell) -> list[Reading]:
    """CPU use and the energy ranking, for questions (top takes about 1.2 s)."""
    output = shell.run("top_power")
    return parse_top(output.text if output.ok else "")
