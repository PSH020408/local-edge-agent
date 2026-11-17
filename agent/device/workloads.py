"""Synthetic workloads: everyday Mac work reproduced as scenarios with phases, the same way every time.

A real game or video editor cannot be run identically twice, so each scenario reproduces what such work asks
of the hardware (cores, GPU, media engine, memory, SSD), phase by phase, as it rises and falls in real use:
a video edit is scrubbing, then previews with effects, then a heavy export; training is data preparation,
then epochs of full GPU load, evaluation and checkpoint saves.

Two rules make the modes comparable (decided 2026-11-17):
1. Work, not time. Every phase is a fixed amount of work. A batch phase (export, a full build, training) is
   timed until it is done; an interactive phase (a game frame, a preview, typing) has a deadline per tick and
   counts the ticks it missed. A slower mode then shows as a longer batch or as missed deadlines.
2. The same randomness every time. The rise and fall comes from a seeded random generator, so every mode
   gets exactly the same pattern of load.
The amounts are set once from a calibration on the adapter in High Power (`calibrate`), stored in
logs/workloads/calibration.json, and not changed afterwards: a calibration in a slow mode would shrink the work.

These are proxies, not calibrated against the real applications (stated as a limit in the results).
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

MAC = sys.platform == "darwin"
SEED = 2026
UNIT_SECONDS = 0.010        # one CPU unit: about 10 ms of one performance core at full clock (calibrated)
_CAL: dict = {}             # calibration, set in each process (workers get it through their initialiser)


# ---------- work primitives ----------

def _init_worker(calibration: dict) -> None:
    _CAL.update(calibration)


def cpu_work(units: float) -> int:
    """A fixed amount of CPU work: `units` x the loop count that took 10 ms in the calibration."""
    count, target = 0, int(units * _CAL.get("cpu_iterations", 200_000))
    while count < target:
        count += 1
    return count


def _cpu_job(units: float) -> float:
    started = time.perf_counter()
    cpu_work(units)
    return time.perf_counter() - started


def walk(n: int, low: float, high: float, rng: random.Random, step: float = 0.15) -> list[float]:
    """A smooth random sequence between `low` and `high` (scene complexity, slider activity, ...)."""
    value, out = (low + high) / 2, []
    for _ in range(n):
        value = min(high, max(low, value + rng.uniform(-step, step) * (high - low)))
        out.append(value)
    return out


def _encoder(codec: str) -> str:
    """The media engine's hardware encoders on the Mac; software encoders elsewhere, for dry runs only."""
    return {"hevc": "hevc_videotoolbox", "h264": "h264_videotoolbox"}[codec] if MAC else {"hevc": "libx265", "h264": "libx264"}[codec]


def _ffmpeg(args: list[str]) -> subprocess.Popen:
    return subprocess.Popen(["ffmpeg", "-hide_banner", "-nostdin", "-y", *args], stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, text=True)


def _ffmpeg_wait(process: subprocess.Popen) -> dict:
    _, log = process.communicate()
    frames = [int(x) for x in re.findall(r"frame=\s*(\d+)", log)]
    return {"frames": frames[-1] if frames else 0, "ok": process.returncode == 0, "error": "" if process.returncode == 0 else log[-300:]}


@dataclass
class Ctx:
    """What a scenario needs: assets, calibration, a seeded generator, a CPU pool, GPU helpers, phase records."""

    assets: Path
    calibration: dict
    rng: random.Random = field(default_factory=lambda: random.Random(SEED))
    phases: list[dict] = field(default_factory=list)
    _pool: object = None
    _gpu: dict = field(default_factory=dict)

    def __post_init__(self):
        _CAL.update(self.calibration)
        self.scale = self.calibration.get("scale", 1.0)  # 0.1 for a quick check that every scenario runs

    def s(self, seconds: float) -> float:
        """A duration of the scenario, scaled for the quick check."""
        return seconds * self.scale

    def n(self, count: int) -> int:
        return max(1, round(count * self.scale))

    # CPU
    def pool(self):
        if self._pool is None:
            self._pool = mp.get_context("spawn").Pool(os.cpu_count() or 8, initializer=_init_worker, initargs=(self.calibration,))
        return self._pool

    def cpu(self, workers: int, units: float) -> float:
        """`workers` cores each doing `units` of work; returns the time until all are done.

        When the job takes every core, it is cut into small pieces that the pool hands out as cores free up:
        the 4 efficiency cores are about half as fast, and equal shares would leave the job waiting for them
        (quick check 2026-11-17: 64 s for 18 s of work per core)."""
        started = time.perf_counter()
        if workers >= (os.cpu_count() or 8):
            pieces = workers * 8
            self.pool().map(_cpu_job, [units * workers / pieces] * pieces, chunksize=1)
        else:
            self.pool().map(_cpu_job, [units] * workers)
        return time.perf_counter() - started

    def close(self):
        if self._pool is not None:
            self._pool.close()
            self._pool.join()

    # GPU (MLX)
    def gpu(self, products: float, size: int = 2048) -> float:
        """`products` matrix products of size x size on the GPU (fractions round up to whole products)."""
        import mlx.core as mx
        if size not in self._gpu:
            a, b = mx.random.normal((size, size)), mx.random.normal((size, size))
            mx.eval(a, b)
            self._gpu[size] = (a, b)
        a, b = self._gpu[size]
        started = time.perf_counter()
        left = max(1, round(products))
        while left:  # up to 8 products queued at once: one wait per group keeps the GPU fed
            group = min(8, left)
            mx.eval(*[a @ b for _ in range(group)])
            left -= group
        return time.perf_counter() - started

    def products_per(self, seconds: float) -> float:
        """GPU products in a budget per tick (a frame): not scaled by the quick check, unlike durations."""
        return seconds / self.calibration["gpu_product_seconds"]

    def filter_24mp(self) -> float:
        """An unsharp mask over a 24 MP photo on the GPU."""
        return self._unsharp("photo", (4000, 6000, 3))

    def filter_4k(self) -> float:
        """The same effect on one 4K video frame (8.3 MP). The calibration measured 94 ms for a 24 MP photo,
        so a video preview with the photo-sized effect would fill most of its 0.1 s deadline at full speed."""
        return self._unsharp("frame", (2160, 3840, 3))

    def _unsharp(self, key: str, shape: tuple) -> float:
        """A 3 x 3 blur from shifted copies, then sharpening. Image filters like this are bound by memory
        bandwidth, as in real editors; a convolution layer would build a huge intermediate matrix instead
        (7 GB for 24 MP: the dry run was killed for memory)."""
        import mlx.core as mx
        if key not in self._gpu:
            self._gpu[key] = mx.random.uniform(shape=shape)
            mx.eval(self._gpu[key])
        image = self._gpu[key]
        started = time.perf_counter()
        blurred = sum(mx.roll(image, (dy, dx), axis=(0, 1)) for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9
        mx.eval(mx.clip(image + 0.5 * (image - blurred), 0, 1))
        return time.perf_counter() - started

    # SSD
    def ssd(self, megabytes: int, read_back: bool = True) -> float:
        """Writes (and reads back) `megabytes` past the file cache."""
        path, block = self.assets / "ssd.bin", os.urandom(16 * 1024 * 1024)
        started = time.perf_counter()
        with open(path, "wb") as handle:
            _no_cache(handle)
            for _ in range(max(1, megabytes // 16)):
                handle.write(block)
            handle.flush()
            os.fsync(handle.fileno())
        if read_back:
            with open(path, "rb") as handle:
                _no_cache(handle)
                while handle.read(16 * 1024 * 1024):
                    pass
        path.unlink(missing_ok=True)
        return time.perf_counter() - started

    # phases
    def batch(self, name: str, work: Callable[[], object]) -> float:
        """A fixed amount of work, timed until it is done."""
        started = time.perf_counter()
        work()
        seconds = time.perf_counter() - started
        self.phases.append({"phase": name, "kind": "batch", "seconds": round(seconds, 2)})
        return seconds

    def ticks(self, name: str, n: int, period: float, work: Callable[[int], object]) -> dict:
        """`n` ticks of `period` seconds; `work(i)` must finish within its tick or the tick counts as missed."""
        started, missed = time.perf_counter(), 0
        n = self.n(n)
        for i in range(n):
            begin = time.perf_counter()
            work(i)
            spent = time.perf_counter() - begin
            if spent > period:
                missed += 1
            else:
                time.sleep(period - spent)
        record = {"phase": name, "kind": "interactive", "seconds": round(time.perf_counter() - started, 2),
                  "ticks": n, "missed": missed, "missed_share": round(missed / max(n, 1), 3)}
        self.phases.append(record)
        return record

    def idle(self, name: str, seconds: float) -> None:
        seconds = self.s(seconds)
        time.sleep(seconds)
        self.phases.append({"phase": name, "kind": "idle", "seconds": round(seconds, 2)})

    # scaling from the calibration
    def units_for(self, seconds: float) -> float:
        return self.s(seconds) / UNIT_SECONDS

    def products_for(self, seconds: float) -> float:
        return self.s(seconds) / self.calibration["gpu_product_seconds"]


def _no_cache(handle) -> None:
    if MAC:
        import fcntl
        fcntl.fcntl(handle.fileno(), 48, 1)  # F_NOCACHE: measure the SSD, not memory


# ---------- calibration (once, on the adapter in High Power) ----------

def calibrate(assets: Path) -> dict:
    """Measures how much work fits in the target times on this Mac at full speed."""
    _CAL["cpu_iterations"] = 5_000_000  # time the same loop that cpu_work runs, then scale it to 10 ms
    timings = []
    for _ in range(5):
        started = time.perf_counter()
        cpu_work(1)
        timings.append(time.perf_counter() - started)
    cpu_iterations = int(5_000_000 * UNIT_SECONDS / sorted(timings)[2])
    result = {"cpu_iterations": cpu_iterations, "machine": os.uname().machine, "time": time.strftime("%Y-%m-%d %H:%M")}
    ctx = Ctx(assets, result)
    try:
        ctx.gpu(3)
        result["gpu_product_seconds"] = round(ctx.gpu(20) / 20, 5)
        ctx.filter_24mp()
        result["filter_seconds"] = round(sum(ctx.filter_24mp() for _ in range(5)) / 5, 4)
    except ImportError:  # dry runs without MLX
        result["gpu_product_seconds"], result["filter_seconds"] = 0.003, 0.02
    process = _ffmpeg(["-i", str(assets / "clip4k.mp4"), "-t", "5", "-vf", EXPORT_FILTER, "-c:v", _encoder("hevc"),
                       "-b:v", "40M", "-f", "null", "-"])
    began = time.perf_counter()
    frames = _ffmpeg_wait(process)["frames"]
    result["export_fps"] = round(frames / (time.perf_counter() - began), 1) if frames else 30.0
    began = time.perf_counter()
    subprocess.run(["clang", "-O2", "-c", str(assets / "csrc" / "unit0.c"), "-o", str(assets / "unit0.o")], capture_output=True)
    result["compile_file_seconds"] = round(time.perf_counter() - began, 3)
    try:
        trainer = Trainer()
        trainer.step()
        began = time.perf_counter()
        for _ in range(5):
            trainer.step()
        result["train_step_seconds"] = round((time.perf_counter() - began) / 5, 4)
    except ImportError:
        result["train_step_seconds"] = 0.2
    ctx.close()
    return result


# ---------- assets ----------

EXPORT_FILTER = "unsharp=5:5:1.0,eq=contrast=1.1:saturation=1.2"


def prepare_assets(folder: Path) -> None:
    """Creates the test media and sources once: a 4K clip, a music file, C sources."""
    folder.mkdir(parents=True, exist_ok=True)
    clip, music = folder / "clip4k.mp4", folder / "music.m4a"
    if not clip.exists():  # 60 s of 4K at 30 fps, HEVC 40 Mbit/s: a synthetic pattern (simpler than real footage)
        subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-f", "lavfi", "-i", "testsrc2=size=3840x2160:rate=30",
                        "-t", "60" if MAC else "2", "-c:v", _encoder("hevc"), "-b:v", "40M", "-tag:v", "hvc1", str(clip)],
                       capture_output=True, check=True)
    if not music.exists():
        subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=600",
                        "-c:a", "aac", "-b:a", "256k", str(music)], capture_output=True, check=True)
    sources = folder / "csrc"
    if not sources.exists():
        sources.mkdir()
        for i in range(240):
            body = "\n".join(f"double f{i}_{k}(double x) {{ double s = 0; for (int j = 0; j < {50 + k}; j++) "
                             f"{{ s += x * j / (j + {k + 1}.0); if (s > 1e9) s -= 1e9; }} return s; }}" for k in range(40))
            (sources / f"unit{i}.c").write_text(body + "\n", encoding="utf-8")


def _play(assets: Path, seconds: float, start: float = 0.0) -> subprocess.Popen:
    """4K playback: hardware decoding at the real-time rate; the media engine does the work."""
    hw = ["-hwaccel", "videotoolbox"] if MAC else []
    return _ffmpeg([*hw, "-re", "-stream_loop", "-1", "-ss", f"{start:.1f}", "-i", str(assets / "clip4k.mp4"),
                    "-t", f"{seconds:.1f}", "-f", "null", "-"])


def _compile(ctx: Ctx, files: list[Path]) -> None:
    from concurrent.futures import ThreadPoolExecutor
    out = ctx.assets / "obj"
    out.mkdir(exist_ok=True)
    with ThreadPoolExecutor(os.cpu_count() or 8) as pool:
        list(pool.map(lambda p: subprocess.run(["clang", "-O2", "-c", str(p), "-o", str(out / (p.stem + ".o"))],
                                               capture_output=True), files))


class Trainer:
    """A 4-layer transformer (512 wide, 8000-token vocabulary) trained for real with MLX on random tokens."""

    def __init__(self, batch: int = 16, length: int = 256):
        import mlx.core as mx
        import mlx.nn as nn
        import mlx.optimizers as optim
        self.mx, self.batch, self.length, self.vocab = mx, batch, length, 8000

        class Model(nn.Module):
            def __init__(self, vocab):
                super().__init__()
                self.embed = nn.Embedding(vocab, 512)
                self.body = nn.TransformerEncoder(num_layers=4, dims=512, num_heads=8)
                self.head = nn.Linear(512, vocab)

            def __call__(self, x):
                return self.head(self.body(self.embed(x), mask=None))

        self.model = Model(self.vocab)
        self.optimizer = optim.Adam(learning_rate=1e-4)
        self.loss = lambda m, x, y: nn.losses.cross_entropy(m(x), y).mean()
        self.grad = nn.value_and_grad(self.model, self.loss)

    def _tokens(self):
        return self.mx.random.randint(0, self.vocab, (self.batch, self.length))

    def step(self):
        x = self._tokens()
        loss, grads = self.grad(self.model, x, x)
        self.optimizer.update(self.model, grads)
        self.mx.eval(self.model.parameters(), self.optimizer.state, loss)

    def evaluate(self):
        x = self._tokens()
        self.mx.eval(self.loss(self.model, x, x))


# ---------- scenarios (about 3-4 minutes each at full speed) ----------

def s_idle(ctx: Ctx):
    ctx.idle("screen on, nothing running", 120)


def s_document(ctx: Ctx):
    """Typing in bursts with pauses (2-15 ms of work per second), an autosave every 45 s."""
    pattern = []
    for _ in range(18):  # 10-second stretches: typing or a pause
        typing = ctx.rng.random() < 0.65
        pattern += [ctx.rng.uniform(0.2, 1.5) if typing else 0.0 for _ in range(10)]

    def tick(i):
        if pattern[i]:
            cpu_work(pattern[i])
        if i % 45 == 44:
            ctx.cpu(2, 20)
            ctx.ssd(50, read_back=False)
    ctx.ticks("typing, pauses, autosave", len(pattern), 1.0, tick)


def s_music(ctx: Ctx):
    seconds = round(ctx.s(180))
    subprocess.run(["afplay", "-t", str(seconds), str(ctx.assets / "music.m4a")] if MAC else ["sleep", str(seconds)],
                   capture_output=True)
    ctx.phases.append({"phase": "playback", "kind": "realtime", "seconds": seconds})


def s_web(ctx: Ctx):
    """Page loads at random (on average every 12 s, 0.2-0.6 s on 4 cores), scrolling on the GPU between them,
    a 10-second video ad at one minute."""
    loads = [ctx.rng.random() < 1 / 12 for _ in range(180)]
    sizes = [ctx.rng.uniform(20, 60) for _ in range(180)]
    scroll = walk(180, 0.0, 1.0, ctx.rng)
    ad = None

    def tick(i):
        nonlocal ad
        if i == ctx.n(60):
            ad = _play(ctx.assets, ctx.s(10))
        if loads[i]:
            ctx.cpu(4, sizes[i])
        elif scroll[i] > 0.4:
            ctx.gpu(1, size=1024)
    ctx.ticks("browsing (a page load must finish within its second)", 180, 1.0, tick)
    if ad:
        _ffmpeg_wait(ad)


def s_video_4k_play(ctx: Ctx):
    """3 minutes of 4K playback with three seeks."""
    starts = [0.0] + [ctx.rng.uniform(5, 50) for _ in range(3)]
    for k, start in enumerate(starts):
        result = _ffmpeg_wait(_play(ctx.assets, ctx.s(45), start))
        ctx.phases.append({"phase": f"playback {k + 1}", "kind": "realtime", "seconds": ctx.s(45), "frames": result["frames"],
                           "error": result["error"]})


def s_video_call(ctx: Ctx):
    """3 minutes of 1080p real-time encoding; the CPU work follows who speaks and how much moves (10-40% of 2 cores)."""
    encode = _ffmpeg(["-re", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30", "-t", f"{ctx.s(180):.0f}",
                      "-c:v", _encoder("h264"), "-b:v", "3M", "-f", "null", "-"])
    activity = walk(180, 0.1, 0.4, ctx.rng)
    ctx.ticks("call (audio and video processing per second)", 180, 1.0, lambda i: ctx.cpu(2, activity[i] * 100))
    _ffmpeg_wait(encode)


def s_photo(ctx: Ctx):
    """Import, editing with sliders (a preview within 0.5 s), then export of 20 photos."""
    ctx.batch("import (read and decode)", lambda: (ctx.ssd(1024), ctx.cpu(4, ctx.units_for(2.0))))
    moving = walk(180, 0.0, 1.0, ctx.rng)

    def preview(i):
        if moving[i] > 0.35:
            ctx.filter_24mp()
            ctx.cpu(2, 8)
    ctx.ticks("editing (preview within 0.5 s)", 180, 0.5, preview)

    def export():
        for _ in range(20):
            ctx.cpu(8, ctx.units_for(0.4))
            ctx.filter_24mp()
    ctx.batch("export 20 photos", export)


def s_compile(ctx: Ctx):
    """Edit, build the changed files, three times; then a full build of the project."""
    sources = sorted((ctx.assets / "csrc").glob("*.c"))
    for k in range(3):
        ctx.idle(f"editing {k + 1}", ctx.rng.uniform(10, 20))
        changed = ctx.rng.sample(sources, ctx.rng.randint(8, 20))
        ctx.batch(f"incremental build {k + 1} ({len(changed)} files)", lambda: _compile(ctx, changed))
    # A full build of about 40 s at full speed: the project is built as often as that takes (once at least).
    one = len(sources) * ctx.calibration["compile_file_seconds"] / (os.cpu_count() or 8)
    rounds = max(1, round(ctx.s(40) / one))
    ctx.batch(f"full build ({rounds} x {len(sources)} files)", lambda: [_compile(ctx, sources) for _ in range(rounds)])


def s_file_copy(ctx: Ctx):
    ctx.batch("copy 4 GB (write and read back)", lambda: [ctx.ssd(1024) for _ in range(4)])
    ctx.idle("after the copy", 15)


def s_video_edit(ctx: Ctx):
    """4K editing: scrubbing, previews with effects (a frame within 0.1 s), a fixed-length export, review."""
    for k in range(4):
        _ffmpeg_wait(_play(ctx.assets, ctx.s(5), ctx.rng.uniform(0, 50)))
    ctx.phases.append({"phase": "scrubbing (4 x 5 s)", "kind": "realtime", "seconds": 20})
    playback = _play(ctx.assets, ctx.s(60))
    effects = walk(600, 0.0, 1.0, ctx.rng)
    ctx.ticks("preview with effects (a frame within 0.1 s)", 600, 0.1,
              lambda i: ctx.filter_4k() if effects[i] > 0.3 else None)
    _ffmpeg_wait(playback)
    frames = max(1, int(40 * ctx.calibration["export_fps"]))  # 40 s of export at full speed

    def export():
        result = _ffmpeg_wait(_ffmpeg(["-stream_loop", "-1", "-i", str(ctx.assets / "clip4k.mp4"), "-frames:v", str(frames),
                                       "-vf", EXPORT_FILTER, "-c:v", _encoder("hevc"), "-b:v", "40M", "-f", "null", "-"]))
        ctx.phases.append({"phase": "export frames", "kind": "info", "frames": result["frames"], "error": result["error"]})
    ctx.batch(f"export ({frames} frames)", export)
    ctx.idle("review", 20)


def _game_worker(args) -> int:
    """Game logic, physics or audio on one core: work per frame follows the scene, 60 frames a second."""
    calibration, per_frame = args
    _CAL.update(calibration)
    missed = 0
    for units in per_frame:
        begin = time.perf_counter()
        cpu_work(units)
        spent = time.perf_counter() - begin
        if spent > 1 / 60:
            missed += 1
        else:
            time.sleep(1 / 60 - spent)
    return missed


def s_game(ctx: Ctx):
    """Loading, 2 minutes of play at 60 fps (scene complexity rises and falls), a menu, loading again."""
    ctx.batch("loading", lambda: (ctx.ssd(1024), ctx.cpu(4, ctx.units_for(3.0))))
    import numpy as np
    world = np.ones(int(6 * ctx.scale * 1024**3) // 8)  # 6 GB of textures and level data held in memory
    stride = max(1, len(world) // 600)
    frames = ctx.n(120 * 60)
    scene = walk(frames, 0.45, 1.0, ctx.rng, step=0.02)
    products = ctx.products_per(0.010)  # the heaviest scene: 10 ms of GPU work in a 16.7 ms frame
    cpu_frames = [[round(0.4 * s, 3) for s in scene] for _ in range(3)]
    background = ctx.pool().map_async(_game_worker, [(ctx.calibration, f) for f in cpu_frames])
    def frame(i):
        ctx.gpu(products * scene[i])
        world[(i % 600) * stride:(i % 600 + 1) * stride:512] += 1.0  # the part of the level in view
    ctx.ticks("play at 60 fps", frames, 1 / 60, frame)
    ctx.phases[-1]["cpu_missed"] = sum(background.get())
    ctx.ticks("menu", 20 * 60, 1 / 60, lambda i: ctx.gpu(products * 0.15) if i % 2 == 0 else None)
    ctx.batch("loading the next level", lambda: (ctx.ssd(512), ctx.cpu(4, ctx.units_for(1.5))))


def s_render_3d(ctx: Ctx):
    """Scene preparation on one core, then 60 tiles of uneven complexity on the GPU (about 90 s at full speed)."""
    ctx.batch("scene preparation", lambda: ctx.cpu(1, ctx.units_for(5.0)))
    weights = [ctx.rng.uniform(0.3, 1.7) for _ in range(60)]
    per_tile = ctx.products_for(1.5)
    ctx.batch("render 60 tiles", lambda: [ctx.gpu(per_tile * w) for w in weights])


def s_llm(ctx: Ctx):
    """A long document read once (about 8,000 tokens) and three answers of 200 tokens with qwen3:14b."""
    root = Path(__file__).resolve().parent.parent.parent
    document = "\n\n".join((root / n).read_text(encoding="utf-8") for n in ("README.md", "docs/roadmap.md", "docs/stage7_design.md"))[:32000]
    stats = {"prompt_tokens": 0, "prompt_s": 0.0, "tokens": 0, "gen_s": 0.0}

    def ask(prompt, tokens):
        body = {"model": "qwen3:14b", "prompt": prompt, "stream": False, "think": False,
                "options": {"num_predict": tokens, "temperature": 0, "seed": 1, "num_ctx": 16384}}
        request = urllib.request.Request("http://localhost:11434/api/generate", json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=600) as response:
            r = json.loads(response.read())
        stats["prompt_tokens"] += r.get("prompt_eval_count", 0)
        stats["prompt_s"] += r.get("prompt_eval_duration", 0) / 1e9
        stats["tokens"] += r.get("eval_count", 0)
        stats["gen_s"] += r.get("eval_duration", 0) / 1e9

    nonce = f"Session {time.time():.0f}."  # a new first line: Ollama would reuse a cached prompt
    ctx.batch("read the document", lambda: ask(f"{nonce}\n{document}\n\nSummarise it in three sentences.", 60))
    for k in range(3):
        ctx.idle(f"reading the answer {k + 1}", ctx.rng.uniform(5, 12))
        ctx.batch(f"answer {k + 1}", lambda: ask(f"{nonce} Question {k}: explain one design decision of a battery agent.", 200))
    ctx.phases.append({"phase": "speeds", "kind": "info",
                       "read_tokens_per_s": round(stats["prompt_tokens"] / stats["prompt_s"], 1) if stats["prompt_s"] else None,
                       "written_tokens_per_s": round(stats["tokens"] / stats["gen_s"], 1) if stats["gen_s"] else None})


def s_training(ctx: Ctx):
    """Data preparation on 8 cores, then three epochs: training steps, an evaluation, a checkpoint save."""
    trainer = Trainer()
    steps = max(10, int(25 / ctx.calibration["train_step_seconds"]))  # about 25 s of training per epoch at full speed
    ctx.batch("data preparation", lambda: ctx.cpu(8, ctx.units_for(8.0)))
    for epoch in range(1, 4):
        ctx.batch(f"epoch {epoch}: {steps} training steps", lambda: [trainer.step() for _ in range(steps)])
        ctx.batch(f"epoch {epoch}: evaluation", lambda: [trainer.evaluate() for _ in range(steps // 4)])
        ctx.batch(f"epoch {epoch}: checkpoint", lambda: ctx.ssd(512, read_back=False))


def s_stress(ctx: Ctx):
    """Every core and the GPU at once, for a fixed amount of work (about 3 minutes at full speed)."""
    cores = os.cpu_count() or 8
    workers = cores - 2  # two cores left to feed the GPU (quick check: with all 14 busy the GPU was 29% busy)
    pieces = workers * 8

    def both():
        with mp.get_context("spawn").Pool(workers, initializer=_init_worker, initargs=(ctx.calibration,)) as pool:
            cpu = pool.map_async(_cpu_job, [ctx.units_for(180) * workers / pieces] * pieces, chunksize=1)
            ctx.gpu(ctx.products_for(180))
            cpu.get()
    ctx.batch("CPU and GPU together", both)


@dataclass
class Profile:
    key: str
    tier: int
    name: str
    uses: str
    run: Callable[[Ctx], None]


PROFILES = [
    Profile("idle", 0, "Idle, screen on", "nothing (baseline)", s_idle),
    Profile("document", 1, "Documents, notes, terminal", "efficiency cores, short bursts", s_document),
    Profile("music", 1, "Music playback", "audio decoding", s_music),
    Profile("web", 2, "Web browsing", "bursts on 4 cores, light GPU", s_web),
    Profile("video_4k_play", 2, "4K video playback", "media engine (decoder)", s_video_4k_play),
    Profile("video_call", 2, "Video call", "media engine (encoder), 2 cores", s_video_call),
    Profile("photo", 3, "Photo editing", "cores, GPU filter, SSD", s_photo),
    Profile("compile", 3, "Coding and building", "all cores in bursts", s_compile),
    Profile("file_copy", 3, "File copy, backup", "SSD bandwidth", s_file_copy),
    Profile("video_edit", 4, "4K video editing", "media engine, GPU effects, CPU filters", s_video_edit),
    Profile("game", 4, "Game (60 fps)", "GPU per frame, 3 cores, SSD loading", s_game),
    Profile("render_3d", 4, "3D rendering", "GPU at full load", s_render_3d),
    Profile("llm", 4, "Local LLM inference", "memory bandwidth", s_llm),
    Profile("training", 5, "Deep-learning training", "GPU, memory bandwidth, SSD", s_training),
    Profile("stress", 5, "Maximum load", "every core and the GPU", s_stress),
]


def by_tier(tier: int) -> list[Profile]:
    return [p for p in PROFILES if p.tier == tier]


def run_scenario(profile: Profile, assets: Path, calibration: dict) -> dict:
    """Runs one scenario; returns its phases and the totals the runner compares between modes."""
    ctx = Ctx(assets, calibration)
    started = time.perf_counter()
    error = ""
    try:
        profile.run(ctx)
    except Exception as exc:  # noqa: BLE001 - one failed scenario must not end the session
        error = f"{type(exc).__name__}: {exc}"
    finally:
        ctx.close()
    batch = [p for p in ctx.phases if p["kind"] == "batch"]
    interactive = [p for p in ctx.phases if p["kind"] == "interactive"]
    ticks = sum(p["ticks"] for p in interactive)
    return {"total_s": round(time.perf_counter() - started, 1),
            "batch_s": round(sum(p["seconds"] for p in batch), 1) if batch else None,
            "missed_share": round(sum(p["missed"] for p in interactive) / ticks, 3) if ticks else None,
            "phases": ctx.phases, "error": error}


def unload_models(host: str = "http://localhost:11434") -> list[str]:
    """Frees the models Ollama holds, so they do not take memory from the workloads (Run D6)."""
    try:
        with urllib.request.urlopen(f"{host}/api/ps", timeout=2) as response:
            names = [m["name"] for m in json.loads(response.read()).get("models", [])]
        for name in names:
            body = json.dumps({"model": name, "keep_alive": 0}).encode()
            urllib.request.urlopen(urllib.request.Request(f"{host}/api/generate", body, {"Content-Type": "application/json"}), timeout=30).read()
        return names
    except Exception:  # noqa: BLE001
        return []


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None

