"""Workload set W: the scenarios of one tier, on the adapter or on battery (agent/device/workloads.py).

    python scripts/run_workloads.py --tier 3                # whatever the power source is now
    python scripts/run_workloads.py --tier 3 --only compile
    python scripts/run_workloads.py --tier 4 --quick        # a short check that every scenario runs

Each scenario is a fixed amount of work in phases that rise and fall with a seeded pattern. On the adapter
each runs once, in the adapter's mode (High Power on this Mac): the reference. On battery each runs in Low
Power and Automatic (tiers 0-2) or in all three modes (tiers 3-5); the battery mode is restored afterwards.
Compared between modes: the time of the batch phases, the share of missed deadlines in the interactive
phases, chip power and energy (powermetrics, every second), and the whole-system power from the battery
registry. The first run on the adapter calibrates the amounts of work (logs/workloads/calibration.json).

Keep the Mac on its own while it runs: other apps closed, brightness fixed. It stays awake by itself.
Reports: logs/workloads/ (JSON and Markdown).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.device import power_policy as pp  # noqa: E402
from agent.device import workloads as wl  # noqa: E402
from agent.device.shell import LiveShell  # noqa: E402
from agent.device.sources import chip, power  # noqa: E402

PAUSE = 20.0                          # seconds between runs, to let the chip settle


class Monitor:
    """powermetrics every second and the battery registry every second, while one run lasts."""

    def __init__(self, shell, seconds: float):
        self.shell, self.seconds = shell, seconds
        self.publications: list[tuple[float, dict]] = []
        self._stop = threading.Event()

    def __enter__(self):
        self.t0 = time.monotonic()
        self.samples: list[dict] = []
        self.thread = threading.Thread(target=self._poll, daemon=True)
        self.pm_thread = threading.Thread(target=self._chip, daemon=True)
        self.thread.start()
        self.pm_thread.start()
        return self

    def _chip(self):
        # powermetrics in 5-sample calls that end by themselves: a terminated powermetrics may lose the
        # samples it had not written out yet.
        while not self._stop.is_set():
            out = subprocess.run(chip.command(samples=5), capture_output=True, text=True)
            self.samples += [{r.name: r.value for r in s} for s in chip.parse(out.stdout)]
            if not out.stdout:
                self._stop.wait(1.0)

    def _poll(self):
        last = None
        while not self._stop.is_set():
            state = pp._battery_state(self.shell)
            if state.get("battery.update_time") != last:
                self.publications.append((time.monotonic() - self.t0, state))
                last = state.get("battery.update_time")
            self._stop.wait(1.0)

    def __exit__(self, *exc):
        self.t1 = time.monotonic() - self.t0
        self._stop.set()
        self.thread.join()
        self.pm_thread.join(timeout=10)
        return False

    def summary(self, on_battery: bool) -> dict:
        def mean(key):
            values = [s[key] for s in self.samples if s.get(key) is not None]
            return round(sum(values) / len(values), 2) if values else None

        def peak(key):
            values = [s[key] for s in self.samples if s.get(key) is not None]
            return max(values) if values else None

        cores = [k for s in self.samples[:1] for k in s if k.endswith("_cluster_active")]
        out = {"chip_w": mean("chip.combined_power"), "chip_peak_w": peak("chip.combined_power"), "cpu_w": mean("chip.cpu_power"), "gpu_w": mean("chip.gpu_power"),
               "gpu_busy": mean("chip.gpu_active"), "gpu_mhz": mean("chip.gpu_frequency"),
               "thermal_max": peak("chip.thermal_pressure_level"), "samples": len(self.samples)}
        for key in cores:
            out[key.replace("chip.", "").replace("_cluster_active", "_busy")] = mean(key)
        # Whole system: only publications inside the run, after a 10 s settling time.
        # Publications inside the run (first full run: a 10 s settling margin left runs under 2 minutes with
        # fewer than two, and no system power; the counter is exact between any two publications anyway).
        inside = [(t, s) for t, s in self.publications if 0 <= t <= self.t1]
        out["publications"] = len(inside)
        if on_battery:
            powers = [-(s.get("battery.voltage") or 0) * (s.get("battery.current") or 0) for _, s in inside
                      if s.get("battery.voltage") is not None and s.get("battery.current") is not None]
            out["system_w_vi"] = round(sum(powers) / len(powers), 1) if powers else None
            if len(inside) >= 2:
                (ta, a), (tb, b) = inside[0], inside[-1]
                joules = pp._joules(a, b, "charge drop")
                out["system_w_charge"] = round(joules / (tb - ta), 1) if joules is not None and tb > ta else None
        elif len(inside) >= 2:
            (_, a), (_, b) = inside[0], inside[-1]
            out["system_w"] = pp._mean_watts(a, b, 0, "system counter")
            out["system_w"] = round(out["system_w"], 1) if out["system_w"] is not None else None
        # A time series every 5 s for the heat and power curves (the feedback controller is designed from them).
        out["series"] = [{"t": i, "chip_w": s.get("chip.combined_power"), "gpu_busy": s.get("chip.gpu_active"),
                          "gpu_mhz": s.get("chip.gpu_frequency"), "p0_mhz": s.get("chip.p0_cluster_frequency"),
                          "thermal": s.get("chip.thermal_pressure_level")}
                         for i, s in enumerate(self.samples) if i % 5 == 0]
        return out


def run_one(profile, mode, shell, assets, calibration, on_battery) -> dict:
    with pp.BatteryMode(shell, mode) as switch:
        mode_now = {r.name: r.value for r in power.read(shell)}.get("power.mode_now")
        with Monitor(shell, 300) as monitor:
            result = wl.run_scenario(profile, assets, calibration)
    row = {"profile": profile.key, "name": profile.name, "tier": profile.tier,
           "source": "battery" if on_battery else "adapter", "mode": pp.NAMES.get(mode_now, mode_now),
           "notes": " ".join(switch.notes), **result}
    row.update(monitor.summary(on_battery))
    row["chip_wh"] = round(row["chip_w"] * row["total_s"] / 3600, 3) if row.get("chip_w") is not None else None
    return row


def quick(calibration: dict) -> dict:
    """The same scenarios with about a tenth of the work, to check that each one runs."""
    small = dict(calibration, scale=0.1)
    small["train_step_seconds"] = calibration["train_step_seconds"] * 10
    small["export_fps"] = calibration["export_fps"] / 10
    return small


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tier", type=int, required=True, choices=range(6))
    parser.add_argument("--only", help="comma-separated profile keys")
    parser.add_argument("--quick", action="store_true", help="a short check that every scenario runs (results not comparable)")
    args = parser.parse_args()

    shell = LiveShell()
    state = pp._battery_state(shell)
    on_battery = state.get("power.external") == 0
    profiles = wl.by_tier(args.tier)
    if args.only:
        wanted = {k.strip() for k in args.only.split(",")}
        profiles = [p for p in profiles if p.key in wanted]
    if on_battery and (state.get("battery.charge") or 0) < 40:
        sys.exit("The charge is below 40%: charge first, or run this tier on the adapter.")
    modes = [None] if not on_battery else ([pp.LOW, pp.AUTOMATIC] if args.tier <= 2 else [pp.LOW, pp.AUTOMATIC, pp.HIGH])
    if args.quick:
        modes = modes[:1]
    folder = ROOT / "logs" / "workloads"
    assets = folder / "assets"
    print("Preparing the test media (once) ...", flush=True)
    wl.prepare_assets(assets)
    freed = wl.unload_models()
    if freed:
        print(f"Unloaded from memory: {', '.join(freed)}", flush=True)
    calibration_path = folder / "calibration.json"
    if not calibration_path.exists():
        if on_battery:
            sys.exit("No calibration yet: run any tier once on the adapter first (the amounts of work are set at full speed).")
        print("Calibrating the amounts of work at full speed (about a minute, once) ...", flush=True)
        calibration_path.write_text(json.dumps(wl.calibrate(assets), indent=1), encoding="utf-8")
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    if args.quick:
        calibration = quick(calibration)
    awake = subprocess.Popen(["caffeinate", "-dimsu", "-w", str(os.getpid())]) if wl.MAC else None
    print(f"Tier {args.tier} on {'battery' if on_battery else 'the adapter'}: {len(profiles)} scenario(s) x {len(modes)} "
          f"mode(s), about {len(profiles) * len(modes) * (0.4 if args.quick else 3.5):.0f} minutes. Leave the Mac alone.", flush=True)

    rows = []
    for profile in profiles:
        for mode in modes:
            row = run_one(profile, mode, shell, assets, calibration, on_battery)
            rows.append(row)
            power_text = row.get("system_w") or row.get("system_w_charge") or row.get("system_w_vi")
            print(f"{profile.key:14} {row['mode']:10} total {row['total_s']} s, batch {row['batch_s']} s, missed {row['missed_share']}, "
                  f"chip {row['chip_w']} W (peak {row['chip_peak_w']}), system {power_text} W, GPU {row['gpu_busy']}%, "
                  f"thermal max {row['thermal_max']}" + (f"  ERROR {row['error'][:150]}" if row["error"] else ""), flush=True)
            time.sleep(PAUSE)
    if awake:
        awake.terminate()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = folder / f"tier{args.tier}_{'battery' if on_battery else 'adapter'}{'_quick' if args.quick else ''}_{stamp}"
    out.with_suffix(".json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    lines = [f"# Workloads, tier {args.tier}, on {'battery' if on_battery else 'the adapter'}, {stamp}", "",
             "| Scenario | Mode | Total s | Batch s | Missed | Chip W | Chip peak W | Chip Wh | GPU busy % | System W | Thermal max |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        system = r.get("system_w") if not on_battery else f"{r.get('system_w_charge')} (charge) / {r.get('system_w_vi')} (V×I)"
        lines.append(f"| {r['name']} | {r['mode']} | {r['total_s']} | {r['batch_s']} | {r['missed_share']} | {r['chip_w']} | "
                     f"{r['chip_peak_w']} | {r['chip_wh']} | {r['gpu_busy']} | {system} | {r['thermal_max']} |")
    lines += ["", "Phases:"]
    for r in rows:
        lines.append(f"- {r['name']} ({r['mode']}): " + "; ".join(
            f"{p['phase']} {p.get('seconds', '')} s" + (f", missed {p['missed']}/{p['ticks']}" if p.get("kind") == "interactive" else "")
            for p in r["phases"] if p.get("kind") != "info"))
    out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nReport: {out.with_suffix('.md').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
