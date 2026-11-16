# Stage 7 design: hardware diagnosis, chip-aware from the start

Author: PARK, SEHO

Goal: questions such as "how is my battery?", "why is my Mac slow or hot?" or "can I run this now?" are answered from real measurements of the machine, with a diagnosis and advice, within the budgets in [roadmap.md](roadmap.md). The layer built here (telemetry, store, sampler, router) is used by every later stage.

## 1. Requirements

| Requirement | Target |
|---|---|
| Quick answer from stored readings | under 3 s |
| Diagnosis with a per-second capture of n seconds | n + 5 s |
| Background sampler | under 1% of one core, at background priority |
| Rights | read-only; administrator rights only for `powermetrics` (one sudoers rule for that command) |
| Dependencies | none new: Python standard library and macOS built-in commands |
| Tests | offline, on recorded command outputs; scenario sets for the agents |
| Honesty | the language model does not compute; every number in an answer is checked against the measurements |

## 2. Layers

| Layer | Embedded analogue | Role |
|---|---|---|
| Readers (`agent/device/sources/`) | device drivers | run a macOS command, parse its output |
| `Reading` (`agent/device/readings.py`) | hardware abstraction layer | one record format and SI units for every source |
| Store and sampler (`store.py`, `sampler.py`) | ring buffer and periodic task | readings every 10 s, oldest removed after 7 days |
| Capture (`capture.py`) | burst sampling | n seconds at 1 Hz or faster during a diagnosis |
| Diagnosis (`agent/agents/`) | application | measure → compute → rules → advice |
| Router (`agent/router.py`) | interrupt dispatch | sends a question to its agent in under 1 ms when the rules decide |
| Answer writer | output stage | small model writes the sentences; code checks the numbers |

```
question --> router (rules; qwen3:1.7b only if undecided)
                |
        +-------+--------+
        v                v
  battery agent    performance agent      (Stage 8: Wi-Fi agent)
        |                |
        +-------+--------+
                v
  store (recent readings, window statistics)   capture (n s, per second, on demand)
                ^                                   |
  sampler (10 s, background priority) <-- readers --+
                                          battery | power | thermal | load | memory | storage | buses | powermetrics | SMC
```

## 3. Files

```
agent/device/
  readings.py        Reading record, units, naming rule
  shell.py           run a command with a timeout; record and replay outputs for tests
  sources/
    battery.py       cycle count, design / full-charge / present capacity, voltage, current, temperature, charging state
    power.py         power source, adapter watts, power mode, macOS time-remaining estimate
    thermal.py       thermal pressure level
    load.py          CPU and GPU utilisation, load average, energy-heavy processes
    memory.py        memory used, pressure, compression, swap
    storage.py       free space, health status, throughput
    buses.py         Thunderbolt and USB devices and link speeds
    chip.py          powermetrics: CPU cluster, GPU and Neural Engine frequency, residency and power
    smc.py           stretch: fan speed and temperature sensors from the system management controller
  store.py           SQLite store: write batches, latest value, window statistics, retention
  sampler.py         background sampler; measures its own CPU time
  capture.py         per-second capture of n seconds; features (mean, max, min, trend)
agent/agents/
  battery_agent.py
  performance_agent.py
agent/router.py
scripts/
  probe_device.py    what this Mac allows; recorded outputs for tests (identifiers removed)
  run_device_set.py  scenario runner
evals/device/
  battery.toml, performance.toml, router.toml
tests/
  fixtures/device/   recorded outputs (from the probe, identifiers removed)
  test_device.py
```

## 4. Reading format

```
Reading(name="battery.cycle_count", value=312, unit="count", time=<ISO time>, quality="ok")
```

- Name: `<source>.<item>`. Units: V, A, W, Wh, mAh, %, °C, MHz, bytes, bytes/s, count, level.
- Readers convert to SI units (macOS reports mV, mA and hundredths of a degree).
- `quality`: `ok`, `missing` (could not be read; never an exception), `estimated` (computed).

## 5. Sources

To be confirmed by the probe (`scripts/probe_device.py`).

| Readings | Source | Period | Rights |
|---|---|---|---|
| Battery: cycle count, capacities, voltage, current, temperature, charging | `ioreg -rn AppleSmartBattery -a` (plist) | 10 s | none |
| Power source, charge, macOS time remaining | `pmset -g batt` | 10 s | none |
| Adapter watts, power mode | `pmset -g ac`, `pmset -g` | on demand | none |
| Battery condition and maximum capacity as macOS reports it | `system_profiler SPPowerDataType -json` | on demand | none |
| Thermal pressure | `notifyutil -g com.apple.system.thermalpressurelevel`, `pmset -g therm` | 10 s | none |
| CPU utilisation, load average | `ps`, `sysctl vm.loadavg` | 10 s | none |
| GPU utilisation | `ioreg -c IOAccelerator` performance statistics | 10 s | none |
| Energy-heavy processes | `top -o power` | on demand | none |
| Memory pressure, swap | `memory_pressure`, `vm_stat`, `sysctl vm.swapusage` | 10 s | none |
| Free space, health, throughput | `df`, `diskutil info -plist /`, `iostat` | 10 min | none |
| Buses and links | `system_profiler SPThunderboltDataType SPUSBDataType SPNVMeDataType -json` | on demand | none |
| CPU / GPU / ANE frequency, residency, power | `sudo -n powermetrics` | capture | sudoers rule for that command |
| Fan speed, temperatures | system management controller keys (IOKit) | capture | stretch, no public interface |

Outputs that contain identifiers (serial numbers, hardware UUIDs, MAC addresses, network names, the user name) are scrubbed before they are stored as test fixtures.

## 6. Store, sampler and capture

- Store: one SQLite table `readings(time, name, value, unit, quality)`, indexed by name and time; queries: latest, window mean / max / min, series; rows older than 7 days removed; one transaction per sampling round.
- Sampler: fast sources every 10 s, storage every 10 min; started with background priority (`taskpolicy -b`), which macOS schedules on the efficiency cores; it records its own CPU time per round. Experiment: 10 minutes at default and at background priority, CPU time and power compared.
- Capture: during a diagnosis, n seconds (default 10) of fast sources and `powermetrics` at 1 s; features per reading: mean, maximum, minimum, slope.

## 7. Battery agent

Computed by code:

| Value | Formula |
|---|---|
| Health | full-charge capacity / design capacity × 100 % |
| Power | voltage × current (W); mean of the last 2 minutes |
| Remaining energy | present capacity (mAh) × voltage / 1000 (Wh) |
| Remaining time (discharging) | remaining energy / mean power |
| Time to full (charging) | (full-charge − present capacity) / charging current |
| Comparison | own estimate against the macOS estimate (baseline for the Stage 9 model) |

Rules:

| Condition | Advice |
|---|---|
| Health < 80% or cycles ≥ 1,000 (Apple's limits) | replacement recommended |
| Health 80-85% | watch the trend |
| On battery and CPU ≥ 70% or GPU ≥ 50% for 2 min | connect power |
| On power, same load, power mode not High Power | suggest High Power Mode (changed only after confirmation) |
| Charge < 20% with heavy load | defer the job or charge |
| Battery temperature ≥ 35 °C | heat warning |
| Mean power ≥ 1.5 × the logged usual | name the three biggest energy users |

## 8. Performance agent

Diagnosis from a capture, each rule with the readings that triggered it:

| Fault | Signature |
|---|---|
| GPU held at low clocks (seen on 2026-11-16) | GPU residency high, frequency in the lowest states, GPU power low, thermal pressure above nominal, no fan response |
| Runaway process | one process above 90% of a core for the whole capture |
| Memory thrashing | pressure high, swap growing, compressed memory growing |
| Charger too weak | on power but battery discharging under load, adapter watts below the machine's rating |
| Storage full or slow | free space under 10%, or throughput far below the measured normal |
| Heat without fan response (stretch, needs SMC) | temperatures rising, fan speed flat |

Also answers "can I run this now?" by admission control: each heavy job's memory, time and power are measured once; a job starts, runs with a smaller model, or is deferred from the current readings. Long runs start with a 20-second speed check and are paced by a feedback controller that keeps power or thermal pressure below a target (step response recorded).

## 9. Router

- Rule table of keywords and patterns per agent, Korean and English (battery: 배터리, 충전, 방전, 교체, battery, charge; performance: 느려, 뜨거, 발열, 팬, slow, hot; Stage 8 adds network).
- One matching agent → route; several or none → `qwen3:1.7b` with a JSON schema; still undecided → the existing agent loop. Document and image paths keep their own pipelines.
- Accuracy measured on 30 router questions.

## 10. Answer writer

`qwen3:4b` receives only the structured result (readings, computed values, findings, advice) and writes the answer. The number check from Stages 4-6 compares every number with the measured and computed values; if the model keeps changing numbers, the numbers are filled in by code.

## 11. Verification

| What | How |
|---|---|
| Readers | recorded outputs of this Mac (`tests/fixtures/device/`) |
| Computations and rules | boundary cases (79.9% and 80.0% health, 69% and 70% load) |
| Store | write, query, retention |
| Sampler | CPU time over 10 minutes at both priorities |
| Router | 30 questions |
| Agents | scenario sets with the expected diagnosis written before the run: charging, on battery, heavy load, the GPU state of 2026-11-16 replayed from its readings |
| Budgets | time per answer from `logs/model_calls.jsonl`, energy from `powermetrics` |

## 12. Risks

| Risk | Response |
|---|---|
| Command outputs differ from the expected format | probe first; fixtures from this Mac |
| A value cannot be read without rights | marked `missing`; the rule that needs it answers "cannot tell" |
| Instantaneous power is noisy | 2-minute mean, stated in the answer |
| The small model changes numbers | number check; numbers filled in by code if needed |
| The sampler costs more than it saves | its CPU time is measured; the period is raised if over budget |
| SMC keys differ on this model | stretch item; the diagnosis works without fan data |

## 13. Schedule

| Date | Work |
|---|---|
| 11-16 | design; probe; sudoers rule for `powermetrics` |
| 11-17 | Reading, shell helper, readers, fixture tests |
| 11-18 | store, sampler and its experiment, capture, chip readings |
| 11-19 | performance diagnosis rules, performance agent, router |
| 11-20 | battery agent, admission control, speed check, feedback controller |
| 11-21 | scenario runs, budgets measured, records, stage commit |

## 14. Probe results (2026-11-16)

All 21 sources are readable on this Mac (MacBook Pro, Apple M4 Pro, 10 performance and 4 efficiency cores, 24 GB). `powermetrics` runs without a password through the sudoers rule for that command. Readings found beyond the plan:

| Reading | Source | Use |
|---|---|---|
| Whole-system input power on the adapter (`SystemPowerIn`, `SystemVoltageIn`, `SystemCurrentIn`), adapter efficiency loss | `PowerTelemetryData` in the battery registry | Total power on AC without rights; on battery, voltage × current of the pack |
| Cell voltages (three cells in series) and per-cell maximum charge (`Qmax`) | `BatteryData` in the battery registry | Cell balance check |
| Charger state and the reason charging is paused | `ChargerData` | Explains "connected but not charging" (charging held near 90%) |
| Adapter voltage and current offers (USB Power Delivery profiles) | `AdapterDetails` | Charger check |
| GPU utilisation without rights (device, renderer, tiler) and GPU memory in use | `IOAccelerator` statistics | Load without `powermetrics` |
| Thermal pressure level without rights | `notifyutil` | Background sampler |
| Signal and noise of the Wi-Fi link; signal of connected Bluetooth devices | `system_profiler` | Stage 8 |

Battery health is reported three ways: macOS shows maximum capacity 90% ("Good"); the raw full-charge capacity is 86.0% of the design capacity; the nominal capacity is 88.4%. Apple's 80% service limit refers to the figure macOS shows, so the replacement rule uses it, and the answer also gives the raw ratio.

Process names in recorded outputs are replaced by numbered placeholders, and battery manufacturing data is removed, before the outputs are kept as test fixtures.

## 15. Battery-aware power policy (proposed 2026-11-16, built with admission control)

On the adapter, the mode is already High Power: macOS applies the adapter's setting when power is connected, so the agent only confirms it ("on the adapter: running in High Power Mode"). On battery, the agent chooses the mode for the job and restores the previous mode afterwards:

| Job | Examples | Mode on battery |
|---|---|---|
| Light | readings, battery or performance answers, routing | Low Power |
| Medium | document questions with the small models | Automatic |
| Heavy | vision, long runs, the 14B model | High Power only if the charge is at least 50% and the job's measured energy fits; otherwise Automatic with advice to connect power or defer |
| Any, charge below 20% | | Low Power; heavy jobs deferred |

- Switching needs administrator rights. The sudoers rule is limited to the exact commands `pmset -b powermode 0`, `1` and `2` (battery settings only), not `pmset` in general.
- Evidence for the table: each job class is run in each mode on battery, and its energy is integrated from the battery's voltage × current. Running fast at high power can use less or more energy than running slowly ("race to idle"); the measurement decides, not an assumption.
