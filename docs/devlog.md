# Development log

Author: PARK, SEHO

Dated entries: what was built, what was decided and why, and progress against the schedule in [roadmap.md](roadmap.md). Detailed results are in [benchmarks.md](benchmarks.md) and [findings.md](findings.md).

## Progress against the schedule

| Stage | Planned | Started | Finished | State |
|---|---|---|---|---|
| 6 close | 11-16 | 11-15 | | Regression passed (Run 45 and check); holdout pending |
| 7 Device layer and battery agent | 11-17 to 11-19 | | | |
| 8 Wi-Fi and network agent | 11-20 to 11-22 | | | |
| 9 Coverage planning | 11-23 to 11-25 | | | |
| 10 Chip-aware optimisation | 11-26 to 11-27 | | | |
| 11 iPhone client | 11-28 to 11-29 | | | |
| 12 Portfolio | 11-30 | | | |

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

**Schedule.** Stages 7-12 by 2026-11-30 (table above). Stretch items are dropped first if a stage runs late.

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
