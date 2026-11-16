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
