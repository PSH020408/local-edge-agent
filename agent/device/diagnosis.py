"""Diagnosis: readings in, facts and findings out. All numbers are computed here, by code.

A finding is one conclusion with the readings that triggered it (evidence) and what to do (advice).
The rules and thresholds are those of docs/stage7_design.md §7-8 and the decisions in docs/devlog.md.
Facts and evidence are formatted for people here (GB, W, minutes), so the answer writer copies
numbers and never converts or computes them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MODE_NAMES = {0: "Automatic", 1: "Low Power", 2: "High Power"}
PRESSURE_NAMES = {0: "nominal", 1: "moderate", 2: "heavy", 3: "trapping", 4: "sleeping"}

# Thresholds (design §7-8)
HEALTH_REPLACE = 80.0       # % of design capacity as macOS shows it (Apple's service limit)
HEALTH_WATCH = 85.0
BATTERY_HOT = 35.0          # °C
CHARGE_LOW = 20.0           # %
HEAVY_CPU = 70.0            # % of all cores
HEAVY_GPU = 50.0            # %
BUSY_CPU = 85.0
CELL_SPREAD = 0.05          # V between the highest and the lowest cell
ADAPTER_LIMIT = 0.85        # share of the adapter rating above which the adapter counts as at its limit
HELD_BIT = 0x01000000        # ChargerData NotChargingReason while macOS holds the charge (seen at the 90% limit)
ASSIST_SMALL = 5.0          # W from the battery on the adapter that is not yet a problem (Run D3, L01-L02)
GPU_BUSY = 80.0             # % active
GPU_HELD = 0.45             # frequency below this share of the maximum while busy
BUSY_PROCESS_CPU = 90.0     # % of one core for the whole capture
MEMORY_LOW = 20.0           # % available
MEMORY_CRITICAL = 10.0
SWAPOUT_FAST = 600.0        # pages per minute
STORAGE_LOW = 10.0          # % free
STORAGE_CRITICAL = 5.0
GB = 1024 ** 3

# Memory a job needs (measured model sizes: qwen3:14b 9.2 GB, vision model 5.7 GB, small models 1-3 GB)
JOBS = {  # job: (description, memory needed with its models loaded from scratch, the models it uses)
    "document": ("a document question with the 14B model", 10.0, ("qwen3:14b",)),
    "vision": ("an image question with the vision model", 6.5, ("qwen3-vl:8b-instruct",)),
    "long_run": ("a long test run with the 14B and vision models", 16.0, ("qwen3:14b", "qwen3-vl:8b-instruct")),
    "light": ("a light job with the small models", 3.0, ("qwen3:4b-instruct", "qwen3:1.7b")),
}
WORKING_MEMORY = 1.0        # GB a job needs beyond its model's weights (context, buffers)

# Everyday work, from the workload set W on this Mac (evals/device/workloads.md, 2026-11-17): memory the work
# holds, the whole Mac's mean power and the chip's peak power while it ran, and whether it leans on the GPU.
# Asked "can I edit 4K video now?", the agent answers from these and the present state (added 2026-11-17).
WORK = {  # key: (description, memory GB, mean system W, peak chip W, GPU-heavy)
    "light": ("documents, web and music", 1.0, 8.0, 18.0, False),
    "video_play": ("watching 4K video", 1.0, 7.5, 1.0, False),
    "video_call": ("a video call", 1.5, 13.0, 5.5, False),
    "photo": ("photo editing", 4.0, 15.0, 43.0, True),
    "compile": ("coding and building", 4.0, 17.0, 35.0, False),
    "video_edit": ("4K video editing and export", 8.0, 22.0, 17.0, True),
    "game": ("a demanding game", 6.0, 26.0, 26.0, True),
    "render_3d": ("3D rendering", 4.0, 33.0, 36.0, True),
    "training": ("training a deep-learning model", 8.0, 32.0, 37.0, True),
}
WORK_WORDS = [
    ("video_edit", r"영상\s*편집|동영상\s*편집|4k\s*(영상\s*)?(편집|내보내기|렌더|export)|video edit|edit(ing)? (4k )?video|premiere|final cut|파이널\s*컷|프리미어"),
    ("game", r"게임|(?<![a-z])gam(e|es|ing)(?![a-z])"),
    ("render_3d", r"3d|렌더링|블렌더|blender|(?<![a-z])render"),
    ("training", r"학습|딥러닝|트레이닝|training|train a|fine.?tun"),
    ("compile", r"컴파일|빌드|코딩|개발\s*작업|compil|build|coding|xcode"),
    ("photo", r"사진\s*편집|라이트룸|포토샵|photo edit|lightroom|photoshop"),
    ("video_call", r"화상\s*(통화|회의)|줌|zoom|facetime|페이스타임|video call|meeting"),
    ("video_play", r"영상\s*(시청|보기|재생)|유튜브|넷플릭스|youtube|netflix|watch(ing)? (a )?(4k )?(video|movie)|streaming"),
    ("light", r"문서\s*작업|웹\s*서핑|인터넷|음악|documents?\b(?! question)|browsing|web|music"),
]
OVERVIEW_QUESTION = r"어떤\s*작업|무슨\s*작업|뭘\s*할\s*수|뭐\s*할\s*수|what can i (do|run)|which (work|tasks)|what work"
WORK_QUESTION = r"가능|할\s*수\s*있|돌아가|괜찮|돼\?|될까|되나|해도|can i|could i|is it ok|possible|able to"


@dataclass
class Finding:
    code: str
    severity: str  # info, warning, problem
    title: str
    evidence: dict[str, str] = field(default_factory=dict)
    advice: str = ""


@dataclass
class Report:
    topic: str
    facts: dict[str, str] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)

    def codes(self) -> list[str]:
        return [f.code for f in self.findings]


def _num(view, name):
    value = view.value(name)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _mean(view, name):
    m = view.mean(name)
    return m if m is not None else _num(view, name)


def _round(x, digits=1):
    return None if x is None else round(x, digits)


def gb(x) -> str:
    """Memory in GB of 1024³ bytes (24 GB of memory shows as 24.0)."""
    return f"{x / GB:.1f} GB"


def gb_disk(x) -> str:
    """Storage in GB of 10⁹ bytes, as Finder and the SSD's label count it."""
    return f"{x / 1e9:.1f} GB"


def minutes(m: float) -> str:
    m = int(round(m))
    return f"{m} min ({m // 60} h {m % 60} min)"


def cpu_percent(view) -> float | None:
    total, cores = _mean(view, "process.total_cpu"), _num(view, "cpu.cores")
    return round(total / cores, 1) if total is not None and cores else None


def battery_report(view, profile: dict | None = None, baseline_power: float | None = None, top: list | None = None,
                   question: str = "") -> Report:
    """view: a Capture (or anything with value() and mean()); profile: readings from battery.read_profile().
    The disagreement between the two sources of the energy mode is reported only when the question is about the mode."""
    profile = profile or {}
    report = Report("battery")
    f = report.facts
    source = view.value("power.source")
    on_battery = source == "Battery"
    charge = _num(view, "battery.charge")
    design, full, present = (_num(view, f"battery.{k}") for k in ("design_capacity", "full_charge_capacity", "present_capacity"))
    voltage, current = _mean(view, "battery.voltage"), _mean(view, "battery.current")
    cycles, design_cycles = _num(view, "battery.cycle_count"), _num(view, "battery.design_cycle_count")
    macos_health = profile.get("battery.macos_maximum_capacity")
    raw_health = round(100 * full / design, 1) if full and design else None
    temperature = _mean(view, "battery.temperature")
    mode_now = _num(view, "power.mode_now")
    cells = [_num(view, f"battery.cell{i}_voltage") for i in range(1, 9)]
    cells = [c for c in cells if c is not None]
    cpu, gpu = cpu_percent(view), _mean(view, "gpu.usage")
    heavy = (cpu is not None and cpu >= HEAVY_CPU) or (gpu is not None and gpu >= HEAVY_GPU)
    asks_mode = bool(re.search(r"모드|mode", question, re.I))
    discharging_on_adapter = not on_battery and current is not None and current < -0.2
    # What matters depends on the power source (decided 2026-11-17). On the adapter: battery health and
    # lifespan, heat, and whether the adapter does its job; the energy mode made no difference to speed
    # (energy runs E1-E3) and the time left does not apply. On battery: time left, consumption, efficiency,
    # stability and heat. Facts that do not matter are left out, so the writer cannot bring them in.
    battery_side = on_battery or discharging_on_adapter
    hot = temperature is not None and temperature >= BATTERY_HOT

    if source:
        f["power source"] = "battery" if on_battery else "power adapter"
    if charge is not None:
        f["charge"] = f"{charge}%"
    if view.value("power.charge_state"):
        f["charge state (macOS)"] = str(view.value("power.charge_state"))
    if mode_now is not None and (on_battery or asks_mode):
        f["energy mode now"] = MODE_NAMES.get(mode_now, str(mode_now))
    if macos_health is not None:
        f["maximum capacity (macOS)"] = f"{macos_health:g}%"
    if profile.get("battery.macos_condition"):
        f["condition (macOS)"] = str(profile["battery.macos_condition"])
    if raw_health is not None:
        f["full-charge capacity / design capacity"] = f"{raw_health}% ({full:,} of {design:,} mAh)"
    if cycles is not None:
        f["charge cycles"] = f"{cycles:,}" + (f" of {design_cycles:,} rated" if design_cycles else "")
    if temperature is not None:
        f["battery temperature"] = f"{temperature:.1f} °C"
    if cells:
        f["cell voltages"] = ", ".join(f"{c:.3f} V" for c in cells) + f" (spread {1000 * (max(cells) - min(cells)):.0f} mV)"
    if cpu is not None and (battery_side or hot):
        f["CPU use"] = f"{cpu}%"
    if gpu is not None and (battery_side or hot):
        f["GPU use"] = f"{gpu:.0f}%"

    # Power and time
    power = None
    if on_battery and voltage is not None and current is not None:
        power = abs(voltage * current)
        f["power drawn from the battery"] = f"{power:.1f} W"
    elif not on_battery and _mean(view, "power.system_input") is not None:
        f["power drawn by the Mac from the adapter"] = f"{_mean(view, 'power.system_input'):.1f} W"
        if _num(view, "power.adapter_watts"):
            f["adapter rating"] = f"{_num(view, 'power.adapter_watts')} W"
    if present is not None and voltage is not None and battery_side:
        energy = present * voltage / 1000
        f["energy left in the battery"] = f"{energy:.1f} Wh"
        if on_battery and power and power > 0.5:
            f["time left at the present power (own estimate)"] = minutes(60 * energy / power)
    supplied, rating = _mean(view, "power.system_input"), _num(view, "power.adapter_watts")
    # Run D3, L01-L02: 3.0 W from the battery while the adapter gave 72 W of its 100 W. That is not a weak
    # adapter; it is a problem only when the adapter gives nothing, is at its limit, or the battery carries a lot.
    at_limit = bool(supplied and rating and supplied >= ADAPTER_LIMIT * rating)
    assist_only = False
    if discharging_on_adapter and voltage is not None:
        power = abs(voltage * current)
        f["power drawn from the battery although the adapter is connected"] = f"{power:.1f} W"
        assist_only = bool(supplied) and not at_limit and power < ASSIST_SMALL
        if present is not None and power > 0.5 and not assist_only:
            f["time left at the present power (own estimate)"] = minutes(60 * present * voltage / 1000 / power)
    # Run D6, L02: "how long will the battery last?" on the adapter got a health report. The battery is not
    # in use, so the answer is the time it would last once unplugged, at this user's usual power on battery.
    asks_time = bool(re.search(r"버텨|버틸|남은 시간|얼마나 (더|오래)|time left|how long|last", question, re.I))
    if not battery_side and asks_time and present is not None and voltage is not None:
        energy = present * voltage / 1000
        f["energy left in the battery"] = f"{energy:.1f} Wh"
        if baseline_power:
            f["usual power on battery"] = f"{baseline_power:.1f} W"
            f["time on battery at the usual power (own estimate)"] = minutes(60 * energy / baseline_power)
    if _num(view, "power.macos_time_remaining") is not None:
        f["time left (macOS estimate)"] = minutes(_num(view, "power.macos_time_remaining"))
    if _num(view, "power.macos_time_to_full") is not None:
        f["time to full (macOS estimate)"] = minutes(_num(view, "power.macos_time_to_full"))
    # The charger reports why it is not charging as a bit field, like a status register. On this Mac the value
    # was 0x1000000 (bit 24) both times charging was held at the 90% limit set in System Settings.
    reason = view.value("battery.not_charging_reason")
    held = not on_battery and isinstance(reason, int) and bool(reason & HELD_BIT) and view.value("battery.is_charging") != 1
    if held:
        f["charging held by macOS"] = f"yes, at {f.get('charge', '?')} (charger status 0x{reason:X})"
    charging_current = _num(view, "battery.charging_current")
    if not on_battery and view.value("battery.is_charging") == 1 and charging_current and full and present is not None:
        f["time to full at the present charging current"] = minutes(60 * (full - present) / (1000 * charging_current))

    # Findings
    findings = report.findings
    health = macos_health if macos_health is not None else raw_health
    if health is not None or cycles is not None:
        evidence = {k: f[k] for k in ("maximum capacity (macOS)", "full-charge capacity / design capacity", "charge cycles") if k in f}
        if (health is not None and health < HEALTH_REPLACE) or (cycles is not None and design_cycles and cycles >= design_cycles):
            findings.append(Finding("battery_replace", "problem", "The battery has reached Apple's service limit", evidence,
                                    "Have the battery replaced (Apple: below 80% of the original capacity or at the rated cycle count)."))
        elif health is not None and health < HEALTH_WATCH:
            findings.append(Finding("battery_aging", "warning", "The battery is ageing but still above the service limit", evidence,
                                    "No replacement needed yet; watch the maximum capacity over the coming months."))
        else:
            findings.append(Finding("battery_ok", "info", "Battery health is good", evidence, "No action needed."))
    if temperature is not None and temperature >= BATTERY_HOT:
        findings.append(Finding("battery_hot", "warning", f"The battery is warmer than it should be (above {BATTERY_HOT:g} °C)",
                                {"battery temperature": f["battery temperature"]},
                                "Lower the load or move the Mac to a hard, open surface so the vents are free."))
    if len(cells) >= 2 and max(cells) - min(cells) > CELL_SPREAD:
        findings.append(Finding("cell_imbalance", "warning", "The battery cells are out of balance", {"cell voltages": f["cell voltages"]},
                                "Charge to full once; if the spread stays, have the battery checked."))
    if on_battery:
        if charge is not None and charge < CHARGE_LOW:
            findings.append(Finding("charge_low", "warning", "The charge is low", {"charge": f["charge"]},
                                    "Connect the adapter" + (" and defer heavy work." if heavy else ".")))
        if heavy:
            evidence = {k: f[k] for k in ("CPU use", "GPU use", "power drawn from the battery") if k in f}
            findings.append(Finding("heavy_on_battery", "warning", "Heavy work is running on battery", evidence,
                                    "Connect the adapter for this work; on battery it drains the charge fast."))
        if power and baseline_power and power >= 1.5 * baseline_power:
            evidence = {"power drawn from the battery": f["power drawn from the battery"], "usual power on battery": f"{baseline_power:.1f} W"}
            for i, (name, impact) in enumerate((top or [])[:3], start=1):
                evidence[f"energy user {i}"] = f"{name} (energy impact {impact:g})"
            findings.append(Finding("fast_drain", "warning", "The battery is draining faster than usual", evidence,
                                    "Quit or pause the biggest energy users if you do not need them."))
    else:
        if discharging_on_adapter:
            evidence = {"battery current": f"{current:.2f} A (discharging)",
                        "power drawn from the battery": f["power drawn from the battery although the adapter is connected"]}
            for key in ("adapter rating", "power drawn by the Mac from the adapter", "time left at the present power (own estimate)"):
                if key in f:
                    evidence[key] = f[key]
            if rating and supplied:
                evidence["share of the adapter rating in use"] = f"{100 * supplied / rating:.0f}%"
            if not supplied:  # Run D2, L01-L02: adapter reported as connected, 0 W in, the battery carrying the load
                # Run D2: the adapter had been unplugged on purpose during the run; macOS still reported
                # "AC attached" while the input power was already 0 W. The status flag lags the power reading.
                findings.append(Finding("adapter_not_supplying", "problem",
                                        "The Mac runs on its battery although macOS still reports the adapter as connected", evidence,
                                        "If the adapter was just unplugged, macOS will catch up in a moment; otherwise reconnect it, "
                                        "check the cable and try another port. The battery is draining."))
            elif assist_only and held:
                # Run D3-D5: limit on, 3.0-3.4 W from the battery with 72-78 W in; limit off, 85 W in and charging.
                evidence["charging held by macOS"] = f["charging held by macOS"]
                findings.append(Finding("battery_assist", "info",
                                        "The battery adds a little power while macOS holds the charge", evidence,
                                        "Normal while the charge is held (charge limit or optimised charging); no action needed."))
            elif assist_only:
                findings.append(Finding("battery_assist", "info",
                                        "The battery adds a little power while the adapter is below its limit", evidence,
                                        "No action needed if it stops within a few minutes; if it continues, try another cable or port."))
            elif at_limit:
                findings.append(Finding("charger_weak", "problem", "The battery discharges because the adapter is at its limit", evidence,
                                        "Use an adapter with more power or lower the load."))
            else:
                findings.append(Finding("adapter_short", "warning",
                                        "The battery discharges although the adapter is below its rating", evidence,
                                        "Try another cable or port; a cable rated for less power can limit the adapter."))
        if "energy left in the battery" in f and not discharging_on_adapter:
            evidence = {k: f[k] for k in ("energy left in the battery", "time on battery at the usual power (own estimate)") if k in f}
            findings.append(Finding("on_adapter_time", "info", "On the adapter the battery is not in use", evidence,
                                    "The time applies once the adapter is unplugged."))
        if asks_mode:
            findings.append(Finding("mode_not_needed", "info", "On the adapter the energy mode does not change the speed of model jobs",
                                    {"measured (qwen3:14b)": "25.3 tokens/s in Automatic and in High Power (runs E1-E3)"},
                                    "Leave it as it is. High Power only lets the fans run faster in work that lasts many minutes."))
        if view.value("battery.is_charging") == 0 and charge is not None and charge < 100 and view.value("battery.fully_charged") != 1 \
                and (current is None or current >= -0.2):
            findings.append(Finding("charging_paused", "info", "Charging is paused by macOS",
                                    {k: f[k] for k in ("charge", "charging held by macOS") if k in f},
                                    "Normal: macOS holds the charge below full to protect the battery."))
    if on_battery and mode_now == 2:
        findings.append(Finding("high_power_on_battery", "info", "High Power Mode is on while running on battery",
                                {"energy mode now": f["energy mode now"]},
                                "Automatic gave the same speed for model jobs (runs E1-E3); on battery Automatic is enough."))
    profile_high = profile.get("power.profile_ac_high_power_mode")
    mode_ac = _num(view, "power.mode_ac")
    if asks_mode and profile_high is not None and mode_ac is not None and (profile_high == 1) != (mode_ac == 2):
        findings.append(Finding("mode_sources_disagree", "info", "Two macOS sources report the adapter's energy mode differently",
                                {"pmset": MODE_NAMES.get(mode_ac, str(mode_ac)), "system_profiler High Power": "on" if profile_high else "off"},
                                "The pmset value matches System Settings and is used."))
    return report


def performance_report(view, storage: dict | None = None, top: list | None = None, job: str | None = None,
                       loaded: dict | None = None, bench: dict | None = None, question: str = "",
                       apps: list | None = None, ports: dict | None = None, work: str | None = None) -> Report:
    """view: a Capture with chip samples; storage: readings from storage.read(); top: [(name, energy impact)]."""
    storage = storage or {}
    report = Report("performance")
    f, findings = report.facts, report.findings
    cpu = cpu_percent(view)
    cores = (_num(view, "cpu.cores"), _num(view, "cpu.performance_cores"), _num(view, "cpu.efficiency_cores"))
    gpu_use = _mean(view, "gpu.usage")
    gpu_active, gpu_freq, gpu_max = _mean(view, "chip.gpu_active"), _mean(view, "chip.gpu_frequency"), _num(view, "chip.gpu_max_frequency")
    levels = [x for x in (_num(view, "thermal.pressure_level"), _num(view, "chip.thermal_pressure_level")) if x is not None]
    level = max(levels) if levels else None
    available = _mean(view, "memory.available")
    total_memory = _num(view, "memory.total")
    swap_used, swap_total = _num(view, "memory.swap_used"), _num(view, "memory.swap_total")
    swapouts = view.features.get("memory.swapouts") if hasattr(view, "features") else None
    busiest, busiest_cpu = view.value("process.max_cpu_name"), view.features.get("process.max_cpu") if hasattr(view, "features") else None

    if cores[0]:
        f["CPU cores"] = f"{cores[0]} ({cores[1]} performance, {cores[2]} efficiency)"
    if cpu is not None:
        f["CPU use"] = f"{cpu}% of all cores"
    if _num(view, "cpu.load_1m") is not None:
        f["load average (1 min)"] = f"{_num(view, 'cpu.load_1m'):.2f}"
    for key, label in (("p0", "performance cluster 1"), ("p1", "performance cluster 2"), ("e", "efficiency cluster")):
        freq, top_freq = _mean(view, f"chip.{key}_cluster_frequency"), _num(view, f"chip.{key}_cluster_max_frequency")
        if freq is not None and top_freq:
            f[f"{label} frequency"] = f"{freq:.0f} MHz of {top_freq} MHz"
    if gpu_use is not None:
        f["GPU use"] = f"{gpu_use:.0f}%"
    if gpu_freq is not None and gpu_max:
        f["GPU frequency"] = f"{gpu_freq:.0f} MHz of {gpu_max} MHz"
    if gpu_active is not None:
        f["GPU active time"] = f"{gpu_active:.0f}%"
    for name, label in (("chip.cpu_power", "CPU power"), ("chip.gpu_power", "GPU power"), ("chip.combined_power", "chip power (CPU + GPU + Neural Engine)")):
        if _mean(view, name) is not None:
            f[label] = f"{_mean(view, name):.1f} W"
    if level is not None:
        f["thermal pressure"] = PRESSURE_NAMES.get(level, str(level))
    if available is not None:
        f["memory available"] = f"{available:.0f}%" + (f" of {gb(total_memory)}" if total_memory else "")
    # Run D5: "memory used by apps" (anonymous pages, vm_stat) is counted differently from "memory available"
    # (memory_pressure: free, inactive and purgeable). 12.2 GB used with 88% of 24 GB available looks like a
    # contradiction, and the model wrote "12.2 GB, 88% of 24 GB" in three runs. The reading is still stored.
    if _num(view, "memory.compressed") is not None:
        f["compressed memory"] = gb(_num(view, "memory.compressed"))
    loaded = loaded or {}
    held_text = "; ".join(f"{name} {size / 1e9:.1f} GB" for name, size in loaded.items())  # given only where it matters
    if swap_used is not None:
        f["swap used"] = gb(swap_used) + (f" of {gb(swap_total)}" if swap_total else "")
    if busiest and busiest_cpu is not None:
        f["busiest process"] = f"{busiest} ({busiest_cpu.last:.0f}% of one core)"
    for i, (name, impact) in enumerate((top or [])[:3], start=1):
        f[f"energy user {i}"] = f"{name} (energy impact {impact:g})"
    free, total = storage.get("storage.free"), storage.get("storage.total")
    if free is not None and total:
        f["storage free"] = f"{gb_disk(free)} of {gb_disk(total)} ({100 * free / total:.0f}%)"
    if storage.get("storage.health"):
        f["storage health (SMART)"] = str(storage["storage.health"])

    # GPU held at low clocks (the state seen on 2026-11-16)
    if gpu_active is not None and gpu_freq is not None and gpu_max and gpu_active >= GPU_BUSY and gpu_freq <= GPU_HELD * gpu_max:
        evidence = {k: f[k] for k in ("GPU active time", "GPU frequency", "GPU power", "thermal pressure") if k in f}
        if level:
            findings.append(Finding("gpu_held_low", "problem", "The GPU is busy but held at its lowest clocks by thermal management (fan speed is not measured)", evidence,
                                    "Shut the Mac down fully, wait 30 seconds and start it again; keep the vents free. "
                                    "If it returns, run Apple Diagnostics for the fans."))
        else:
            findings.append(Finding("gpu_held_low", "warning", "The GPU is busy but running far below its maximum clock", evidence,
                                    "Check the energy mode and the adapter; if it persists, restart the Mac."))
    if level is not None and level >= 2:
        findings.append(Finding("thermal_heavy", "problem", "Thermal pressure is heavy: macOS is slowing the chip down",
                                {"thermal pressure": f["thermal pressure"]}, "Lower the load and free the vents; let the Mac cool down."))
    elif level == 1 and "gpu_held_low" not in report.codes():
        findings.append(Finding("thermal_moderate", "warning", "Thermal pressure is moderate", {"thermal pressure": f["thermal pressure"]},
                                "Expect some slowdown under sustained load; keep the vents free."))
    if busiest_cpu is not None and busiest_cpu.minimum is not None and busiest_cpu.minimum >= BUSY_PROCESS_CPU:
        findings.append(Finding("busy_process", "warning", "One process has kept at least one core fully busy for the whole measurement",
                                {"busiest process": f.get("busiest process", busiest)},
                                "If it is your own work (a model, a build), this is expected; otherwise check it and quit it if it is stuck."))
    if cpu is not None and cpu >= BUSY_CPU:
        findings.append(Finding("cpu_busy", "warning", "The CPU is almost fully busy", {"CPU use": f["CPU use"]},
                                "Wait for the running work to finish or quit what is not needed."))
    swap_fast = swapouts is not None and swapouts.slope_per_minute is not None and swapouts.slope_per_minute >= SWAPOUT_FAST
    if (available is not None and available < MEMORY_LOW) or swap_fast:
        if held_text:
            f["models held in memory by Ollama"] = held_text
        evidence = {k: f[k] for k in ("memory available", "compressed memory", "swap used", "models held in memory by Ollama") if k in f}
        if swap_fast:
            evidence["swap-outs"] = f"{swapouts.slope_per_minute:.0f} pages per minute"
        severity = "problem" if (available is not None and available < MEMORY_CRITICAL) or swap_fast else "warning"
        held = sum(loaded.values()) / 1e9
        advice = ("Quit large apps or browser tabs; run one large model at a time." if held < 2 else
                  f"Ollama holds {held:.1f} GB of models: `ollama stop <model>` frees them at once (idle models unload "
                  "after 5 minutes by themselves). Otherwise quit large apps or browser tabs.")
        findings.append(Finding("memory_short", severity, "Memory is short and macOS is swapping to the SSD", evidence, advice))
    if free is not None and total:
        share = 100 * free / total
        if share < STORAGE_LOW:
            findings.append(Finding("storage_low", "problem" if share < STORAGE_CRITICAL else "warning", "The SSD is almost full",
                                    {"storage free": f["storage free"]}, "Free space: empty the Trash, remove large unused files."))
    if storage.get("storage.health") not in (None, "Verified"):
        findings.append(Finding("storage_failing", "problem", "The SSD reports a health problem",
                                {"storage health (SMART)": f["storage health (SMART)"]}, "Back up now and have the Mac checked."))

    if job:
        description, need, job_models = JOBS[job]
        available_gb = available / 100 * total_memory / GB if available is not None and total_memory else None
        f["job asked about"] = description
        # A model that is already loaded is reused, not loaded again (Run D6, L04).
        reused = [m for m in job_models if m in loaded]
        if reused:
            need = max(WORKING_MEMORY, need - sum(loaded[m] for m in reused) / 1e9)
            f["models of the job already loaded"] = ", ".join(reused)
        f["memory the job needs"] = f"{need:.1f} GB"
        if available_gb is not None:
            f["memory available now"] = f"{available_gb:.1f} GB"
        blocking = [x for x in report.findings if x.severity == "problem"]
        if blocking:
            findings.append(Finding("admit_defer", "warning", "Not now: the Mac has a problem that would slow the job",
                                    {"problem": blocking[0].title}, "Fix the problem first, then start the job."))
        elif available_gb is not None and available_gb < need:
            findings.append(Finding("admit_smaller", "warning", "Not enough free memory for the job as it is",
                                    {k: f[k] for k in ("memory available now", "memory the job needs", "models of the job already loaded") if k in f},
                                    "Quit large apps first, or run it with a smaller model."))
        else:
            findings.append(Finding("admit_run", "info", "The Mac can take the job now",
                                    {k: f[k] for k in ("memory available now", "memory the job needs", "models of the job already loaded", "thermal pressure") if k in f},
                                    "Start it."))
    if work:
        available_gb = available / 100 * total_memory / GB if available is not None and total_memory else None
        on_battery = view.value("power.source") == "Battery"
        present, volts = _num(view, "battery.present_capacity"), _num(view, "battery.voltage")
        energy_wh = present * volts / 1000 if present and volts else None
        if available_gb is not None:
            f["memory available now"] = f"{available_gb:.1f} GB"
        if on_battery and energy_wh:
            f["energy left in the battery"] = f"{energy_wh:.1f} Wh"
        keys = list(WORK) if work == "overview" else [work]
        verdicts = {k: _work_verdict(k, f, findings, available_gb, energy_wh, on_battery) for k in keys}
        if work == "overview":
            def label(k, why):
                hours = re.search(r"about ([\d.]+ h) on battery", why)
                return WORK[k][0] + (f" (about {hours.group(1)})" if hours else "")
            groups = {"yes": [], "with care": [], "not now": []}
            for k, (verdict, why) in verdicts.items():
                groups[verdict].append(label(k, why) if verdict == "yes" else f"{WORK[k][0]} ({why})")
            for verdict, key in (("yes", "can take now"), ("with care", "possible with care"), ("not now", "not now")):
                if groups[verdict]:
                    f[key] = ", ".join(groups[verdict])
            findings.append(Finding("work_overview", "info", "What this Mac can take now",
                                    {k: f[k] for k in ("can take now", "possible with care", "not now") if k in f},
                                    "Measured loads come from synthetic workloads on this Mac; real applications vary."))
        else:
            name, memory_gb, watts, peak, _ = WORK[work]
            f["work asked about"] = name
            f["what this work drew in the measurements"] = f"about {watts:g} W for the whole Mac on average, up to {peak:g} W at the chip, about {memory_gb:g} GB of memory"
            verdict, why = verdicts[work]
            code, severity, title = {"yes": ("work_yes", "info", f"Yes: {name} fits now"),
                                     "with care": ("work_care", "warning", f"Possible with care: {name}"),
                                     "not now": ("work_not_now", "warning", f"Not now: {name}")}[verdict]
            findings.append(Finding(code, severity, title, {"reason": why, **{k: f[k] for k in ("memory available now", "energy left in the battery") if k in f}},
                                    "Measured loads come from synthetic workloads on this Mac; a heavier project or game draws more."))
    if bench:
        _transfer(bench, f, findings)
    # Memory by app, when the question is about memory or apps, or memory is short (added 2026-11-17).
    if apps and (re.search(MEMORY_QUESTION, question, re.I) or "memory_short" in [x.code for x in findings]):
        f["memory by app (resident, largest first)"] = "; ".join(f"{name} {size / GB:.1f} GB ({n} process{'es' if n > 1 else ''})"
                                                               for name, size, n in apps)
        findings.append(Finding("memory_by_app", "info", "The apps holding the most memory", 
                                {"memory by app (resident, largest first)": f["memory by app (resident, largest first)"]},
                                "Quitting the largest app frees the most; shared memory is counted in each process, so the sums run high."))
        short = next((x for x in findings if x.code == "memory_short"), None)
        if short is not None:
            short.evidence["largest app"] = f"{apps[0][0]} {apps[0][1] / GB:.1f} GB"
    if ports:
        listing = []
        for port, speed, connected, devices in ports.get("ports", []):
            what = ", ".join(devices) if devices else ("a device" if connected else "nothing connected")
            listing.append(f"port {port}: {what}" + (f" ({speed})" if speed else ""))
        if listing:
            f["USB-C ports (Thunderbolt / USB4)"] = "; ".join(listing)
        f["USB devices"] = ", ".join(n.strip() for n in ports.get("usb", [])) or "none"
        ssd = ports.get("ssd") or {}
        if ssd:
            f["internal SSD"] = f"{ssd.get('model')}, {ssd.get('size')}, health {ssd.get('health')}, TRIM {ssd.get('trim')}"
        findings.append(Finding("buses", "info", "Ports and connected devices",
                                {k: f[k] for k in ("USB-C ports (Thunderbolt / USB4)", "USB devices", "internal SSD") if k in f},
                                "Nothing to change."))
    # 2026-11-17: asked about transfer speeds, the writer said "no problem with the transfer speeds" although
    # nothing had measured them. A question about something the agent does not measure gets a finding that
    # says so, and the writer is not left to fill the gap.
    for code, pattern, what in NOT_MEASURED:
        if re.search(pattern, question, re.I) and not (code == "transfer" and bench):
            title = f"Not handled: {what}" if code == "user settings" else f"Not measured in this check: {what}"
            findings.append(Finding("not_measured", "info", title, {},
                                    "Say plainly that this is not measured or handled; do not judge it or guess a value."))
    if not any(x.severity in ("warning", "problem") for x in findings):
        findings.append(Finding("no_problem", "info", "No performance problem found in the measurements",
                                {k: f[k] for k in ("CPU use", "GPU use", "memory available", "thermal pressure") if k in f},
                                "Nothing to change."))
    return report


MEMORY_QUESTION = r"메모리|램|(?<![a-z])ram(?![a-z])|memory|어떤\s*앱|무슨\s*앱|앱별|프로그램별|which app"
BUS_QUESTION = r"usb|썬더볼트|thunderbolt|포트|(?<![a-z])ports?(?![a-z])|버스|(?<![a-z])bus(es)?(?![a-z])|연결된\s*(장치|기기)|외장|connected devices?|peripheral"
TRANSFER_QUESTION = r"전송\s*속도|대역폭|읽기\s*속도|쓰기\s*속도|bandwidth|throughput|transfer"
NOT_MEASURED = [
    ("transfer", TRANSFER_QUESTION, "data transfer speeds (memory, SSD)"),
    ("fan", r"팬\s*(속도|rpm|회전)|rpm|fan speed", "fan speed (macOS has no public interface for it)"),
    ("temperature", r"(cpu|gpu|칩|프로세서|코어)\s*(의\s*)?(온도|몇\s*도)|(cpu|gpu|chip|core) temperature",
     "the CPU and GPU temperature (no public interface; only the battery temperature and the thermal pressure level are readable)"),
    # Left to the user on purpose (decided 2026-11-17): the user sets these to taste, the agent does not judge them.
    ("user settings", r"화면\s*밝기|밝기|조도|키보드\s*(백라이트|조명|밝기)|brightness|ambient light|keyboard (backlight|light)",
     "screen brightness, the light sensor and the keyboard light: left to the user's own settings"),
]
TRANSFER_SLOW = 0.7          # share of the normal below which a transfer speed counts as slow


def _transfer(bench: dict, f: dict, findings: list) -> None:
    normal = bench.get("normal") or {}
    names = {"gpu_copy_gbs": "memory bandwidth (GPU copy)", "cpu_copy_gbs": "memory bandwidth (one CPU core)",
             "ssd_write_gbs": "SSD write", "ssd_read_gbs": "SSD read"}
    slow = []
    for key, name in names.items():
        value = bench.get(key)
        if value is None:
            continue
        text = f"{value:g} GB/s"
        if normal.get(key):
            text += f" (normal on this Mac {normal[key]:g} GB/s)"
            if value < TRANSFER_SLOW * normal[key]:
                slow.append(name)
        if key == "gpu_copy_gbs":
            text += "; Apple's figure for the chip is 273 GB/s"
        f[name] = text
    f["CPU to GPU"] = "one shared memory (unified memory): no copy between them, so the memory bandwidth is the transfer speed"
    evidence = {k: f[k] for k in names.values() if k in f}
    if slow:
        findings.append(Finding("transfer_slow", "warning", "Transfer speed below this Mac's normal: " + ", ".join(slow), evidence,
                                "Measure again with other apps closed; if it stays low, restart the Mac."))
    elif any(normal.values()):
        note = " (the normal was recorded now)" if bench.get("normal_set_now") else ""
        findings.append(Finding("transfer_ok", "info", "Transfer speeds are normal" + note, evidence, "Nothing to change."))
    else:
        findings.append(Finding("transfer_measured", "info", "Transfer speeds measured (no normal recorded yet)", evidence,
                                "Run the check once on the adapter to record the normal."))


def work_from_question(question: str) -> str | None:
    """"overview" for "what can I do now?", a WORK key for "can I edit 4K video now?", else None."""
    q = question.lower()
    if re.search(OVERVIEW_QUESTION, q):
        return "overview"
    if not re.search(WORK_QUESTION, q):
        return None
    for key, pattern in WORK_WORDS:
        if re.search(pattern, q):
            return key
    return None


def _work_verdict(key: str, f: dict, findings: list, available_gb, energy_wh, on_battery: bool) -> tuple[str, str]:
    """(verdict, reason) for one kind of work: "yes", "with care" or "not now"."""
    _, memory_gb, watts, _, gpu = WORK[key]
    problems = [x for x in findings if x.severity == "problem"]
    gpu_problem = any(x.code in ("gpu_held_low", "thermal_heavy") for x in problems)
    if problems and (gpu or not gpu_problem) and (memory_gb >= 4 or gpu):
        return "not now", problems[0].title
    if available_gb is not None and available_gb < memory_gb:
        return "with care", f"needs about {memory_gb:g} GB of memory, {available_gb:.1f} GB available: close large apps first"
    if on_battery and energy_wh:
        hours = energy_wh / watts
        if hours < 0.75:
            return "not now", f"about {hours * 60:.0f} min on battery at {watts:g} W: connect the adapter"
        return "yes", f"about {hours:.1f} h on battery at the {watts:g} W this work drew in the measurements"
    return "yes", f"needs about {memory_gb:g} GB of memory; {available_gb:.1f} GB available" if available_gb is not None else "no limit found"


def job_from_question(question: str) -> str | None:
    q = question.lower()
    if not re.search(r"돌려도|돌릴|실행해도|실행할|시작해도|can i run|is it ok to run|should i run|start .* now", q):
        return None
    if re.search(r"이미지|사진|비전|vision|image|photo", q):
        return "vision"
    if re.search(r"긴|오래|시험|평가|전체|밤새|long|overnight|test run|benchmark|eval", q):
        return "long_run"
    if re.search(r"문서|pdf|논문|document|paper|14b", q):
        return "document"
    return "light"
