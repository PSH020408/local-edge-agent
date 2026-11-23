# Roadmap

Author: PARK, SEHO

Principle: **everything runs locally** on the devices I own: a MacBook Pro (Apple M4 Pro, 24 GB unified memory) and an iPhone. No cloud models or services.

## Direction (from 2026-11-16)

Stages 0-6 built a local agent that reads documents, images and formulas with exact, code-checked answers. From Stage 7 the project treats the MacBook as one large embedded device and the iPhone as a client node:

- **Sense**: a telemetry layer reads the machine's own hardware (battery, power, thermal state, memory, storage, Wi-Fi radio) in one uniform format, sampled in the background on the efficiency cores.
- **Decide**: domain agents (battery, Wi-Fi, performance) run fixed diagnostic procedures in code: measure, compute, classify, rank causes. Lightweight models (statistics, a small classifier, a fitted propagation model) are used where a rule is not enough.
- **Act**: the agent proposes fixes and applies them only after confirmation; it also controls its own workload against power, thermal and memory limits.
- **Explain**: a small local language model turns the structured result into an answer. It does not compute or invent numbers; the numbers in the answer are checked against the measurements, as in Stages 4-6.

The goal is engineering problem solving with the hardware at hand (embedded systems, wireless communication, control), not imitating a cloud chatbot. A question such as "why is my Wi-Fi so slow?" goes straight to the Wi-Fi agent, which measures, decides and answers in seconds.

## How every stage is verified

1. Every agent has a scenario set: questions with the expected route, diagnosis and action, and conditions created on purpose (moving away from the router, a heavy workload, running on battery). Each answer is graded against the measurements and the expectation written before the run.
2. Fitted models are scored on data they were not fitted on: held-out measurement points for the coverage model, unseen discharge sessions for battery-time prediction, unseen days for the anomaly detector.
3. Predictions are written before a run; a single-case drop counts only when repeats confirm it.
4. Every failure gets a fix and an offline regression test (`python -m unittest discover -s tests`). Sensor readers are tested with recorded outputs, so tests run without the hardware.
5. Speed and memory are measured for every agent (`logs/model_calls.jsonl`, `scripts/profile_calls.py`).
6. Results go to `docs/benchmarks.md`, decisions and progress to `docs/devlog.md`; a stage is committed when its "done when" line is met.

## Done

| Stage | What | Runs | Commit |
|---|---|---|---|
| 0 Foundation | Ollama on macOS, `qwen3:8b` / `qwen3:14b`, agent loop with tool calling, JSONL traces, speed benchmarks | 1-2 | 8ec9cdc |
| 1 Time | Current time, time zones, date arithmetic, date differences, natural-language dates | 3-5 | 6966262 |
| 2 Math | Engineering calculator (numpy, scipy, sympy), unit-aware calculation (pint), loop guards | 6-10 | 44f5c99 |
| 3 Vision | Separate vision model as a tool, zoom, two-reading verification, image question planner, one-command test set | 11-24 | b4c74bc |
| 4 Documents | PDF and PowerPoint reading, page and passage search, vision for equations and figures, cited answers with code checks, four holdouts | 25-33 | c20fa03 |
| 5 Formulas | Equations located, cropped, read twice and checked against the image; given first in document answers; a fifth holdout | 34-41 | ea2a9b2 |

## Schedule to 2026-11-30

Four stages. Efficiency is not a separate stage: every agent from Stage 7 on is built within a time,
memory and energy budget, on the small models, with the background work on the efficiency cores.
Only what needs collected data comes later (the battery-time model is trained in Stage 9 on the
discharge sessions logged from Stage 7 on).

| Dates | Stage | Main deliverable |
|---|---|---|
| 11-16 | 6 close | Run 45 graded and checked (done); a short holdout on unseen financial documents |
| 11-16 to 11-21 | 7 Hardware diagnosis, chip-aware from the start | Telemetry of every readable part of the machine, background sampler on the efficiency cores, per-second capture, performance and fault diagnosis, battery and performance agents, question router, budgets, admission control, thermal and power feedback control |
| 11-22 to 11-26 | 8 Wireless | Wi-Fi diagnosis, coverage on a floor plan, Bluetooth coverage, propagation compared across bands |
| 11-27 to 11-28 | 9 iPhone client | Ask the Mac agent from the iPhone (Shortcuts, Siri); measurements where the phone is; battery-time model trained on the logged sessions |
| 11-29 to 11-30 | 10 Portfolio | README results and plots, demo recording, final scenario runs |

Progress is checked against this table every day in `docs/devlog.md`. If a stage runs late, items
marked *stretch* are dropped first.

## Budgets for every device agent

| Budget | Target |
|---|---|
| Quick answer from stored readings | under 3 s |
| Diagnosis with a per-second capture of n seconds | n + 5 s |
| Background sampler | under 1% of one core, at background priority (efficiency cores) |
| Language model | `qwen3:4b` for answers, `qwen3:1.7b` for routing fallback; the 14B and vision models only for documents |
| Rights | read-only; administrator rights only for `powermetrics`, allowed for that one command |
| Numbers | every number in an answer is checked against the measurements |

Time, memory and energy per answer are measured for every agent (`logs/model_calls.jsonl`, `powermetrics`).

## Stage 6 — Tables, financial statements and graphs (closing)

- [x] Development set and baseline (Run 42: ✅ 11 of 23)
- [x] Picture pages read, charts transcribed as tables, statement totals and calculations checked by code (Run 43: ✅ 18)
- [x] Chart pages, cached page readings, a related figure no longer given for the asked item (Run 44: ✅ 19, 83%, "not in the document" 3/3)
- [x] Arithmetic explained across paragraphs; page index no longer given to the vision model
- [x] Run 45: tables set and regression of every earlier document set; one regression (formula slides read as [none]) fixed and checked; every gate met; tables 87%
- [ ] Short holdout on unseen financial documents, run once

Done when: extracted figures pass the code checks and chart values are never presented as exact.

## Stage 7 — Hardware diagnosis, chip-aware from the start (11-16 to 11-21)

Design: [stage7_design.md](stage7_design.md).

Core (no administrator rights):
- [x] Sensor probe: what this Mac allows, with recorded outputs for offline tests (identifiers removed)
- [x] Telemetry layer (`agent/device/`): one reader per source, values in SI units with a timestamp and a quality flag
- [x] Battery: charge, cycle count, design, full-charge and present capacity, voltage, current, temperature; adapter power; power mode
- [x] Load and memory: CPU and GPU utilisation, load average, memory pressure, swap, energy-heavy processes
- [x] Storage: free space, health status, read and write throughput; buses and links (Thunderbolt, USB)
- [x] Thermal pressure level
- [x] Store (SQLite, 21 days) and background sampler at background priority; battery read once a minute, the rate at which the registry publishes
- [ ] Sampler cost measured at default and background priority (10 minutes each) (*deferred*)
- [x] Discharge sessions logged (sampler running since 11-16; training data for Stage 9)

Extended:
- [x] Per-second capture of CPU, GPU and Neural Engine frequency, residency and power (`powermetrics`, allowed without a password for that one command)
- [ ] Fan speed and temperature sensors from the system management controller (*stretch*: no public interface; keys differ by model)
- [x] Short benchmarks for memory bandwidth and SSD throughput, compared with the measured normal (run when a question asks about transfer speeds)

Diagnosis and agents:
- [x] Capture of n seconds → features (mean, maximum, trend) → rules: GPU held at low clocks, runaway process, memory thrashing, battery ageing or heat, charger too weak or not supplying, charge held by macOS, storage full or failing
- [x] Battery agent: health against Apple's limits (80%, 1,000 cycles), remaining time from measured power, High Power Mode and charger advice, reasons for fast drain or heat
- [x] Performance agent: "why is my Mac slow or hot?", "can I run this now?"
- [x] Question router: rules first, `qwen3:1.7b` when the rules do not decide (device set Runs D1-D5: 40 of 40 in D5)
- [x] Admission control for heavy jobs
- [x] Battery-aware energy mode switching with restore; job energy from hardware counters (`evals/device/energy.md`)
- [x] Energy modes for LLM jobs settled by speed (E1-E3: High Power = Automatic; the gauge cannot resolve one job's energy)
- [x] Workload set W: 15 scenarios on the adapter (all tiers) and on battery (tiers 0-2); battery tiers 3-5 deferred
- [x] Speed check before long runs (`scripts/speed_check.py`; test-set runs stop when the Mac is under 60% of its normal speed)
- [x] Power feedback controller (PI, pacing the work), tested on a simulated plant
- [x] Controller held at its targets in a recorded hardware test (C2: mean within 0.1 W, in the band after 3-5 s; `evals/device/controller.md`)

Verify: readers tested on recorded outputs; scenario sets for both agents (on battery, charging, heavy load, the GPU state seen on 2026-11-16 replayed from its readings); router accuracy on 30 questions; budgets measured.
Done when: both agents answer within budget with measured values, every scenario gets the expected diagnosis, and the controller holds its target in a recorded test.

## Stage 8 — Wireless: Wi-Fi, coverage and Bluetooth (planned 11-22 to 11-26, done 11-21)

- [x] Wi-Fi link reading: signal, noise, SNR, SINR (802.11 CCA rule), channel, band, width, modulation (MCS), link rate
- [x] Active test: latency, spikes over the usual ping, share of late pings, loss to the router and the internet, DNS time, throughput; fault location (Wi-Fi link or beyond the router); verdicts for games, calls, 4K, messaging and large files from published requirements
- [x] The best of several networks: ranked from one scan, a join-and-measure test when it is close (`wifi_choice.py`, `wifi_here.py`)
- [x] Coverage on a floor plan: 25 points, two walks, three routers; the multi-wall model failed its gate (12-14 dB), maps interpolated (IDW); a door-path model (loss per bend) predicts held-out points within 3-4 dB
- [x] Bluetooth: LE coverage from an iPhone; connected and paired devices, battery, in range, and causes of dropouts (battery, signal, 2.4 GHz sharing)
- [x] Games and Apple's Continuity features: experiments C1 and G1; AirDrop is the only setting that delays the pings
- [x] The connection card: plain words by default, the radio chain and evidence on request
- [ ] Propagation compared across bands (2.4 GHz, 5 GHz, Bluetooth): data recorded, not fitted

The floor plan of my home stays out of the repository.
Done when: "why is my Wi-Fi slow?" returns the faulty segment, a verdict and a fix, and the coverage model predicts
held-out points within a stated error. Met: the card names the segment and the fix; the door-path model 3.1 and
4.4 dB on the held-out points (proposed after the walks, so a new walk is its real test).

- [x] Model per question (11-23): light 8B, heavy 14B for hard questions or when the light one does not finish; experiment Q1 to compare with each model alone

Planned from the design review of 11-23 ([reviews.md](reviews.md)): experiment L1, whether the language model
adds anything to the network answers (new phrasings routed by rules alone against rules plus the model; the card
alone against the card with the model's text, judged by people without the background).

## Stage 9 — iPhone client (11-27 to 11-28)

- [ ] Local HTTP endpoint on the Mac (home network only, shared key)
- [ ] iPhone Shortcut "Ask Mac" with Siri: question to the Mac agent, answer back on the phone
- [ ] Measurements where the phone is ("how is the Wi-Fi in the bedroom?")
- [ ] Battery remaining-time model trained on the discharge sessions logged since Stage 7, compared with the macOS estimate on unseen sessions
- [ ] *stretch*: Bluetooth Low Energy "smart key" iOS app (Swift, CoreBluetooth)

Done when: a Mac diagnosis can be asked and read on the iPhone.

## Stage 10 — Portfolio (11-29 to 11-30)

- README with the architecture, results tables and plots (coverage maps, controller response, budgets before and after)
- Demo recording: a spoken question on the iPhone → diagnosis on the Mac → answer on the phone
- Final scenario runs for every agent
- Answer examples per agent exported from the run reports (`logs/` stays private: live cases name the processes running on this Mac), and screenshots of the terminal and the iPhone

## Later

- Image generation (painter), postponed: the earlier plan (local image runner, see-paint-check loop) moves after Stage 10
- Visual reasoning experiment (thinking vision model), redesign of the accurate profile, a vision holdout on new images
- Open items from Stage 5: page descriptions sometimes win over confirmed equation readings (RV1, EQ4); braces read as exponents (RV4); inline formulas from the text layer (RV8)
