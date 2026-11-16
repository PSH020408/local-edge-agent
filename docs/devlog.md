# Development log

Author: PARK, SEHO

Dated entries: what was built, what was decided and why, and progress against the schedule in [roadmap.md](roadmap.md). Detailed results are in [benchmarks.md](benchmarks.md) and [findings.md](findings.md).

## Progress against the schedule

| Stage | Planned | Started | Finished | State |
|---|---|---|---|---|
| 6 close | 11-16 | 11-15 | | Regression passed (Run 45 and check); holdout pending |
| 7 Hardware diagnosis, chip-aware from the start | 11-16 to 11-21 | 11-16 | | Core built and tested (Runs D1-D5, no wrong answer in D5); power policy, speed check, feedback control, fan reading and the logging of battery sessions to do |
| 8 Wireless: Wi-Fi, coverage, Bluetooth | 11-22 to 11-26 | | | |
| 9 iPhone client and battery-time model | 11-27 to 11-28 | | | |
| 10 Portfolio | 11-29 to 11-30 | | | |

## History before this log

| Dates | Stage | Commit |
|---|---|---|
| 10-29 | 0 Foundation: Ollama, agent loop, tool calling, speed benchmarks | 8ec9cdc |
| 10-31 | 1 Time and date tools | 6966262 |
| 11-01 | 2 Engineering math and unit-aware calculation | 44f5c99 |
| 11-05 | 3 Vision tools and the image question planner | b4c74bc |
| 11-06 to 11-08 | 4 Documents: page and passage search, cited answers, four holdouts | 12d35a0 … d81fe90 |
| 11-10 to 11-15 | 5 Formulas: equations read from the page image, a fifth holdout | abf92cd … 7f75361 |
| 11-15 to 11-16 | 6 Tables, statements and charts: 48% → 83% on the development set | f1f50cb, 745310e |

## 2026-11-16 — Direction change: from a document agent to an edge AI agent

**Decision.** From Stage 7 the project treats the MacBook as an embedded device and the iPhone as a client node. The agent senses the machine's own hardware, diagnoses in code, acts with confirmation, and uses a small language model only to explain. Image generation is postponed until after Stage 12.

**Why.**
- Stages 0-6 showed what a local language model can do when code does the exact work. Extending that to more document types would mostly repeat what cloud assistants already do.
- The devices at hand have sensors, a Wi-Fi radio, a battery, heterogeneous cores and a hard memory limit. Using them turns the project toward embedded systems, wireless communication and control, which is my field.
- The method of Stages 4-6 carries over unchanged: predictions before runs, held-out data for every fitted model, numbers in answers checked against measurements.

**Ideas kept** (useful to a user, not only as experiments):
- Wi-Fi link verdict from the radio values and a 10-second test, with fault location; distance and walls enter through the coverage model
- Channel and network scan, also for choosing the best of several public networks
- Network anomaly detection against a baseline from the background log
- Battery and power agent built on a common telemetry layer; remaining-time prediction (macOS keeps its estimate out of the menu bar)
- Background work on the efficiency cores
- Thermal and power feedback control and a battery-aware policy, as optimisation
- Coverage planning on the floor plan of a home: path-loss fit, router placement and count
- iPhone as a client of the Mac agent; a Bluetooth "smart key" as a stretch goal

**Ideas dropped**: data transfer by sound or light, acoustic ranging, motion recognition, step-based distance, sound classification. They produce data but do not solve a user's problem.

**Models.** The device agents need a small, fast model for routing fallback and answer writing. To be installed at the start of Stage 7 (not during a test run): `ollama pull qwen3:4b` and `ollama pull qwen3:1.7b`. The 14B and vision models stay for documents.

**How the work is done from Stage 7.** Each part starts with a design note: the problem, the components, two or three options with their trade-offs, and the choice with its reason. Code follows the note, with tests, and the note is kept below in this log.

**Schedule.** Stages 7-12 by 2026-11-30, revised the same day to four stages (entry below). Stretch items are dropped first if a stage runs late.

## 2026-11-16 — Stage 6: Run 44 and fixes

Run 44 on the tables set: ✅ 19, ⚠️ 2, ❌ 2 of 23 (83%), "not in the document" 3/3. The gate failed on one case, a growth rate whose operands were in an earlier paragraph than the result; the arithmetic check now looks across paragraphs and in two steps. The page index is no longer given to the vision model. Every model call is now logged with its load, prompt and generation time and the memory held, so Run 45 also measures where the time goes. Details: `evals/documents/tables.md`.

## 2026-11-16 — A slow run diagnosed by hand: GPU held at its lowest clocks

Run 45 ran at about a third of its usual speed: `qwen3:14b` generated 5.5 tokens/s for three hours (21 tokens/s in the first two minutes), and the fans stayed silent. The model call log ruled out two causes: both models were fully on the GPU, and the speed was the same with one or two models loaded.

| Reading | During the slow run | After a full shutdown |
|---|---|---|
| Thermal pressure | Moderate | Nominal |
| GPU active residency | 99.9% | busy |
| GPU frequency | 338-618 MHz (maximum 1,578) | 1,578 MHz |
| GPU power | 2-3 W | 22.4 W |
| `qwen3:14b` generation | 5.5 tokens/s | 25.4 tokens/s |
| Fans | silent | audible |

Power adapter (100 W) and power mode (High Power) were normal, and a CPU load ran at full clocks after the restart. The state did not match real heat: thermal pressure stayed at Moderate while the GPU drew 2-3 W, which points to the thermal management state rather than temperature; a shutdown cleared it. The same three- to five-fold slowdown was seen in Run 39 and probably in Runs 43-44.

Lessons for the device agents: (1) a long run should start with a short speed check, like a power-on self test, and stop with a warning when the machine is far below its measured normal; (2) the performance agent can detect this state from readings alone: GPU busy at its lowest clocks, low power, thermal pressure above Nominal, fans not responding → recommend a restart.

## 2026-11-16 — Stage 6: Run 45 and the check

Run 45 ran all eight document sets (178 questions). One real regression: a slide whose formulas exist only as a picture was read as [none], and the retry asked for charts (GC2, in two sets). A figure page that is not a chart page is now asked again with a prompt that names every kind of content; the check read both formulas. Three one-case drops (D06, TC2, PA10) were run three times each: D06 and TC2 were right 3 of 3 (run-to-run variation), PA10 stayed ⚠️ as in earlier runs. Every gate is met; the tables set went from 48% to 87% over Stage 6. Remaining: one short holdout on unseen financial documents, run once on this code.

Profile of the normal-speed part of Run 45: `qwen3:14b` took 76% of the model time and two thirds of that was reading the prompt; model loading was under 1%. Shorter contexts are the first target for Stage 10.

## 2026-11-16 — Plan revised: four stages, efficiency from the start

**Decision.** Chip-aware optimisation is no longer a stage of its own. Every device agent is built within a time, memory and energy budget from Stage 7 on (budgets in [roadmap.md](roadmap.md)). Wi-Fi diagnosis and coverage planning are one stage, with Bluetooth coverage added. Stages: 7 hardware diagnosis (11-16 to 11-21), 8 wireless (11-22 to 11-26), 9 iPhone client and the battery-time model (11-27 to 11-28), 10 portfolio (11-29 to 11-30).

**Why.** Optimising at the end measures and tunes agents that were designed without limits; embedded systems are designed against their budgets from the start. Only what needs collected data waits: the battery-time model needs days of logged discharge sessions.

**Stage 7 design decisions** (details in [stage7_design.md](stage7_design.md)):

| Question | Choice | Reason |
|---|---|---|
| Format of a reading | Fixed record: name, value, unit, time, quality | Like a register map: one format for every source, SI units, missing values marked instead of failing |
| When to read | Background every 10 s (storage every 10 min), on demand for questions, per-second capture of n seconds for a diagnosis | Baselines need history; diagnosis needs dense data only while it runs |
| Storage | SQLite (standard library), 7 days kept | Queries by time window; constant size like a ring buffer |
| How to read | macOS built-in commands parsed in Python, no new packages | Uses what the platform provides; outputs can be recorded and replayed in tests |
| Administrator rights | `powermetrics` only, allowed without a password for that one command | Chip frequency and power per second are needed for diagnosis; the rule is limited to one read-only command and can be removed with one command |
| Router | Rules first, `qwen3:1.7b` only when the rules do not decide | Most questions are routed in under a millisecond |
| Advice thresholds | Health below 80% or 1,000 cycles → replace (Apple's limits); 80-85% → watch; heavy load (CPU ≥ 70% or GPU ≥ 50% for 2 min) on battery → connect power; on power without High Power Mode → suggest it; charge below 20% → defer; battery at 35 °C or more → heat warning; average power 1.5× the usual → list the biggest users | Published limits where they exist, otherwise values to be checked against the logged baseline |
| Sampler start | By command first; started at login once it is stable | Simple to debug before it runs unattended |
| Bluetooth partner (Stage 8) | Connected earbuds if the Mac reads their signal, otherwise an iPhone test app | Decided by the probe at the start of Stage 8 |

## 2026-11-16 — Stage 7: sensor probe

`scripts/probe_device.py` ran every macOS command the readers will use: 21 of 21 available, `powermetrics` included (sudoers rule for that one command, checked with `visudo -c`). Two findings changed the plan: the battery registry also reports the whole-system input power on the adapter, so total power is measurable on AC without rights; and battery health is reported three ways (90% in macOS, 86.0% raw, 88.4% nominal), so the design now states which one each rule uses. Reviewing the fixtures before the first commit showed that process lists name the applications on the machine, and that the battery's manufacturing data was kept; the probe now replaces process names and removes that data, with tests. Results in `docs/stage7_design.md` §14.

## 2026-11-16 — Stage 7: which source decides the power mode

Two sources disagreed on the power mode while the Mac was on the adapter: `pmset -g` reported `powermode 2` (High Power), while `system_profiler SPPowerDataType` reported Low Power Mode on and High Power Mode off. System Settings shows High Power Mode on the adapter, and `pmset -g custom` gives the setting per power source: adapter `powermode 2` (High Power), battery `powermode 0` (Automatic). Decision: the power mode is read from `pmset -g custom`; the `system_profiler` switches are kept as readings, and a disagreement is reported, not resolved silently. The energy mode is a user setting; the low clocks seen at idle (GPU 338 MHz, 0.11 W) come from dynamic voltage and frequency scaling, which works under every mode. `pmset -g custom` was added to the shell commands and the probe; its recording holds the lines shown above until the next probe run records the full output.

## 2026-11-16 — Stage 7: power and thermal readers; a battery-aware power policy

Readers for the power mode per source, the source in use and the macOS time-remaining estimate (`agent/device/sources/power.py`), and for the thermal pressure level and the recorded CPU limits (`thermal.py`), with tests on the recorded outputs and on outputs for the battery case, older Macs and a recorded cap. "No CPU power status has been recorded" is stored as a 100% speed limit with quality "estimated": it is the absence of a record, not a measurement.

Proposed policy (design §15): on the adapter keep High Power and say so; on battery choose Low Power, Automatic or High Power by job class and charge, restore the previous mode afterwards, and decide the table by measuring each job's energy in each mode. Mode changes will use a sudoers rule limited to `pmset -b powermode 0/1/2`.

## 2026-11-16 — Stage 7: load and memory readers

`load.py`: core counts, load average, the busiest process (`ps`, cheap enough for the sampler), CPU use and the energy ranking (`top`, second sample only; for questions), GPU use and GPU memory from the graphics driver's statistics without rights. `memory.py`: total, free, app, wired, file cache, compressed memory, swap used and the swap counters, and the available percentage from `memory_pressure`. On the recording, free memory is 0.3 GB of 24 GB while 88% is available: macOS fills unused memory with file caches, so a shortage is judged from the available percentage, compression and how fast swap grows, not from free memory.

## 2026-11-16 — Stage 7: the device agent, ready for its first test run

Built to the design in one pass, then tested offline on recorded outputs (314 tests):

| Part | File | Role |
|---|---|---|
| Readers | `agent/device/sources/storage.py`, `chip.py` | SSD space from the APFS container (not `df`), SMART status, throughput, buses; per-second CPU cluster, GPU and Neural Engine frequency, residency and power from `powermetrics`, with each cluster's maximum frequency |
| Store | `store.py` | SQLite, one transaction per round, windows with mean, minimum, maximum and slope, 7-day retention |
| Sampler | `sampler.py`, `scripts/run_sampler.py` | fast sources every 10 s, storage every 10 min, its own CPU time (process and children) stored every round |
| Capture | `capture.py` | n seconds of per-second readings, powermetrics in a parallel thread (one process for all n samples), features per reading |
| Diagnosis | `diagnosis.py` | facts computed and formatted by code; findings with evidence and advice; thresholds of design §7-8; admission decision for "can I run ...?" |
| Router | `router.py` | rules in Korean and English; the small model only for ties, no match, or a keyword inside a general-knowledge question |
| Answer | `answer.py` | `qwen3:4b` writes from the report; numbers checked against it; one rewrite, then a code template |
| Agent | `agent.py`, `main.py` | battery: 2 s capture without chip readings; performance: 10 s capture with chip readings; wired into the main question router after documents and images |

Test set (`evals/device/cases.toml`, `scenarios.py`, `scripts/run_device_set.py`): 28 questions on 18 states built from this Mac's recorded outputs (each state changes only the readings it is about, including the GPU state of 05:04), 4 questions that are not about the device, and 6 questions on the Mac as it is. Predictions are written in the case file before the first run.

Three problems were found while building, before any run: process names and battery manufacturing data in the recorded outputs (removed), a recorded plist made invalid by the identifier removal (blank values now keep their type), and English keywords not matched next to Korean particles ("CPU를": `\b` treats Hangul as a word character). Not built yet in Stage 7: switching the energy mode on battery, the 20-second speed check before long runs and the feedback controller; they follow the first test run.

## 2026-11-16 — Stage 7: Run D1, the first run of the device set

Routing 36 of 38, findings 27 of 28 (every routed case right, including the GPU state of 05:04), but the answers failed: the `qwen3:4b` tag in Ollama is the 2507 thinking model, which ignored `think = false`, wrote its reasoning as the answer in English and ran to 1,400-2,600 tokens (25-47 s). The number check rejected 24 of 35 answers and the code template answered instead, so no wrong number reached an answer, but the model's output was unusable as an answer every time. Fixes: `qwen3:4b-instruct` as the answer model, a cap on the answer length, rejection of reasoning written as an answer, a keyword fix ("성능" inside "고성능") and general-knowledge questions decided by rule. Details and the gate for Run D2: `evals/device/results.md`.

Lesson: a model tag is not a fixed thing. The same name pointed to a different model than the one tested in Stages 0-6 (the hybrid `qwen3:8b` and `qwen3:14b` honour `think = false`); the model's identity is now checked by its digest.

## 2026-11-16 — Stage 7: Run D2, the device set passes its gate

With the instruct model: routing 38 of 38, findings 28 of 28, 34 of 34 answers written by the model, battery answers in 4.4 s and performance answers in 13.3 s (68 s and 81 s in Run D1). Hand grading: ✅ 21, ⚠️ 13, ❌ 0; the ⚠️ answers mix up the meaning of a number (available and used memory) or add a cause that is not in the findings. The adapter was unplugged on purpose during the live cases: macOS still reported "AC attached" while 0 W came in and the battery delivered about 75 W. The diagnosis trusted the power reading over the status flag and reported the discharge, but advised a stronger adapter; it now recognises an adapter that supplies nothing. Lesson: two readings of one state can update at different rates, so a diagnosis should rest on the physical measurement (power) rather than on a status flag. Details: `evals/device/results.md`.

## 2026-11-16 — Stage 7: Run D3, the fixes hold and a false alarm appears

Committed as `dec29c9`, then run with the adapter connected: routing 39 of 39, findings 29 of 29, 35 of 35 answers by the model, the same speed as Run D2. The Run D2 fixes held (time to full while charging, English answers, the adapter that supplies nothing). Graded more strictly than Run D2 (a wrong Korean term counts): ✅ 13, ⚠️ 19, ❌ 3. Two ❌ are a diagnosis error, not the model's: with 72 W coming from a 100 W adapter and 3 W from the battery, the rule called the adapter too weak, because it fired on any discharge on the adapter. It now compares the input with the adapter's rating first. The third ❌ is a broken fragment ("2. tqdm.") that the number check let through; Latin words that are in neither the facts nor the question are now checked like numbers. The prompt rules added after Run D2 did not stop the meaning mix-ups, so the Korean terms are now given with each Korean question. Lesson: a threshold needs a reference (a discharge means nothing without the adapter's rating), and a rule written in a prompt is weaker than a check written in code. Details and the gate for Run D4: `evals/device/results.md`.

## 2026-11-16 — Stage 7: Run D4, the charge limit tested

Run with the 90% charge limit turned off. Routing 40 of 40, findings 30 of 30, 36 of 36 answers by the model, no ❌ (✅ 18, ⚠️ 18). The Korean term list cut wrong terms from 5 to 1 and mixed meanings from 9 to 3, but primed the model: given the energy modes on every question, it named High Power Mode where the facts said Automatic and gave mode advice that was not in the findings. Only the terms that appear in the report are given now. The live battery cases doubled as a test of the charge limit: without it, at a similar load, the adapter supplied 85 W instead of 72 W and the battery charged instead of giving 3 W, so the limit, not the adapter, explains the discharge in Run D3. Lesson: an instruction in a prompt is also an input, so it can add errors as well as remove them; give the model only what the case needs.

## 2026-11-16 — Stage 7: Run D5, the answer writer is left here

Charge limit back on (set in System Settings > Battery). Routing 40 of 40, findings 30 of 30, hand grade ✅ 26, ⚠️ 10, ❌ 0 (Run D4: ✅ 18, ⚠️ 18). Giving only the terms in the report removed the wrong modes and terms. The battery again gave 3.4 W on the adapter with the limit on (78.4 W in), the third reading that fits the charge limit as the cause. Two last fixes: "memory used by apps" is no longer given next to "memory available", because the two are counted differently and look contradictory even to a person; and the template says in Korean why it answers in English. The remaining guesses about the fans need a fan reading, not another prompt rule. Five runs in one evening: Run D1 had no usable answer; Run D5 has no wrong one.

## 2026-11-16 — Stage 7: where the charge hold can be read

The 90% limit is set in System Settings > Battery. Its value is not in `pmset -g` and there is no `com.apple.smartcharging` domain, but the charger reports why it is not charging: `ChargerData > NotChargingReason` in the battery registry, a bit field like a status register. It read 0x1000000 (bit 24) in the recorded fixture and again in a live check, both times on the adapter at 90% with charging held, and `ChargerInhibitReason` read 0. The diagnosis now reads that bit: when it is set and the battery gives a little power, it says that macOS holds the charge (a charge limit or optimised charging) instead of pointing at the cable. Bit 24 is identified from two readings in one state; the sampler stores the code, so the readings with the limit off and at 100% will show whether other states set it too.

