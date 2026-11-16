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

| Dates | Stage | Main deliverable |
|---|---|---|
| 11-16 | 6 close | Run 45 graded; a short holdout; sensor probe run on the Mac |
| 11-17 to 11-19 | 7 Device layer and battery agent | Telemetry layer, background sampler on efficiency cores, question router, battery and power agent |
| 11-20 to 11-22 | 8 Wi-Fi agent | Link reading, 10-second active test, fault location, use-case verdict, best-network ranking, anomaly detection |
| 11-23 to 11-25 | 9 Coverage planning | Floor plan, measured signal map, fitted indoor propagation model, router placement and count |
| 11-26 to 11-27 | 10 Chip-aware optimisation | Small models, admission control, thermal and power feedback control, battery-aware policy, battery-time model |
| 11-28 to 11-29 | 11 iPhone client | Ask the Mac agent from the iPhone (Shortcuts, Siri); Bluetooth "smart key" as a stretch goal |
| 11-30 | 12 Portfolio | README results, demo recording, final scenario runs |

Progress is checked against this table every day in `docs/devlog.md`. If a stage runs late, the stretch items (marked *stretch*) are dropped first, then Stage 11 shrinks to the Shortcuts client.

## Stage 6 — Tables, financial statements and graphs (closing)

- [x] Development set and baseline (Run 42: ✅ 11 of 23)
- [x] Picture pages read, charts transcribed as tables, statement totals and calculations checked by code (Run 43: ✅ 18)
- [x] Chart pages, cached page readings, a related figure no longer given for the asked item (Run 44: ✅ 19, 83%, "not in the document" 3/3)
- [x] Arithmetic explained across paragraphs; page index no longer given to the vision model
- [ ] Run 45: tables set and regression of every earlier document set, gates in `evals/documents/tables.md`
- [ ] Short holdout on unseen financial documents, run once

Done when: extracted figures pass the code checks and chart values are never presented as exact.

## Stage 7 — Device layer and battery agent (11-17 to 11-19)

Telemetry layer (`agent/device/`): one reader per source, each returning values with units and a timestamp, read-only, no administrator rights by default.

- [ ] Sensor probe: which readings this Mac allows (battery registry, power and thermal state, memory pressure, storage, Wi-Fi radio, chip power with and without administrator rights)
- [ ] Readers: battery (charge, cycle count, design and full-charge capacity, voltage, current, temperature), power source and power mode, thermal state, CPU and GPU load, memory pressure and swap, storage space and throughput
- [ ] Background sampler at a fixed period, run at background priority so macOS places it on the efficiency cores; its own CPU time and energy measured on both core types
- [ ] Question router in code (keywords and patterns, under 1 ms); the small model only when the rules do not decide
- [ ] Battery and power agent: health against Apple's published limits (80% of design capacity, 1,000 cycles) → replacement advice; heavy workload on battery → connect power or use High Power Mode; remaining time from measured power (voltage × current) and remaining energy; the biggest energy users
- [ ] Discharge sessions logged from day one (training data for Stage 10)

Verify: readers tested on recorded outputs; scenario set for the battery agent (on battery, charging, under load).
Done when: "how is my battery?" answers in under 5 seconds with measured values, and every scenario gets the expected advice.

## Stage 8 — Wi-Fi and network agent (11-20 to 11-22)

- [ ] Link reading: signal strength, noise, signal-to-noise ratio, channel, band, channel width, PHY mode, link rate
- [ ] 10-second active test: latency, jitter and loss to the router and to the internet; DNS lookup time; download and upload throughput
- [ ] Fault location: Wi-Fi link, router, internet provider or DNS, from which segment is slow
- [ ] Use-case verdict from published requirements (online gaming, video call, streaming, messaging), with the reason
- [ ] Channel scan: nearby networks per channel and band, congestion score, channel advice for my router
- [ ] Best network among several (for example public Wi-Fi): ranked from the scan, then the top candidates tested with confirmation
- [ ] Anomaly detection: a baseline from the background log (robust statistics per hour of day); "is my network acting strange?" compares now with the baseline
- [ ] Actions with confirmation: reconnect, switch band or network

Verify: scenarios created on purpose (near and far from the router, behind walls, a saturated link); the fault location is checked against where the problem was created.
Done when: "why is my Wi-Fi slow?" returns the faulty segment, a use-case verdict and a fix in about 15 seconds.

## Stage 9 — Coverage planning on a floor plan (11-23 to 11-25)

- [ ] Floor plan with a known scale; walls marked as line segments with a material type
- [ ] Signal measured at 15-25 points around the home, with the router position recorded
- [ ] Indoor propagation model fitted by least squares: path loss = PL₀ + 10·n·log₁₀(d) + Σ wall losses (multi-wall model); path-loss exponent and wall losses reported
- [ ] Model scored on held-out points it was not fitted on
- [ ] Coverage map for any router position; placement search and the number of routers needed for a target level (for example −67 dBm for video calls) in every room
- [ ] Agent question: "where should I put the router?" / "how many access points do I need?"

The floor plan of my home is kept out of the repository; the repository uses a synthetic plan with the same method.

Verify: prediction error on held-out points; the predicted dead zones checked by measurement.
Done when: the fitted model predicts held-out points within a stated error and the placement advice is checked at the predicted weak spots.

## Stage 10 — Chip-aware optimisation (11-26 to 11-27)

- [ ] Profile of every model call (load, prompt, generation time, memory held) from `logs/model_calls.jsonl`
- [ ] Small model for routing fallback and answer writing (`qwen3:4b`, `qwen3:1.7b` compared with `qwen3:8b` on the scenario sets); the large models only for documents
- [ ] Memory budget: which models stay loaded together in 24 GB; context size per call
- [ ] Admission control: each heavy job's memory, time and power measured once; a new job is started, run with a smaller model, or deferred from the current load
- [ ] Thermal and power feedback control: workload adjusted to keep power or the thermal state below a target; step response recorded (overshoot, settling time)
- [ ] Battery-aware policy: model size and pace chosen from charge level and remaining work
- [ ] Battery remaining-time model trained on the logged discharge sessions; compared with the macOS estimate (`pmset -g batt`) on unseen sessions
- [ ] *stretch*: on-device text recognition (Apple Vision) instead of the vision model for text pages; MLX against Ollama

Verify: time, memory and energy per answer before and after; the controller's response plotted.
Done when: the device agents answer with the small model at the same scenario grades, and the controller holds its target in the recorded test.

## Stage 11 — iPhone client (11-28 to 11-29)

- [ ] Local HTTP endpoint on the Mac (home network only, with a shared key)
- [ ] iPhone Shortcut "Ask Mac": a question typed or spoken through Siri goes to the Mac agent, and the answer comes back to the phone
- [ ] iPhone-side measurement: the phone tests the Wi-Fi where it is ("how is the Wi-Fi in the bedroom?")
- [ ] *stretch*: Bluetooth Low Energy "smart key": a small iOS app (Swift, CoreBluetooth); when the phone comes near, the Mac sends a status summary; a button asks for a diagnosis

Verify: answers on the phone match the answers on the Mac; round-trip time measured.
Done when: a Mac diagnosis can be asked and read on the iPhone.

## Stage 12 — Portfolio (11-30)

- README with the architecture, results tables and plots (coverage map, controller response, speed before and after)
- Demo recording: a spoken question on the iPhone → diagnosis on the Mac → answer on the phone
- Final scenario runs for every agent

## Later

- Image generation (painter), postponed: the earlier plan for Stages 8-9 (local image runner, see-paint-check loop) moves after Stage 12
- Visual reasoning experiment (thinking vision model), redesign of the accurate profile, a vision holdout on new images
- Open items from Stage 5: page descriptions sometimes win over confirmed equation readings (RV1, EQ4); braces read as exponents (RV4); inline formulas from the text layer (RV8)
