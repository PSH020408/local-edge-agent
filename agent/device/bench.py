"""Short transfer-speed benchmarks: memory bandwidth (GPU and one CPU core) and SSD write and read.

Why (2026-11-17): asked "are the transfer speeds between RAM, SSD, CPU and GPU normal?", the performance agent
answered "no problem with the transfer speeds" although nothing measured them; the writer repeated the
question's subject as if it had been checked. Now the speeds are measured when a question asks about them,
in about 5 s, and compared with this Mac's normal (the first run on the adapter is stored as the normal).

On Apple silicon the CPU and the GPU share one memory (unified memory): there is no copy between them over a
bus, so "CPU to GPU transfer" is the memory bandwidth itself. Generating LLM tokens uses about 230 of the
M4 Pro's 273 GB/s (energy run E1), which is the same quantity measured here.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

MAC = sys.platform == "darwin"
SPEC = {"gpu_copy_gbs": 273.0}   # M4 Pro memory bandwidth (Apple's figure), a ceiling, not a normal


def gpu_copy(gigabytes: float = 1.0, repeats: int = 5) -> float | None:
    """GB/s read + written by the GPU copying a large array (memory bandwidth as the GPU sees it)."""
    try:
        import mlx.core as mx
    except ImportError:
        return None
    n = int(gigabytes * 1e9 / 4)
    x = mx.ones((n,), dtype=mx.float32)
    mx.eval(x)
    mx.eval(x + 1)  # warm up
    started = time.perf_counter()
    for _ in range(repeats):
        mx.eval(x + 1)
    seconds = time.perf_counter() - started
    return round(2 * n * 4 * repeats / seconds / 1e9, 1)


def cpu_copy(gigabytes: float = 0.5, repeats: int = 5) -> float:
    """GB/s read + written by one CPU core copying a large array."""
    import numpy as np
    a = np.ones(int(gigabytes * 1e9 / 8))
    b = np.empty_like(a)
    np.copyto(b, a)
    started = time.perf_counter()
    for _ in range(repeats):
        np.copyto(b, a)
    seconds = time.perf_counter() - started
    return round(2 * a.nbytes * repeats / seconds / 1e9, 1)


def _no_cache(handle) -> None:
    if MAC:
        import fcntl
        fcntl.fcntl(handle.fileno(), 48, 1)  # F_NOCACHE: the SSD, not the file cache in memory


def ssd(folder: Path, megabytes: int = 1024) -> tuple[float, float]:
    """(write GB/s, read GB/s) for one file written with fsync and read back, past the file cache."""
    folder.mkdir(parents=True, exist_ok=True)
    path, block = folder / "bench.bin", os.urandom(16 * 1024 * 1024)
    started = time.perf_counter()
    with open(path, "wb") as handle:
        _no_cache(handle)
        for _ in range(megabytes // 16):
            handle.write(block)
        handle.flush()
        os.fsync(handle.fileno())
    write = megabytes / 1024 / (time.perf_counter() - started)
    started = time.perf_counter()
    with open(path, "rb") as handle:
        _no_cache(handle)
        while handle.read(16 * 1024 * 1024):
            pass
    read = megabytes / 1024 / (time.perf_counter() - started)
    path.unlink(missing_ok=True)
    return round(write * 1.073741824, 2), round(read * 1.073741824, 2)  # GiB/s to GB/s


def run(folder: Path, normal_path: Path | None = None, on_adapter: bool = True) -> dict:
    """All three, about 5 s. The first result on the adapter becomes the stored normal."""
    write, read = ssd(folder)
    result = {"gpu_copy_gbs": gpu_copy(), "cpu_copy_gbs": cpu_copy(), "ssd_write_gbs": write, "ssd_read_gbs": read}
    normal = {}
    if normal_path is not None:
        if normal_path.exists():
            normal = json.loads(normal_path.read_text(encoding="utf-8"))
        elif on_adapter and all(v is not None for v in result.values()):
            normal_path.parent.mkdir(parents=True, exist_ok=True)
            normal_path.write_text(json.dumps(dict(result, time=time.strftime("%Y-%m-%d %H:%M")), indent=1), encoding="utf-8")
            normal = dict(result)
            result["normal_set_now"] = True
    result["normal"] = {k: normal.get(k) for k in ("gpu_copy_gbs", "cpu_copy_gbs", "ssd_write_gbs", "ssd_read_gbs")}
    return result
