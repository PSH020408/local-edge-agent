# Stage 7 device test set: results

Questions in `cases.toml`, device states in `scenarios.py`, runner `scripts/run_device_set.py`.
Reports are written to `logs/device_runs/` (not committed: the live cases list the processes running on the Mac).

Automatic checks per case: route, expected and forbidden findings, expected strings in the answer, numbers
in the answer that are not in the facts, and who wrote the answer (the model, the model after one rewrite,
or the code template). Answers are also read and graded by hand.

## Run D1 — first run (2026-11-16)

Code: the Stage 7 device agent as built on 2026-11-16 (uncommitted on 9016576). Answer model `qwen3:4b`,
router model `qwen3:1.7b`. 38 cases in about 21 minutes.

| Check | Result |
|---|---|
| Route right | 36 of 38 |
| Findings as expected | 27 of 28 (the miss is B12, routed to the wrong agent) |
| Answers by the model | 11 of 35; 24 replaced by the code template |
| Answers with a number not in the facts at first | 24 of 35 |
| Time per battery question (live) | median 68 s (budget 3-5 s) |
| Time per performance question (live) | median 81 s (budget 15 s) |

**The diagnosis worked; the answer writer did not.** Every case routed to its agent got the expected
findings, including the GPU state of 2026-11-16 (P02, P03, P12). But:

1. **Wrong answer model.** The `qwen3:4b` tag in Ollama is the 2507 thinking model (same digest as
   `qwen3:4b-thinking-2507-q4_K_M`). It ignores `think = false` and wrote its reasoning as the answer
   ("Okay, let me tackle this..."), in English, 1,400-2,600 tokens per call (25-47 s at 60 tokens/s), often
   ending in a loop of repeated digits ("6, 6, 6, ..."). The number check rejected 24 answers, and the code
   template answered instead, so no wrong number reached the answer; the 11 answers accepted from the model
   passed the number check but were reasoning text, not answers. As answers to a user, the model's output
   was unusable in every case.
2. **B12, a keyword inside a word.** "고성능 모드" (High Power Mode) also matched the performance keyword
   "성능", the tie went to the small model, which chose performance.
3. **R04, the small model on a general question.** "Explain the chemistry of lithium-ion batteries" was
   sent to the battery agent by `qwen3:1.7b`.

Predictions written before the run: routing all right except possibly one model case (two misses, one of
them a rule bug); findings all right (yes, for every routed case); "a few rewritten, 1-3 templates" (no:
24 templates, because of the wrong model); battery under 5 s (no: 68 s).

### Fixes after Run D1

| Problem | Fix | Kind |
|---|---|---|
| Thinking model as the answer model | `qwen3:4b-instruct` (the 2507 instruct model) in `config.toml`; the tag and its digest are checked in the comment | Config |
| Reasoning written as the answer | An answer that starts like reasoning ("Okay", "let me ...", "the user is asking") or holds a `<think>` block is rejected and rewritten once, then the template | Code |
| Long, looping answers | `num_predict` 400 for the writer, 30 for the router | Config |
| "성능" inside "고성능" | The performance keyword no longer matches after "고" or "저" | Code |
| General questions decided by the small model | A general-knowledge question that does not point at this machine is not a device question, by rule | Code |
| Rejected answers not visible in the report | The model's first answer and the reason it was rejected are kept in the run report | Code |

Gate for Run D2, written before it: route right 38 of 38 (B15 and R02 by the model); findings 28 of 28;
answers by the model or after one rewrite at least 30 of 35, none with a number not in the facts; battery
questions under 5 s and performance questions under 15 s (median of the live cases).

Predictions: the instruct model answers in Korean and copies the numbers in most cases; a few answers need
one rewrite; the template is needed at most twice; battery answers take 2-4 s (about 150 tokens at
60 tokens/s), performance answers 10 s of capture plus 2-4 s.

## Run D2 — after the Run D1 fixes (2026-11-16)

Answer model `qwen3:4b-instruct`, router `qwen3:1.7b`. 38 cases in about 3 minutes (21 minutes in Run D1).

| Check | Run D1 | Run D2 |
|---|---|---|
| Route right | 36 of 38 | **38 of 38** |
| Findings as expected | 27 of 28 | **28 of 28** |
| Answers by the model (first or second try) | 11 of 35, all unusable | **34 of 34** (one rewritten) |
| Answers with a number not in the facts at first | 24 | **1** (caught and rewritten) |
| Live battery questions | 68 s | **4.4 s** (median) |
| Live performance questions | 81 s | **13.3 s** (median, 10 s of it the capture) |

Gate: route 38 of 38 (met), findings 28 of 28 (met), at least 30 model answers with no unsupported number
(met: 34), battery under 5 s and performance under 15 s (met). **Gate passed.**

Hand grading of the 34 answers against the facts: **✅ 21, ⚠️ 13, ❌ 0.**

| ⚠️ | Why |
|---|---|
| B04 | Raw capacity 82.4% and the macOS figure 83% mixed in one sentence |
| B08 | Calls 38.5 °C "normal" although the finding is a heat warning; the advice is right |
| B10 | Read the macOS "0:58 remaining" as time of use; while charging it is the time to full. A labelling error in the diagnosis, not the model's |
| B11 | Advice right, explanation of the cause garbled |
| B13 | Advice right, adds a cause that is not in the findings |
| B14, P13 | English questions answered in Korean |
| P03 | Says thermal management stops the fans: a cause that is not measured |
| P08, P10, L04 | Free storage called used, available memory called used |
| L01, L02 | See below: the state was right, the advice (a stronger adapter) did not fit; L02 gives no time left |

**An unplugged adapter caught live.** The adapter was unplugged on purpose during the live cases, without
telling the agent. In L01 and L02 macOS still reported the adapter as connected ("AC attached") while the
input power was already 0 W and the battery delivered 6.3 A at 11.8 V (about 75 W; macOS: 46 minutes to
empty). The diagnosis went by the power reading, not the status flag, and reported that the battery was
discharging; its advice (a stronger adapter) did not fit, because the adapter supplied nothing.

Predictions: Korean answers that copy the numbers (yes); a few rewrites (one); the template at most twice
(none); battery 2-4 s (4.4 s live, 2.5-3.7 s on scenarios); performance about 13 s (yes).

### Fixes after Run D2

| Problem | Fix | Kind |
|---|---|---|
| macOS "remaining" while charging read as time left (B10) | Read as the time to full when the state is "charging" | Code |
| Adapter reported as connected but supplying nothing (L01, L02) | New finding when the input power is 0 W while the battery discharges: a just-unplugged adapter that macOS has not caught up with, or a loose or faulty one; the time left is computed in this state too. A scenario of this state and case B16 added | Code |
| English questions answered in Korean | The language is stated by code in the request ("Answer in English.") | Code |
| Meanings mixed (available and used, raw and macOS capacity) and added causes | Writer rules: keep each fact's meaning; give only the causes in the findings | Prompt |

## Run D3 — after the Run D2 fixes (2026-11-16)

Commit `dec29c9`. Same models. 39 cases (B16 added), adapter connected for the live cases. The gate of Run D2
was used again (no new gate was written before this run).

| Check | Run D2 | Run D3 |
|---|---|---|
| Route right | 38 of 38 | **39 of 39** |
| Findings as expected | 28 of 28 | **29 of 29** |
| Answers by the model (first or second try) | 34 of 34 | **35 of 35** (two rewritten) |
| Answers with a number not in the facts at first | 1 | 2 (both caught and rewritten) |
| Live battery questions | 4.4 s | 4.6 s (median) |
| Live performance questions | 13.3 s | 13.6 s (median) |

**Gate passed.** The Run D2 fixes held: B10 now gives the time to full (macOS 58 min, own estimate 44 min),
B14 and P13 are answered in English, B16 (adapter supplying nothing) is diagnosed and explained correctly.

Hand grading of the 35 answers, stricter than in Run D2 (a wrong Korean term now counts as ⚠️):
**✅ 13, ⚠️ 19, ❌ 3.**

| Kind | Cases | Example |
|---|---|---|
| ❌ Wrong diagnosis | L01, L02 | See below |
| ❌ Broken text | L05 | The rewritten answer holds "압축된 메모리는 2. tqdm."; the number check let "2." pass as a counting word |
| ⚠️ Meanings mixed | B01, B04, B09, P01, P04, P10, P11, L03, L04 | "12.2GB 중 88%가 사용 가능" (P01); available memory called used (L03, L04, again) |
| ⚠️ Wrong term | B02, B03, B12, P02, P12 | High Power Mode as "고용량 모드", vents as "밸브", fans as "펌프" |
| ⚠️ Added cause or advice | B11, B13, P05 | "turn High Power Mode off" (B11), not in the findings |
| ⚠️ Contradicts a finding | B08 | Calls 38.5 °C "not hot" although the finding is a heat warning (again) |
| ⚠️ Unmeasured claim | P03 | "the fans are confirmed not to work" (again); fan speed is not read |

The prompt rules added after Run D2 ("keep each fact's meaning", "give only the causes in the findings")
did not stop the mix-ups: the same three cases (P03, B08, available memory) went wrong again.

**A false alarm on the adapter (L01, L02).** With the adapter connected, the Mac drew 72.0 W from it (of
100 W) and 3.0 W from the battery (−0.24 A). The diagnosis called this a weak adapter ("use an adapter with
more power") and gave 19 h 44 min as time left. Neither fits: the adapter had 28 W to spare, and 3 W is
small. The rule fired on any discharge on the adapter. Both cases show the same battery values to 0.1, so
the battery readings had not refreshed between them (the gauge updates less often than once per question).

### Fixes after Run D3

| Problem | Fix | Kind |
|---|---|---|
| Any discharge on the adapter called a weak adapter (L01, L02) | Weak adapter only when it supplies at least 85% of its rating. Under 5 W from the battery with the adapter below its limit is information (`battery_assist`), with no time left. More than that below the rating: a cable or port to check (`adapter_short`). Scenario `adapter_headroom` and case B17 added | Code |
| Broken fragments in an answer (L05) | A Korean answer whose Latin words are in neither the facts nor the question is rewritten once, like a wrong number | Code |
| Wrong Korean terms, available called used | The Korean terms are given with every Korean question (High Power Mode = 고성능 모드, memory available = 사용 가능한 메모리, ...) | Prompt |
| "Not hot" at 38.5 °C (B08) | The finding states its threshold: "warmer than it should be (above 35 °C)" | Code |
| "Fans confirmed not to work" (P03) | The GPU finding says that fan speed is not measured | Code |

Gate for Run D4, written before it: route 40 of 40, findings 30 of 30, at least 33 of 36 answers by the model
with no unsupported number or stray word, live times as before; by hand: no ❌, and fewer ⚠️ for meanings
mixed and wrong terms (9 and 5 in Run D3). Predictions: the terms fix most of the wrong-term cases; the
meaning mix-ups drop but do not disappear, since a 4B model still writes "X 중 Y%" across two facts.

## Run D4 — after the Run D3 fixes, with the charge limit off (2026-11-16)

Commit `166b505`. Same models, 40 cases (B17 added). The 90% charge limit was turned off for this run, so the
live battery cases also test whether the limit explains L01-L02 of Run D3 (below).

| Check | Run D3 | Run D4 |
|---|---|---|
| Route right | 39 of 39 | **40 of 40** |
| Findings as expected | 29 of 29 | **30 of 30** |
| Answers by the model, no unsupported number or stray word | 35 of 35 | **36 of 36** (one rewritten) |
| Live battery questions | 4.6 s | 4.9 s (median) |
| Live performance questions | 13.6 s | 14.5 s (median) |

Hand grading, as strict as Run D3: **✅ 18, ⚠️ 18, ❌ 0** (Run D3: ✅ 13, ⚠️ 19, ❌ 3). **Gate passed**: no ❌,
meanings mixed down from 9 to 3, wrong terms down from 5 to 1. Both predictions held.

| ⚠️ kind | Run D3 | Run D4 | Cases in Run D4 |
|---|---|---|---|
| Meanings mixed | 9 | 3 | P01, P04, P06 (used memory against the total) |
| Wrong term | 5 | 1 | L06 (storage total called "최대 용량(macOS)") |
| Added cause or advice | 3 | 7 | B04, B08, B10, B11, B12, B17, P05, most about the energy mode |
| Wrong energy mode stated | 0 | 2 | B06, B07: "High Power Mode" on battery in Automatic mode |
| Terms not in the report mentioned | 0 | 2 | P08, L02: "cell spread is not given" in an SSD or battery-time answer |
| Contradiction or fan inference | 2 | 3 | B13; P02, P03 |

**The term list fixed the terms and caused a new error.** Every Korean question got the whole list, which
starts with the three energy modes. The model then brought the modes into answers that were not about them:
"High Power Mode" on battery reports in Automatic mode (B06, B07), "turn High Power Mode off" as advice
(B08, B11), "no energy mode setting is needed" in performance answers, and terms with no fact behind them
(P08, L02, L06). Fix: only the terms that appear in the report are given.

### The charge limit and the battery discharge on the adapter (L01, L02)

| | Run D3, limit at 90% | Run D4, no limit |
|---|---|---|
| Charge, state | 90%, not charging | 90%, charging (14 min to full at the present current) |
| Power from the adapter | 72.0 W of 100 W | **85.0 W** of 100 W |
| Battery | −0.24 A, 3.0 W out | charging |
| Load | CPU 17-24%, GPU 44-77% | CPU 18%, GPU 40-47% |

Prediction written before the run: if the limit causes the discharge, the adapter supplies more than 72 W and
the battery charges without it. **Both happened.** The adapter could give more than 72 W, so it was not at
its limit in Run D3; with charging held at 90%, the battery covered a small part of the load. This supports
the limit as the cause, but does not prove it: one reading per run, and the load was not the same. The
diagnosis already reports this state as information (`battery_assist`, Run D3 fixes). It will name the limit
as the cause only once the agent can read the limit setting.

### Fixes after Run D4

| Problem | Fix | Kind |
|---|---|---|
| The term list primed the energy modes and terms with no fact | Only the terms that appear in the report are given | Code |

Gate for Run D5, written before it: route and findings all right, no ❌, no energy mode named that is not in
the facts, no mention of the energy mode in performance answers, ⚠️ at most 12 of 36.

## Run D5 — after the Run D4 fixes, charge limit back on (2026-11-16)

Commit `85deb2c`. Same models and 40 cases. The 90% charge limit (set in System Settings > Battery, no other
app) was on again.

| Check | Run D4 | Run D5 |
|---|---|---|
| Route right | 40 of 40 | **40 of 40** |
| Findings as expected | 30 of 30 | **30 of 30** |
| Answers by the model | 36 of 36 | 35 of 36 (one by the template) |
| Live battery / performance questions | 4.9 s / 14.5 s | 4.8 s / 14.1 s (median) |

Hand grading: **✅ 26, ⚠️ 10, ❌ 0** (Run D4: ✅ 18, ⚠️ 18). **Gate passed**: no ❌, no energy mode named that is
not in the facts (B06 and B07 now say nothing about the mode; B15 says "자동"), no energy mode in the
performance answers, ⚠️ 10 of at most 12.

| ⚠️ kind | Run D4 | Run D5 | Cases in Run D5 |
|---|---|---|---|
| Added cause or advice | 7 | 4 | B08, B10, B11, B12: High Power Mode named as a cause or "turn it off" as advice, where the facts say it is on |
| Meanings mixed | 3 | 3 | P01, P04, P06: "memory used by apps 12.2 GB" set against the total or called low |
| Fan inference | 2 | 2 | P02, P03: the fans are guessed at from "fan speed is not measured" |
| Template in English for a Korean question | 0 | 1 | L05: both model answers computed 60% of 24.0 GB = 14.4 GB, so the template answered |
| Wrong mode, terms not in the report, wrong term | 5 | 0 | - |

One test-set flaw found: in P05 the model read the cause from the process name ("process-stuck"). The
scenario names a process by what it does, which a real process would not.

**Third reading of the charge limit.** With the limit back on, L01-L02 again show the battery giving a little
power on the adapter: 78.4 W from the adapter (78% of its rating) and 3.4 W from the battery. Limit on: 72.0 W
and 78.4 W in, the battery discharging; limit off: 85.0 W in, the battery charging. The diagnosis reported it
as `battery_assist` (information), as intended after Run D3.

### Fixes after Run D5, and where the answers stop

| Problem | Fix | Kind |
|---|---|---|
| "Memory used by apps" next to "memory available" (P01, P04, P06 in three runs) | Not given to the writer. The two figures come from different counts (vm_stat anonymous pages; memory_pressure free, inactive and purgeable), so 12.2 GB used with 88% of 24 GB available looks like a contradiction even to a person. The reading is still stored | Code |
| Template in English without a reason (L05) | For a Korean question the template starts with a Korean line saying the answer could not be written | Code |

Not fixed by the writer, on purpose: the fan guesses (P02, P03) need a fan reading, not a prompt rule (the
SMC fan reading of the Stage 7 plan); the mode named as a cause (B08, B10-B12) is a limit of the 4B model
seen in every run. From Run D1 to Run D5 the hand grade went from no usable answer to ✅ 26 of 36 with no ❌.
The answer writer is left here; the next device-set run comes with the next Stage 7 feature.

