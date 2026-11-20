# Development log

Author: PARK, SEHO

Dated entries: what was built, what was decided and why, and progress against the schedule in [roadmap.md](roadmap.md). Detailed results are in [benchmarks.md](benchmarks.md) and [findings.md](findings.md).

## Progress against the schedule

| Stage | Planned | Started | Finished | State |
|---|---|---|---|---|
| 6 close | 11-16 | 11-15 | | Regression passed (Run 45 and check); holdout pending |
| 7 Hardware diagnosis, chip-aware from the start | 11-16 to 11-21 | 11-16 | 11-17 | Done: readers, store, sampler, diagnosis, agents (Run D6: no wrong answer), energy-mode policy, speed check, workload set W, power controller (C2). Deferred: battery tiers 3-5, sampler cost, SMC sensors |
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

## 2026-11-16 — Stage 7: energy mode switching on battery

A sudoers rule (`/etc/sudoers.d/powermode`, checked with `visudo -c` before it was installed) lets exactly `pmset -b powermode 0`, `1` and `2` run without a password. The negative test of the rule first passed for the wrong reason: sudo had cached the password typed a moment before, so the command that should have been refused (`pmset -b sleep 0`) ran and turned off sleep on battery. It was set back to 1 (the value in use before), and the test repeated after `sudo -k` was refused as it should be. Lesson: a test that something is blocked must first close the other ways through.

`agent/device/power_policy.py`: the policy table of design §15 in code (job class and charge to mode), a context manager that saves the battery mode, switches, runs the job and restores the mode even when the job fails, but keeps a change the user made during the job, and an energy meter that measures the job's energy two ways (V × I integrated, and the drop in the charge left). Only the three allowed commands are ever run with sudo, and tests check it against a fake Mac that keeps a mode. `scripts/measure_job_energy.py` runs the same generation in each mode on battery to decide the table.

## 2026-11-16 — Stage 7: energy run E1, and a measurement that failed its own check

qwen3:14b on battery, the same 800-token generation in each mode: 14.1 tokens/s in Low Power, 25.3 in Automatic and 25.3 in High Power. Generating a token reads every weight once, so the speed is set by memory bandwidth (about 9 GB × 25.3/s ≈ 230 GB/s of the M4 Pro's 273 GB/s), and High Power cannot make it faster. The policy now gives heavy generation Automatic instead of High Power. The energy figures were not usable: the V × I integral and the drop of the charge left disagreed by up to ten times, because the battery registry refreshes only every few seconds and the runs were 30-60 s. `scripts/gauge_rate.py` measures the refresh interval of each value, including the power controller's accumulators, before the next run. The sampler now keeps 21 days of readings (was 7), so today's battery sessions last until the battery-time model of Stage 9.

## 2026-11-16 — Stage 7: the battery registry publishes once a minute

`scripts/gauge_rate.py` read the battery registry every second for a minute: every value changed exactly once, and its update time moved by 60 s. That explains the failed energy run E1 and the identical battery values of Run D3. The power controller keeps a running sum of the system load sampled every second (59 samples in the minute) and publishes it with the rest, and on battery the published load equalled the battery's V × I. Energy is now the difference of that sum between the publication before a job and the one after it, minus the idle power outside the job, with a check that the sample count matches the window. The sampler reads the battery once a minute instead of every 10 s. Lesson: find the source's own update rate before choosing a sampling rate or a measurement method.

## 2026-11-16 — Stage 7: energy run E2, High Power gives no speed on battery

Generation and a 7,684-token prompt with qwen3:14b in each mode. Speed: Automatic and High Power identical in both jobs (25.4 tokens/s written, 213 read); Low Power 35-45% slower. The prediction that High Power would speed up the compute-bound prompt reading was wrong: High Power Mode mainly lets the fans sustain heavy work, which matters only once heat limits the chip, not in a 40-second job. Energy: the counter gave 4.1 W for a 14B generation, below the idle power, while its sample check passed; a lag in its publications would explain every result. A plausibility check (the job above idle) now flags such windows, and a step-response test (`scripts/gauge_step.py`) will measure the lag against powermetrics. Lesson: a check that only tests the shape of the data (sample counts) cannot catch data that is well-formed and wrong; it needs a physical expectation.

## 2026-11-16 — Stage 7: step test of the energy counter on the adapter

One minute of 14B generation between idle periods, with powermetrics as a reference. On the adapter the counter followed the load within the same minute and fell back right after: no lag. It also showed that the system drew about 66-80 W during generation while the chip drew 25-32 W, so memory, display and the rest take more than half the power of a bandwidth-bound job, and chip power alone would understate its energy by half. The E2 failures therefore point to the battery side, where the load comes from the gauge's averaged current. The meter now integrates until the counter settles back to idle instead of stopping at the first publication; the step test on battery will confirm the cause.

## 2026-11-17 — Stage 7: on battery, the coulomb counter

The step test on battery answered the open question: the system counter barely moved during a 14B generation (6.4 W against 4.9 W idle, while the chip alone drew 17 W), and the energy did not arrive later either. On battery that counter does not measure a job's load. The battery gauge's coulomb counter (the charge left, in mAh) does: E1's charge-drop figure for High Power, about 69 W, matches the 66-80 W measured on the adapter. The meter now picks its source by power state (system counter on the adapter, charge drop on battery), each read at the registry's publications and integrated until the reading settles back to idle. Three measurement designs in one evening, each replaced because an experiment showed where it failed.

## 2026-11-17 — Stage 7: energy run E3, and the speed check before long runs

E3 used the charge drop on battery. Speed matched E1 and E2 within 1% again, but the energy did not hold: the idle minute before the Low Power run read −4.5 W (the charge left went up), and High Power gave 0.892 Wh where E1 gave 0.608 Wh for the same job. The gauge's charge figure is an estimate it corrects from the cell voltage, and for a job of about 0.5 Wh those corrections are as large as the job. An idle reading that is not physical is now flagged. The modes will be compared either on the adapter, where the system counter is precise, or with longer repeated runs on battery.

Speed check (`agent/device/speed_check.py`, `scripts/speed_check.py`): before a test-set run, a 100-token generation with qwen3:14b is compared with this Mac's normal speed for the current energy mode (25.3 tokens/s in Automatic and High Power, 14.1 in Low Power, from E1-E3). Under 60% of normal, the performance diagnosis runs and the run stops unless `--force` is given; under 80%, a warning. Motivation: Run 45 lost hours to a GPU held at its lowest clocks, found only afterwards. The measured speed is stable because generation is bound by memory bandwidth, which is what makes it a usable health signal.

## 2026-11-17 — Stage 7: on the adapter or on battery, different questions

Decision (user's proposal): on the adapter, battery time and the energy mode do not matter; what matters is the battery's health and lifespan, heat, and whether the adapter supplies what it should. On battery: time left, consumption, efficiency, stability and heat. The data agreed: in E1-E3 High Power never changed the speed, and the gauge cannot resolve the energy of a single job, so the mode comparison stops here. The battery report now gives the answer writer only the facts that matter for the current source; the energy-mode remarks that caused most ⚠️ in Runs D4-D5 had come from facts the writer did not need. Run D6 checks it.

## 2026-11-17 — Stage 7: Run D6, and the agent's own models in its memory diagnosis

With the battery report split by power source: ✅ 29, ⚠️ 7, ❌ 0, and no energy-mode remarks left on the adapter. The live cases found real memory pressure (16% available, heavy swapping), and the cause was the agent's own models, loaded by the speed check and the answers: a diagnosis that cannot see them blames other apps, and the admission check asked for 10 GB for a 14B question with the 14B already in memory. The device layer now reads the models Ollama holds (`/api/ps`), names them in a memory shortage, and the admission check reuses a loaded model instead of counting it twice. A question about battery time on the adapter now gets the time it would last unplugged, at the usual power on battery from the logged sessions. Lesson: a monitor running on the system it monitors is part of what it measures.

## 2026-11-17 — Stage 7: workload set W

Question raised by the user: the High Power result holds for LLM generation, but games, video, compiling and 3D work load other parts of the chip. Real applications cannot be repeated identically, so each kind of work is reproduced by a synthetic load with the same hardware demand (`agent/device/workloads.py`): 15 profiles in six tiers, from idle and document editing to 4K export, a 60 fps game loop, 3D rendering and real MLX training. Each tier runs on the adapter in High Power (the reference) and on battery in the modes that matter (`scripts/run_workloads.py`), split into sessions of 10-30 minutes. Calibration against the real applications was dropped for lack of time before the exams, and is stated as a limit. Predictions in `evals/device/workloads.md`.

Revised the same morning, before any run (the user's review): the first version held each load constant (compiling and rendering at 100% for the whole run), heavier than real use and not how work rises and falls. The scenarios now have phases (a video edit scrubs, previews effects, then exports; training prepares data, then runs epochs with evaluations and checkpoint saves), with a seeded random drift so every mode gets the same pattern. And every phase is a fixed amount of work rather than a fixed time: a fixed busy time would let a slow mode look as busy as a fast one, while fixed work shows a slow mode as a longer batch or as missed deadlines. The amounts are calibrated once on the adapter in High Power. Predicted loads per scenario are in `evals/device/workloads.md`.

## 2026-11-17 — Stage 7: workload set W on the adapter

All six tiers on the adapter in High Power (about an hour, unattended). Light work (documents, music, web, 4K playback) drew 7-8 W for the whole Mac, the same as idle: the chip added under 1.2 W, and 4K decoding on the media engine nothing measurable, so for light work battery life is set by the screen and base load, not by the energy mode. Everyday heavy work came in bursts (photo editing peaked at 43 W, averaged 7 W). Sustained GPU work held 20-25 W with thermal pressure nominal for 95 s. The stress scenario (every core and the GPU) reached heavy thermal pressure and needed 658 s for 180 s of full-speed work: the chip settled near 32 W and the GPU ran at half clock, a heat cap at about a third of burst speed. That curve is the plant the feedback controller will regulate; every run now records it every 5 s. Details: `evals/device/workloads.md`.

## 2026-11-17 — Stage 7: the chip's power curve under full load

Stress resized to 60 s of full-speed work per part: the chip started at 94 W and decayed toward 34 W with a time constant of about 12 s, clocks falling with it, while macOS still reported nominal thermal pressure. The GPU kept 81% of its clock and finished almost on time; the performance cores fell to half and took 1.8 times as long, then sped up again once the GPU was done. So the plant has two stages, a fast power budget (seconds) and slow heat (minutes, the 11-minute run reached heavy thermal pressure), and the thermal pressure level only reflects the slow one. The feedback controller will therefore watch chip power and clocks, not the pressure level. Each sample now carries its own time stamp.

## 2026-11-17 — Stage 7: workloads on battery (tiers 0-2), and the power controller

On battery, Low Power against Automatic for light work: Low Power saved 0.1-1.5 W of chip power (most for a video call, about 15% of the whole Mac's 10 W; a few percent for documents and web) and missed one page load out of 180. The charge-drop figure was useless for light work (1.8 to 18 W for the same task); chip power from powermetrics and V × I at the publications carried the comparison. On battery, Low Power is a fair default for light work.

Power controller (`agent/device/controller.py`): a PI loop that holds chip power at a target during long jobs by pacing the work (short chunks with rests, like the off time of PWM). Sensor: powermetrics every second, smoothed. Tuning from the measured plant: power follows the load within a second, so the loop is mostly integral, Ki = 1 / (K × 6 s) with K the job's full power minus idle, plus a small proportional part. Tested first on a simulated plant that includes the measured 12 s budget decay: settling in 5-11 s, steady error under 0.1 W. The simulation found two defects before any hardware run: the first tuning gave a 17-22 s response instead of the intended 6 s (wrong formula for the integral gain), and the first anti-windup stopped the duty at 0.95 when the target was out of reach. The recorded hardware test holds real MLX training at 65% and then 40% of its full power (`scripts/run_controller_test.py`).

## 2026-11-17 — Stage 7: controller test C1 on the chip

Real MLX training held at 65% and 40% of its full 28.6 W: mean power within 0.2 W of both targets, training speed in proportion (66% and 43% of the steps), and the same energy per step in every phase (2.6-2.7 J), since pacing trades speed for power and does not lower clocks. The trace showed two loop defects: each step started from the old duty, so the 18.6 W phase first fell to 12 W (fixed with feedforward of the duty the target needs, the integral now only corrects the nonlinearity), and the loop updated more often than the sensor delivered samples, doubling the integral gain (fixed: update on new samples only). The 60 s settling time reported for 11.5 W was noise crossing a narrow band, so the report now also gives the first entry into the band and the share of time inside it. Details: `evals/device/controller.md`.

## 2026-11-17 — Stage 7: controller test C2, the criterion met

With feedforward and updates on new samples only, real MLX training reached the target band in 2.9 s (18.7 W) and 4.7 s (11.5 W), against about 16 and 9 s in C1, and held the mean within 0.1 W of both targets. The remaining 1-2 W of ripple comes from pacing in 0.1 s chunks sampled once a second; it keeps the share of time inside a ±10% band at 85%, which matters less than the mean for a power budget held over minutes. Stage 7's last criterion, the controller holding its target in a recorded test, is met. Deferred: battery runs of workload tiers 3-5, the sampler cost experiment, fan and temperature sensors from the SMC.

## 2026-11-17 — An answer about something never measured

Asked in use "are the data transfer speeds between RAM, SSD, CPU and GPU all normal?", the performance agent answered that they were, although nothing had measured them: the diagnosis found no problem in what it did measure, and the writer restated the question's subject as checked. Two fixes. A question about something the agent does not measure (transfer speeds when not run, fan speed, the chip's temperature) now gets a finding that says so, and the writer reports it as unmeasured. And transfer speeds are now measured when asked (`agent/device/bench.py`, about 5 s): memory bandwidth as the GPU sees it, one CPU core's copy speed, and SSD write and read past the file cache, compared with this Mac's normal (the first run on the adapter is stored). On Apple silicon the CPU and GPU share one memory, so there is no CPU-to-GPU transfer to measure apart from the memory bandwidth itself; the answer says this. Lesson: "no problem found" is only as wide as what was measured, and the answer must not be wider.

Same day: memory by app, and the limits made explicit. A memory question (or a memory shortage) now lists the apps holding the most memory, with each app's helper processes grouped under it (a browser's renderer and GPU helpers count as the browser), from the resident set that `ps` already reports; shared memory is counted in each process, so the sums run high, which the answer says. Fan speed and the CPU and GPU temperatures have no public interface on this Mac and are answered as not measured; screen brightness, the light sensor and the keyboard light are left to the user's settings on purpose, and a question about them gets that answer instead of a judgement. Such questions now route to the performance agent, so the general model never gets the chance to guess.

Same day: a question guide and ports. `docs/device_questions.md` lists the questions the device agent answers, by component, with what each answer is based on and what is not measured; `tests/test_device_questions.py` routes every example and fails if one reaches another agent than the guide says, so the guide stays true. Writing it showed that the bus readings were collected but never used in an answer: a question about ports now lists the three USB-C ports (Thunderbolt 5 / USB4, up to 120 Gb/s each) and what is connected to them, USB devices, and the internal SSD's model and health.

Same day, from the user's review of the guide: "can I run a document question?" is the agent's view, not the user's. A user asks "what can I do now?", "can I edit 4K video?", "can I play a demanding game?". The performance agent now answers these from the loads measured with the workload set (memory, mean system power, peak chip power for nine kinds of work) against the present state: a problem such as a held GPU rules out heavy work, memory available against what the work needs, and on battery the time the battery would last at that work's power. "How long can I game on battery?" goes to the performance agent although it names the battery. The guide was rewritten to say first, for each part of the system, what the agent can read, how often and how it judges it, and only then to give example questions.


## 2026-11-18 — Stage 8: network agent, coverage walk 1

- Network agent: "why is my Wi-Fi slow?" answered hop by hop (radio link, Wi-Fi segment, internet, DNS) from
  10 s of measurement, 30 s for calls and games; AWDL named as the cause of latency spikes on the evidence of W2;
  verdicts per use from measured latency, loss and speed. Router: a network word decides against performance.
- Coverage tools: walls extracted from the floor plan, multi-wall path-loss model, walk and report scripts. The
  floor plan was redrawn by hand in English without the listing's watermark, in two versions at the same pixel
  coordinates: a measurement map (points, routers, door tests) and a plain base for the contour maps, from which
  the walls are also taken.
- Walk 1 (router on the floor, 5 GHz link, 25 points): link adaptation measured from MCS 9 to MCS 1; latency held
  until SNR 7; per-direction rate adaptation seen. The multi-wall model failed its gate (held-out RMSE 13.8 dB);
  the walls differ too much for one loss per wall. Beacons and Bluetooth were not usable and were fixed (named
  scans, BLE). The home turned out to have three routers.

## 2026-11-19 — Stage 8: walk 2, review, SINR and the choice of network

- Walk 2 (25 points, named scans of all six home networks, BLE from an iPhone next to the router): repeat points
  differ by 3.0 dB RMS from walk 1; two routers share both channels; the places where the Wi-Fi drops in daily use
  are in a third router's area. Coverage maps for each router and band, interpolated (IDW) because the wall model
  had failed; drawings of the floor plan and maps finalised by hand.
- Review of the method with a professor of wireless communications. RSSI in the 802.11 standard is a relative,
  vendor-defined index; macOS reports it in dBm through the chip's driver, uncalibrated, so absolute values are
  read as approximate and only comparisons on one source are used. Walls: the measured values are the basis,
  since the walls' materials cannot be known from a MacBook. The routers are linked by cable, so the Mac-to-router
  link is the only wireless hop.
- SINR added beside SNR. Counting the co-channel router as noise gave about 0 dB in the living area where the Mac
  used MCS 6-9: the routers hear each other and take turns. Rule adopted from 802.11's CCA level: co-channel
  networks above -82 dBm share airtime, weaker ones add to the noise.
- "Which Wi-Fi should I use here?": ranked from one scan (SINR, rate expected from the measured table), a short
  join-and-measure test when the difference is within the 5 dB spread (`scripts/wifi_trial.py`). Replayed on walk 2:
  all points with latency spikes advised to switch, none advised to stay had them. Next: trial W4 on the Mac.
- Through the walls or around them: routing AP-A's signal along the shortest way through open space and doors,
  with about 10-12 dB per right-angle bend, predicts the held-out points to 3-4 dB, against 12-14 dB for one loss
  per wall on the straight line. The bathroom below the router's room is 3.7 m away through concrete but 6.4 m and
  two bends around it, which is why it gets almost nothing. Not true of the other two routers, whose walls are
  lighter. Found after the walks, so the next walk is the real test.

## 2026-11-20 — Stage 8: what the connection can carry, starting with games

- The per-use verdicts borrowed a voice guideline and "common guidance". Plan: requirements published by the
  application makers (Teams for calls, Netflix for 4K), latency under load, upload, and a check against real
  sessions of each application before any verdict is called reliable.
- Games first, from the player's own experience: LoL ping 10-15 ms with moments at 40-50 ms that cost fights. The
  old rule (replies above 50 ms, median against 40 ms) saw none of it. New rule: rises of 20 ms over the usual
  ping, 10 pings a second in the agent; `game_watch.py` runs during a game at 20 a second, places each spike on the
  Wi-Fi link or beyond the router and records the AWDL state. LoL, Valorant and PUBG questions now route to the
  network agent. Experiment G1 planned: four games, AWDL alternated.
- The connection card: one fixed-format answer per place that joins both layers. The radio chain (signal, SNR and
  SINR, modulation, link rate) explains and predicts; what the applications feel (spikes, loss, download, upload)
  decides each verdict. Calls judged by Teams' published requirements, 4K by Netflix's, downloads as a time for
  10 GB. The bottleneck is placed on the Wi-Fi link or beyond the router, and the other networks heard here are
  listed with their expected modulation. `wifi_here.py` joins the strong ones and compares measured values.
- Continuity features and games (C1, two runs): AirDrop set to Everyone delayed 26% of the pings to the router
  for 3 minutes; Contacts Only, Handoff, iPhone widgets and AirPlay Receiver showed no effect. Day to day the
  features stay on; a game question gets "AirDrop to Contacts Only, leave the rest". The count of spikes missed a
  steady pattern of delays, so the share of late pings was added.
- The card now speaks everyday words by default (signal "good", "jumps 1 in 4 times", "may stutter", why, what to
  do); "in detail" keeps the radio chain and the evidence for review.
