# Benchmarks

## Environment

| Item | Value |
|---|---|
| Machine | MacBook Pro, Apple M4 Pro (14-core CPU, 20-core GPU) |
| Memory | 24 GB unified memory |
| Runtime | Ollama 0.40.11 (Homebrew, CLI only) |
| Server flags | `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0` |

## Run 1 — Baseline generation speed (2026-10-29)

- Prompt: "Explain what an AI agent is in about 100 words."
- Mode: `/api/chat`, `stream: false`, `think: false`
- Script: `scripts/bench_speed.sh`

| Model | Size on disk | Load time | Prompt eval | Generation | Total |
|---|---|---|---|---|---|
| qwen3:8b | 5.2 GB | 1.1 s | 137.4 tok/s | **43.0 tok/s** | 3.8 s |
| qwen3:14b | 9.3 GB | 3.8 s | 191.9 tok/s | **25.5 tok/s** | 8.2 s |

### Notes

- Generation: 8B is ~1.7x faster than 14B. Both are well above human reading speed.
- Prompt eval numbers are not reliable here: the prompt is only ~20 tokens, so fixed overhead dominates. Re-measure with a long prompt (e.g. 2k tokens with tool schemas) to reflect real agent workloads.
- Load time is a one-time cost per model while it stays resident in memory.

## Run 2 — Plain model vs. agent with tools (2026-10-29)

- Prompt: "지금 몇 시야? 그리고 1847*293/3 정확히 계산해줘" ("What time is it? And calculate 1847*293/3 exactly.")
- Model: qwen3:8b

| Setup | Current time | Calculation | Behavior |
|---|---|---|---|
| `ollama run` (no tools, thinking on) | Could not answer | Correct (180,390.33...) | Hundreds of reasoning tokens; re-checked the multiplication three times |
| Agent (`main.py --fast`, thinking off) | Correct (system clock) | Correct (exact, via `calculator`) | Called `get_current_time` and `calculator` in a single step, then answered |

### Notes

- The model cannot know the current time without a tool; it has no access to the system clock.
- Without tools, arithmetic accuracy depends on the model's reasoning and is not guaranteed. With tools, the model only decides *which* tool to call; execution is deterministic.
- The model issued two tool calls in parallel in one step.
- Follow-up: the final answer repeated the raw float (`180390.33333333334`). Format numeric tool output or instruct the model to round.

## Run 3 — Date reasoning after a time tool call: 8B vs. 14B (2026-10-29)

- Tool available: `get_current_time` only (returns `2026-10-29 HH:MM:SS KST (Thursday)`)
- Four questions asked in Korean, in one session, in the same order, with identical wording
- `think: false`, `temperature: 0.2`

| # | Question | Ground truth | qwen3:8b | qwen3:14b |
|---|---|---|---|---|
| 1 | What day of the week is it today? | Thursday | Thursday ✅ | Thursday ✅ |
| 2 | What date is the day after tomorrow? | Oct 31 (Saturday) | "Saturday" ⚠️ (answered the weekday, not the date) | "Nov 1" ❌ |
| 3 | How many days until the end of this month? | 2 | 2 ✅ | 2 ✅ |
| 4 | How many weeks are left this year? | 63 days = 9 weeks (ISO week 44) | "Week 44, 10 weeks 2 days left" ❌ | "47 weeks passed, 5 weeks left" ❌ |

| | qwen3:8b | qwen3:14b |
|---|---|---|
| Correct tool selection | 4/4 | 4/4 |
| Correct final answer | 2/4 | 2/4 |

### Notes

- Both models always chose the right tool. Failures happened *after* the tool call, when the model did calendar arithmetic on its own.
- The larger model did not fix the problem. It failed in different ways (off-by-one date, wrong week number).
- All wrong answers were stated confidently, with no hedging. Without ground truth, they look correct.
- Conclusion: date arithmetic should be moved from the model into a tool (`date_calculator`). This set of four questions becomes the baseline for that change.

## Run 4 — Date reasoning in English, asked manually: 8B vs. 14B (2026-10-29)

- Tools available: the original four (`get_current_time`, `calculator`, `list_files`, `read_file`)
- Five questions typed one by one in `main.py`, in one session per model, same order and wording
- `think: false`, `temperature: 0.2`

| # | Question | Ground truth | qwen3:8b | qwen3:14b |
|---|---|---|---|---|
| 1 | What day of the week is it today? | Thursday | Thursday ✅ | Thursday ✅ |
| 2 | What is the date the day after tomorrow? | Oct 31, 2026 | Saturday, 2026-10-31 ✅ | Friday, Oct 30, 2026 ❌ |
| 3 | How many days are left until the end of this month? | 2 days | 2 days ✅ | 2 days ✅ |
| 4 | How many weeks are left in this year? | 9 weeks (63 days) | 10 weeks and 2 days ❌ | 2 weeks ❌ |
| 5 | What date will it be 100 days from today? | Feb 6, 2027 | 2027-02-07 ❌ | Jan 26, 2027 ❌ |

| | qwen3:8b | qwen3:14b |
|---|---|---|
| Correct answers | 3/5 | 2/5 |
| Called `get_current_time` | 5/5 | 5/5 |

### Tool calls worth noting

- 8B, Q5: called `calculator("100 / 7")` (= 14.29 weeks) and `get_current_time` again, then did the date math itself and was off by one day.
- 14B, Q5: called `calculator("2026 + (100 / 365)")` (= 2026.27, a fraction of a year), then answered Jan 26, 2027.

### Observations

- **Consistent failure across languages.** 8B answered "10 weeks and 2 days" for Q4 in both Korean (Run 3) and English. This is a systematic weakness, not noise.
- **Tool misuse.** With no date tool, both models used `calculator` for calendar math. The calculator can only do arithmetic, so the result did not help, and the models still guessed the final date.
- **Bigger was not better.** 14B scored lower than 8B again, and its errors were larger (Q2 returned tomorrow's date; Q4 said 2 weeks).
- **Confident wrong answers.** 14B justified Q4 with a made-up premise ("2026 has 52 weeks... there are 2 weeks left") without hedging.

### Conclusion

When the right tool is missing, the model forces the closest available tool and then guesses. Calendar arithmetic needs a dedicated `date_calculator` tool. Runs 3 and 4 are the baseline for that change.

## Run 5 — After adding date tools: 8B vs. 14B (2026-10-31)

- New tools: `get_current_time` (with time zones), `convert_timezone`, `add_to_date`, `date_difference`, `date_info`, `resolve_date` (`agent/time_tools.py`)
- Also changed: `calculator` description now says "never use it for dates or times"; system prompt tells the model to use date tools for all calendar math and to report tool results exactly
- Same five questions as Run 4, typed one by one in one session per model. Reference date: 2026-10-31 (Saturday), so the ground truth differs from Run 4

| # | Question | Ground truth | qwen3:8b | qwen3:14b |
|---|---|---|---|---|
| 1 | What day of the week is it today? | Saturday | Saturday ✅* | Saturday ✅ |
| 2 | What is the date the day after tomorrow? | 2026-11-02 | 2026-11-02 ✅ | November 2, 2026 ✅ |
| 3 | How many days are left until the end of this month? | 0 days | 0 days ✅ | 0 days ✅* |
| 4 | How many weeks are left in this year? | 8 weeks 5 days (61 days) | 8 weeks and 5 days ✅ | 8 weeks and 5 days ✅ |
| 5 | What date will it be 100 days from today? | 2027-02-08 | 2027-02-08 ✅ | February 8, 2027 ✅ |

| | Run 4 (no date tools) | Run 5 (date tools) |
|---|---|---|
| qwen3:8b | 3/5 | **5/5** |
| qwen3:14b | 2/5 | **5/5** |
| `calculator` used for dates | 2 times | 0 times |

### Tool calls

| # | qwen3:8b | qwen3:14b |
|---|---|---|
| 1 | `get_current_time(timezone="user")` → error, then `get_current_time(timezone="New York")` | `get_current_time()` |
| 2 | `add_to_date(date="today", days=2)` | `add_to_date(date="today", days=2)` |
| 3 | `date_difference(end="end of this month", start="today")` | `date_info(date="end of this month")` |
| 4 | `date_difference(end="end of this year", start="today")` | `date_difference(end="end of this year", start="today")` |
| 5 | `add_to_date(date="today", days=100)` | `add_to_date(date="today", days=100)` |

### Hidden failures (*correct by luck)

1. **8B, Q1 — the tool description caused the error.** The `timezone` description said "Empty means the user's local time". The model passed the literal value `"user"`, got an error, then picked New York. It answered correctly only because it was also Saturday in New York. Before 09:00 KST it would have said Friday.
2. **14B, Q3 — wrong reference date.** It asked `date_info` about the *end* of the month and read "0 days left in the month". That is only correct on the last day of the month. On Oct 29 the same call would also say 0, while the answer is 2.

### Fixes

- `timezone` descriptions now say "Omit this argument for local time". Values such as `user`, `local`, `here`, `my` are treated as local time. The error message also says to leave the field empty for local time.
- `date_info` now states the reference date ("N days left in the month after 2026-10-31"), and its description points to `date_difference` for "days until X" questions.
- Regression test added for local time-zone words. 27 offline tests pass.

### Conclusions

- Moving calendar math into tools fixed every wrong answer from Run 4 for both models.
- Model size no longer mattered: both scored 5/5. The tools, not the model, now determine correctness.
- Scoring only the final answer is not enough. Two of ten correct answers came from flawed tool calls. Tool-call traces must be reviewed too.
- Tool descriptions are prompts. One phrase ("Empty means the user's local time") directly caused a wrong tool call.

## Run 6 — Math tools, basic set (2026-10-31)

- New: `agent/math_tools.py` with an engineering `calculator` (functions, decibels, complex numbers, number bases, physical constants) and `convert_units` (pint, including Korean units pyeong/geun/don)
- Math libraries: numpy, scipy, sympy, pint (`requirements.txt`). The agent core still uses only the standard library

| # | Question | Ground truth | qwen3:8b |
|---|---|---|---|
| 1 | Square root of 2 times the sine of 30 degrees | 0.7071 | ✅ `calculator("sqrt(2) * sind(30)")` |
| 2 | 100 km/h in m/s | 27.78 | ✅ `convert_units` |
| 3 | 25 °C in °F | 77 | ✅ `convert_units` |
| 4 | 20 dBm in watts | 0.1 | ✅ `convert_units("dBm" -> "watts")` |
| 5 | 32 pyeong in m² | 105.79 | ✅ `convert_units` |

Score: 8B 5/5. Every question gave the formula or units directly, so this set only checks tool selection.

## Run 7 — Math tools, word problems and iterative fixes (2026-10-31)

Five problems where the model has to choose a formula itself: acceleration (0-100 km/h in 8 s), RL impedance at 60 Hz, Shannon capacity at 30 dB SNR, free-fall speed from 10 m, `0xFF XOR 0b1010`.

| Round | Model | Score | Main failure |
|---|---|---|---|
| Before fixes | qwen3:14b | 4/5 | Sent units to `calculator` six times in a row; built `sqrt(R²+X²) + jX` for impedance |
| After fix 1 | qwen3:14b | 4/5 | `^` was now always a power, but the model used `0xFF ^ 0b1010` for XOR and got 255¹⁰ |
| After fix 2 | qwen3:14b | 3/3 rechecked | Converted radians to degrees in its head (off by 0.01°) |
| After all fixes | qwen3:8b | 5/5 | Each wrong first tool choice was corrected in one step by the error message |

Fixes, each with a regression test:
- Agent loop blocks an identical failed call: first a warning, then a stop
- `^` is a power, except next to hex/binary literals, where it is XOR. Rewritten on tokens, because in Python `^` binds more loosely than `+`. The result states how `^` was read
- New tool `calculate_with_units` (pint). Number-unit pairs are wrapped in parentheses, because pint reads `12 V / 4 ohm` as `(12 V / 4) * ohm`
- Inverse trig results also report degrees; system prompt forbids converting units, angles or rounding in the model's head

## Run 8 — Harder multi-step problems (2026-10-31 to 2026-11-01)

Five problems: RC charge time to 90%, softmax of [2.0, 1.0, 0.1], birthday problem (23 people), arrival time for 450 km at 80 km/h from 9:30 AM, tensile stress in a 20 mm rod under 50 kN.

| Round | qwen3:8b | qwen3:14b |
|---|---|---|
| Before fixes | 3/5 | — |
| After fixes | **5/5** | **5/5** |

Failures found and fixed:
- **Silent wrong answer:** `add_to_date(date="today", hours=5.625)` started from midnight and returned 05:37. Adding hours to a date without a time of day is now an error. 12-hour times (`9:30 AM`, `tomorrow 3 PM`) and fractional hours are supported; results show both 24-hour and 12-hour forms
- **Bug in our tool:** `Ω` was replaced with ` ohm `, so `kΩ` became `k ohm` and pint read `k` as the Boltzmann constant. Fixed to `kohm`
- Long products: `seq(start, end)` and `prod()`; hints for `...`, loop syntax and loop variables; function aliases (`product`, `arctan`, `nCr`, ...)
- Functions inside unit formulas (`ln`, `exp`, `sqrt`, ...), evaluated innermost-first; arguments must be dimensionless
- Lists work element by element: `exp([2, 1, 0.1]) / sum(exp([2, 1, 0.1]))`
- Lone letters in unit formulas (`R * C`) are reported as what pint reads them as (gas constant, coulomb)
- Misplaced arguments name the tool that accepts them; `convert_units` accepts a formula as its value; an empty model reply is retried once

## Run 9 — Final holdout test: seven unseen problems (2026-11-01)

These problems were written after all fixes and were not used to tune any tool. Tools were not changed between the 8B and 14B runs.

| # | Domain | Question | Ground truth | qwen3:8b | qwen3:14b |
|---|---|---|---|---|---|
| 1 | Mechanical | Braking force: 1200 kg, 90 km/h to 0 in 40 m | 9.375 kN | ❌ stopped | ✅ 9.375 kN |
| 2 | Electrical | 100 Ω, 220 Ω, 470 Ω in parallel | 59.98 Ω | ✅ | ✅ |
| 3 | Telecom | 2 W, +10 dBi, −100 dB path loss, +3 dBi | −53.99 dBm | ❌ −84 dBm | ❌ −85 dBm |
| 4 | AI | Binary cross-entropy, p = 0.8, label 1 | 0.2231 | ✅ | ✅ |
| 5 | Computer | Address bits for 64 GiB | 36 | ✅ | ✅ |
| 6 | Probability | Exactly three sixes in 10 rolls | 0.1550 | ✅ | ✅ |
| 7 | Thermal | 2 kW kettle, 1.5 L, 20 → 100 °C | 251.2 s | ✅ | ✅ |
| | | | **Score** | **5/7** | **6/7** |

### Failure analysis

- **Q3, both models: domain knowledge.** 8B used `10*log10(2)`, which is dBW, as dBm (off by exactly 30). 14B treated 2 W as 2 dBm. The calculator already had `watts_to_dbm`, but neither model used it.
- **Q1, 8B: unit expectation.** The formula v²/(2d) was right, but it asked for `m^2/s^2` instead of `m/s^2`. The error said "[length] / [time] ** 2"; the model did not recognize this as an acceleration and repeated the call until the loop stopped it. 14B solved the same problem in one step with the work-energy relation (½mv² / d).
- No failure was caused by a tool bug. All remaining failures were model knowledge or reasoning.

| | Problems used for tuning | Unseen problems |
|---|---|---|
| qwen3:8b | 5/5 | 5/7 |
| qwen3:14b | 5/5 | 6/7 |

## Run 10 — Fixes after the holdout test (2026-11-01)

- Dimension errors now use plain names: "the formula gives an acceleration (m/s²), but 'm^2/s^2' is an energy per mass (J/kg = m²/s²)"
- Formulas with decibels get a link-budget hint: dB values are added, `watts_to_dbm(P) + gains − losses`, and 10·log10(W) is dBW, not dBm
- New functions `watts_to_dbw`, `dbw_to_watts`; the calculator description includes a link-budget example
- The Run 9 scores above are kept as the honest holdout result. A new unseen set is needed to measure these fixes
- 72 offline tests pass

## Run 11 — Vision model setup and image size (2026-11-03)

- Vision model: `qwen3-vl:8b-instruct` (8.2B, Q4_K_M, CLIP projector 576M, Apache 2.0)
- Tool: `describe_image` in `agent/vision_tools.py`. The main model stays text-only and receives only the vision model's text
- Image: `10_night_street_photo.jpg` (1932×2576 phone photo). Sign ground truth: "푸르지오강남", "(031)715-1544"

### Thinking vs. instruct variant

`qwen3-vl:8b` is the thinking variant. With `--think=false` it still started a `<think>` block and stopped after 52 tokens. The instruct variant (`qwen3-vl:8b-instruct`) answers directly and is used by the tool.

The first full-size request cost 4,044 input tokens: 23.5 s of the 30.5 s total went into reading the image, and only 1.3 s into writing the answer.

### Full image at different sizes (question: describe the photo and read any signs)

| Longest side | Sent size | Input tokens | Seconds | Sign text | Phone number |
|---|---|---|---|---|---|
| 640 | 480×640 | 1,152 | 8.4 | 👻 "부산의안경사" (invented, plus "an optician in Busan") | 👻 051-755-1244 |
| 960 | 720×960 | 1,152 | 7.7 | ❌ "무한지오경남" | ❌ 055-775-1544 |
| 1280 | 960×1280 | 1,316 | 10.0 | ⚠️ "푸르지오 건담" | ⚠️ 070-715-1544 |
| 1920 | 1440×1920 | 2,816 | 16.7 | ⚠️ "푸른지오강남" | ⚠️ 036715-1544 |

- The general scene (night, empty road, crosswalk, yellow center line, red lane with arrows, apartments) was correct at every size. The season was wrong ("bare trees, autumn or winter"; the trees have young spring leaves).
- 640 and 960 used the same 1,152 tokens: the model has a minimum image size, so going below about 960 saves nothing.
- At low resolution the model invented a complete, plausible sign instead of saying it could not read it, despite the system prompt.
- The sign covers well under 1% of the photo. No single size reads it correctly.

## Run 12 — Zoom: reading small text by cropping (2026-11-03)

`describe_image` gained a `region` argument (named halves and quarters, or `left,top,right,bottom` fractions). The crop is taken from the original full-resolution image.

| Step | Region | Sent size | Input tokens | Seconds | Result |
|---|---|---|---|---|---|
| Best full view | full, 1920 | 1440×1920 | 2,816 | 16.7 | "푸른지오강남", "036715-1544" |
| Crop, no enlargement | `0.7,0.42,1,0.56` | 580×361 | 1,180 | 4.6 | ✅ "푸르지오강남", ⚠️ "(03)715-1544" |
| Crop, enlarged 2.4× | `0.7,0.42,1,0.56` | 1405×874 | 1,302 | 5.5 | ✅ "푸르지오강남", ✅ "(031)715-1544" |
| Tight crop, enlarged 3× | `0.86,0.43,0.95,0.475` | 519×348 | 1,194 | 4.7 | ✅ "푸르지오강남", ✅ "(031)715-1544" |

Design fixes found along the way:
- **Longest-side limit made zoom useless on tall photos.** The right half of a 1932×2576 photo is still 2576 px tall, so it was scaled by the same factor. The limit is now a pixel budget (max_side² × 3/4, about 1.2 MP for 1280): smaller crops keep more of their original resolution.
- **Small crops lost thin characters.** In the 580×361 crop the "1" in "(031)" disappeared; in the source photo it is blurred into the closing bracket. Zoomed crops are now enlarged up to 3× within the budget, like a magnifier. Full images are never enlarged.

Result: the sign is read exactly, about 3× faster than the best full-image attempt (5.5 s vs. 16.7 s), with fewer input tokens (1,302 vs. 2,816).

## Run 13 — Full vision test set through the agent (2026-11-04)

- Main model `qwen3:8b`, vision `qwen3-vl:8b-instruct`. 12 images and 4 hallucination checks, asked in Korean through `main.py`
- Per-case results: `evals/vision/cases.md`

| | Result |
|---|---|
| Main cases | ✅ 2, ⚠️ 6, ❌ 4 |
| Hallucination checks | 3/4 (invented a value for a resistor that does not exist) |

Strong: Korean infographic, formula transcription (GIF), handwriting transcription, answering "not shown" for missing likes, brands and chart series.

Weak, by cause:
1. Fine detail from a downscaled full view (schematic pins, a small sign)
2. A very small source image (284×213 cartoon)
3. The main model translated questions to English and then embellished the vision answer (invented humor explanations)
4. A correct "not found" from the locate step was overridden by asking describe_image, which invented a value
5. A tool meant for one short item was used for a whole comment thread
6. Model limits that tools do not fix: key signature vs. tuning, reading the rightmost curve, counting fish

## Run 14 — Fixes from Run 13 (2026-11-04)

| Cause | Fix |
|---|---|
| Fine detail | `describe_image(focus=...)` locates the named part, crops it with a 25% margin, enlarges it and answers from the crop |
| Small images | Full images with a longer side below 768 px are enlarged up to 2× (token cost has a floor, see Run 11) |
| Translation and embellishment | Tool description asks for the user's question unchanged; system prompt forbids adding interpretations the tool did not return |
| Ignored "not found" | The result says the item is probably absent and not to ask describe_image for a value |
| Wrong tool | `read_text_in_image` is described as one short item; whole pages and threads go to `describe_image` |

100 offline tests pass. The Run 13 scores are kept as the baseline; the same set is rerun to measure these fixes.

## Run 15 — Rerun of the targeted cases after Run 14 (2026-11-04)

| # | Run 13 | Run 15 | What changed |
|---|---|---|---|
| 01 Schematic | ❌ four pins wrong | ⚠️ pins "not shown" | Used focus three times (MCU, pins, regulator). The second focus was the question itself ("the GPIO pins connected to ..."), so the wrong area was cropped. A wrong answer became an honest "not shown" |
| 03 English conversation | ❌ | ⚠️ | Who said what is now correct, including "Fair enough"; the joke is still explained weakly. Focus on "the tweet thread" covered 95% of the image (wasted call) |
| 04 Korean comments | ❌ | ❌ | Focus "모든 댓글" cropped only the header "전체 리플 [4]", so the answer said there was no content |
| 08 Cartoon | ❌ | ❌ | Enlarged 2×, still read as "shouting, flustered". The model does not recognize the knee-pain scene (model limit) |
| 10 Night street | ⚠️ | ❌ 👻 | Used focus instead of read_text_in_image; read "02-6715-1544" and stated the photo was taken in Gangnam, Seoul, from the word "강남" in a business name. The real area code 031 points to Gyeonggi-do |
| H3 R50 | ❌ 👻 | ✅ | "Cannot be confirmed; not shown" |

Questions are now passed to the vision model in the user's language. New failure type: misuse of the new `focus` argument.

Fixes (Run 16 candidates):
- `focus` must name a visible part, never the question; schematics are inspected one component at a time; focus stays empty for whole-image questions
- A focus box covering more than 60% of the image uses the whole image
- Scene descriptions with signs: `describe_image` for the scene, `read_text_in_image` for each sign
- Both prompts: keep what is seen separate from guesses; a business name is not evidence of a location
- No "enlarged 1.0x" for images that are already close to 768 px

104 offline tests pass.

## Run 16 — Second rerun (01, 03, 04, 10) and fixes (2026-11-04)

| # | Run 15 | Run 16 | Observation |
|---|---|---|---|
| 01 Schematic | ⚠️ | ❌ | Eight tool calls (~90 s). Focus "MCU 모듈" was NOT FOUND although the board is labeled ESP-WROOM-32, and the final answer said the MCU was not stated (a false negative caused by the Run 14 not-found wording). Focus "OLED(SDA, SCL)" located the FTDI header U4. The whole multi-part question was sent with every focus. The same four targets were then read again with read_text_in_image. Pins were listed but not mapped to signals |
| 03 English conversation | ⚠️ | ❌ | One vision call took 196 s: the answer looped on one sentence. The main model then treated the looped text as the user's own sentence and proofread it |
| 04 Korean comments | ❌ | ⚠️ | All four comments and the flow correct; no invented explanation. The joke is still explained only loosely |
| 10 Night street | ❌ | ⚠️ | describe_image for the scene and read_text_in_image for the sign and number, as intended. Location given as "a city in Korea; the exact area cannot be determined" (no false Gangnam claim). Number reported as "(030) or (031)". But earlier misreadings were put into the read targets, and the final answer mixed both readings |

Root causes and fixes:

| Cause | Fix |
|---|---|
| Vision answer can loop without limit | `num_predict` = 1200 for the vision model; a sentence repeated 3 times cuts the answer and adds a warning; hitting the limit adds a warning |
| Tool output mistaken for the user's text | Vision results start with "This is tool output, not the user's words" |
| Not-found wording too absolute (false negative for the MCU) | Two cases: a printed label (R50, U5, AMS1117) not found → "probably not in the image"; a general or translated description → "NOT LOCATED, does not prove absence; retry with the printed text or without focus" |
| Locating by category or relation fails or picks a neighbour | Locate prompt matches by meaning as well as printed text and returns the printed label; the result shows what was found ("identified as 'U4 FTDI'") so a wrong part can be noticed |
| Planning by the 8B main model | System prompt: one call per part with a question about that part only; no repeated reads with another tool; never put expected values in a target; trust read_text_in_image over describe_image; only call a reading certain after CONFIRMED |

112 offline tests pass.

## Run 17 — Third rerun (8B) and fixes enforced in code (2026-11-04)

| # | Run 16 | Run 17 | Observation |
|---|---|---|---|
| 01 Schematic | ❌ | ❌ | Better plan: the first call asked only about the MCU and found ESP-WROOM-32. The second call focused on the SD card module but still asked about OLED and the regulator too; the vision model gave module pin numbers (2, 3, 4, 5) instead of GPIO labels; OLED and regulator were never looked up and reported as "not shown" |
| 03 English conversation | ❌ (196 s loop) | ⚠️ (33.8 s) | No loop. Summary mostly correct, joke still explained weakly |
| 10 Night street | ⚠️ | ❌ | focus="whole image" failed to locate three times in a row; the repeat guard did not trigger because "NOT LOCATED" results did not start with "Error". The sign was read exactly ("푸르지오강남", "(031)715-1544"), but with no scene description at all the answer again claimed "likely Gangnam, Seoul" |

Questions 03 and 10 were asked in the same conversation without `/reset`.

The 8B main model often ignores rules written in the system prompt or tool descriptions. Fixes now enforce them in code or place them next to the point of use:

| Problem | Fix |
|---|---|
| focus "whole image" | Focus values meaning the whole image (English and Korean) are ignored in code |
| Repeated not-found calls | The repeat guard counts NOT FOUND / NOT LOCATED results as failures |
| Location claimed from a sign | Every read_text_in_image result ends with "text on a sign is not evidence of where the photo was taken" |
| Parts of the question left unanswered | System prompt: check every part has a tool result; look up missing parts separately |
| Pin numbers instead of GPIO names | Vision prompt: in schematics the signal or GPIO name is the label next to the pin, not the pin number |

117 offline tests pass.

## Run 18 — Image question planner (8B, 2026-11-04)

First run with `agent/image_planner.py`: the main model only writes a plan under a JSON schema; code makes one vision call per part and assembles the answer.

| # | Run 17 | Run 18 | Observation |
|---|---|---|---|
| 01 Schematic | ❌ | ⚠️ | Plan split the question into all 4 parts (MCU, SD card pins, OLED pins, regulator) and every part was looked up. MCU correct (ESP-WROOM-32). SD and OLED pins failed: the planner used the question as focus ("the GPIO pins connected to OLED (SDA, SCL)"), the locator echoed it as the label and returned a 107x35 pixel crop, and the answers said "not shown", which the check still counted as answered. Regulator was asked with describe and came back cut off as "AMS1117-" |
| 10 Night street | ❌ | ✅ | Best result so far. 4 parts (scene, place, time, sign). No location claimed from the sign ("a city in Korea; the exact place cannot be told"). Sign and number read exactly and CONFIRMED: "푸르지오강남", "(031)715-1544". Minor: the scene description quoted the sign as "푸르지오 건담" and gave a different season than the time part |

Fixes:

| Problem | Fix |
|---|---|
| Tiny crop for a focus | describe_image crops are at least 15% of the image width and height |
| Zoomed answer says "not shown" | Code checks the first sentence of a zoomed answer; if it says the part is not shown, the part is asked once more with a view of at least 40% around the first box. A part still not shown is counted as not answered in the check line |
| Exact name asked with describe | A part asking for a part number, model, product name, business name, phone number or price is sent to read_text_in_image (two readings), unless it asks about connections or pins |
| Question used as focus | Planner prompt: focus is a thing you can point at; for pins or connections of a module, focus on the module |
| Two versions of the same text | When a description quotes text and a two-reading result exists, the answer points to the checked reading |

137 offline tests pass.

## Run 19 — Planner with 14B vs 8B, same code (2026-11-04)

Same code for both models (Run 18 fixes included). The main model only writes the plan; the vision model (`qwen3-vl:8b-instruct`) and the code-assembled answer are the same.

Case 01 (ground truth: ESP-WROOM-32; SD CS G05, MOSI G23, SCK G18, MISO G19; OLED SDA G21, SCL G22; AMS1117-3V3):

| Part | 14B | 8B |
|---|---|---|
| Plan | 4 parts, all asked items covered | 6 parts: SD card split into one part per pin, OLED dropped (6 is the schema maximum) |
| MCU | ✅ ESP-WROOM-32 | ✅ ESP-WROOM-32 |
| SD card pins | ✅ 4/4 in one zoomed view | ⚠️ 3/4 (MOSI given as G18), four separate views of the same module |
| OLED pins | ❌ first view missed; the wider-view retry answered "SDA G23, SCL G24" with confidence (G24 does not exist) | ❌ not planned |
| Regulator | ⚠️ UNCERTAIN: tight crop cut the label ("AMS11"), wider crop read "AMS1117-3V3" plus all nearby text | ⚠️ same |

Case 10 (ground truth: 푸르지오강남, (031)715-1544):

| Part | 14B | 8B |
|---|---|---|
| Plan | 4 parts (scene, place, time, sign) | 3 parts; the scene part asked "where was it taken" instead, so no scene description |
| Location | ✅ "Korea, exact place unknown" | ✅ same |
| Sign | ⚠️ UNCERTAIN, but both readings correct; they differ only in "031-" vs "(031)" | ✅ UNCERTAIN correctly: "(03)715-1544" vs "(031)715-1544" |

Findings:
- 14B plans better: it keeps all parts and groups the pins of one module into one question. Asking the pins of one module together gave better readings than one view per pin.
- Neither model reliably follows the focus rule ("the module, not the pins").
- The wider-view retry can turn an honest "not shown" into a confident wrong answer.
- read_text_in_image compares all text of two crops of different size, so extra nearby text or punctuation alone makes readings "differ".

Fixes after Run 19:

| Problem | Fix |
|---|---|
| Wider-view retry gave a confident wrong answer | An answer that appears only after the first view said "not shown" is marked "not verified" and counted as not confirmed |
| Readings compared all text in two crops | Each reading asks only for the target text; the tight crop margin is 0.3 instead of 0.15 |
| Punctuation-only difference marked UNCERTAIN | Readings with the same letters and digits are "CONFIRMED CHARACTERS" and both forms are shown; a missing digit is still UNCERTAIN |
| 8B dropped parts from the plan | Image questions are planned by `qwen3:14b`, also in fast mode (`planner_model` in config.toml, `--planner-model` to override) |
| Parts missing from the plan went unnoticed | Labels in the question (CS, OLED, AMS1117) and a request to describe must appear in the plan; otherwise a new plan is requested once, and anything still missing is reported in the answer |
| One view per pin of the same module | Parts with the same focus are asked together; maximum parts raised from 6 to 8 |
| Sign note on a schematic | The note about signs and locations is added only when the target is a sign or shop |
| No timings for the planner | The plan line shows planning time; the check line shows total time |

147 offline tests pass.

## Run 20 — Recheck of 01 and 10 after the Run 19 fixes (2026-11-04)

Fast mode (`qwen3:8b`), image questions planned by `qwen3:14b`.

| # | Run 19 (14B) | Run 20 | Observation |
|---|---|---|---|
| 01 Schematic | ⚠️ | ⚠️ | MCU ✅. SD card 4/4 ✅. OLED: the first view missed, the wider-view retry answered SDA G23 (wrong) and SCL G22 (right), now shown as "not verified" instead of as a finding. Regulator: readings "AMS1117" and "AMS1117-3V3" (tight crop cut off) shown as uncertain. No confident wrong answer. Plan 19.8 s, total 64.5 s |
| 10 Night street | ✅ | ✅ | 4 parts. Sign CONFIRMED: "푸르지오강남", "(031)715-1544". No location from the sign. The scene description quoted the sign wrongly ("푸르지오 건담", "075-1544"), and the answer points to the checked reading. Plan 15.9 s, total 56.1 s |

Pattern over Runs 18-20: every focus written as a request ("OLED interface (SDA, SCL)", "the GPIO pins connected to SD card") came back with the request itself as the "printed label", and every answer from that view was wrong or "not shown". Every focus matched to a real printed label ("Micro SD Card", "ESP-WROOM-32", "AMS1117-3V3") was right.

Fixes:

| Problem | Fix |
|---|---|
| One reading cut off ("AMS1117" vs "AMS1117-3V3") | PARTLY CONFIRMED: the longer reading is shown, with the note that the rest was read once |
| Focus with a bracket list | The list in brackets is removed from the focus |
| View placed without a printed label | When the locator returns the request itself as the label, the answer is marked "not verified" |

152 offline tests pass.

## Run 21 — Full vision set through the image planner (2026-11-05)

Per-case results are in `evals/vision/cases.md`. Main cases ✅ 2, ⚠️ 5, ❌ 5; hallucination checks 4/4.

Better than Run 13: 01 (dense schematic), 03 (conversation), H3 (no invented R50 value).
Worse than Run 13: 02, 06, 10 (English question), 11, and 07 shown as uncertain.

Lesson: Runs 18-20 were tuned on cases 01 and 10 only. The full set showed that the planner hurts questions about the image as a whole, and that three of the Run 19-20 changes caused new failures. From now on every change is checked on the full set before the next round of fixes.

| Cause | Cases | Fix |
|---|---|---|
| Whole-image questions zoomed into a piece | 04, 06, 11 | Counting, comparing, flow, humor, feelings, mood, style, layout and summaries are never zoomed |
| Several looks at the whole image lose context and repeat content | 03, 04, 05 | All whole-image parts are asked together in one call |
| Small box labelled with the request itself | 02, 04, 06 (and 01 in Runs 18-20) | Treated as not located; the part is asked about the whole image and marked as not checked by zoom. Large boxes found this way (07, 08, 09) are trusted, without the warnings Run 20 added |
| Reading repeated the request ("the key signature at the beginning of the staff") | 02 | Counts as no text; the reading prompt says to write [no text] for symbols or drawings |
| "signature" matched the sign note | 02 | Word boundaries |
| "explain why it is funny" taken as a missing description | 04 | The "describe" coverage check was removed; the label check stays |
| "log10(Pb)" cut to "log10" | 06 | Only a bracket after a space is removed |
| Three real repeats cut as a loop | 09 | Repetition guard at five repeats |
| "any signs" read a small unreadable sign | 10 | General read targets use the largest located box; the planner is asked to name one specific text |
| "Not shown." after a failed locate marked unverified | H4 | Shown as a plain "not shown" answer |

159 offline tests pass.

## Run 22 — Full set after the Run 21 fixes, first automated run (2026-11-05)

`python scripts/run_vision_set.py --fast` ran all 16 cases in 7.2 minutes (Run 21 by hand: about 20 minutes of questions). Per-case results are in `evals/vision/cases.md`.

Main cases ✅ 3, ⚠️ 8, ❌ 1; hallucination checks 4/4. Every case is at least as good as in Run 13, and 01, 03, 04, 10 and H3 are better. Whole-image questions now take one call: 03 took 12 s (31 s in Run 21), 05 13 s (24 s), 11 14 s (53 s).

| Problem | Case | Fix |
|---|---|---|
| The wider reading added the next line to the title ("WONDERWALL" + "Guitar/Ukulele") | 02 | When the wider reading only adds whole lines, the tight reading is confirmed and the extra lines are shown as nearby text |
| Artist and instrument both read "Guitar/Ukulele" | 02 | Two parts that read the same text are both marked "check the place" |
| Key signature: both readings "[no text]" | 02 | A reading with no text falls back to the whole image |
| "The text of the comments" read as one short text: only the first comment | 04 | Comments, conversations, threads and pages are transcribed from the whole image |
| "표시되지 않았습니다" not recognised as "not shown" | H1 | Added to the not-shown phrases |

Left for later: formula readings that differ only in LaTeX vs plain text (Stage 5, formulas), and model limits in 06, 08 and 11 (Stage 7, thinking experiment).

165 offline tests pass.

## Run 23 — Repeat run with the Run 22 fixes (2026-11-05)

16 cases in 6.7 minutes. Main cases ✅ 4, ⚠️ 7, ❌ 1; hallucination checks 4/4. Stable against Run 22; case 04 improved to ✅ and took 24 s instead of 57 s. Per-case results are in `evals/vision/cases.md`.

The Run 22 fixes acted as intended: the title and the first formula were confirmed with the extra lines shown as nearby text, the artist and instrument readings that matched each other were both flagged, the key signature fell back to the whole image, the comment thread was transcribed in one whole-image call, and H1 was recognised as "not shown".

Stage 3 (vision) ends here. Remaining errors are the vision model's own whole-image readings (06, 08, 11, the key signature in 02, the hand gesture in 09), carried to Stage 7.

## Accurate profile added (2026-11-05)

Speed is not the goal of this project; accuracy is. Like a link that adds redundancy instead of accepting bit errors, the accurate profile spends more model calls per question:

- a second look on a different view for every factual answer, compared in code, and a third look with a majority vote when the two differ
- a tile scan of large images before whole-image questions
- the thinking vision model (`qwen3-vl:8b`) for counting, comparing and chart questions
- planning with thinking, and a pixel budget of about 1.9 MP

`--fast` keeps the Run 23 setup for quick checks. Both profiles are run on the same set next (Run 24).

179 offline tests pass.

## Run 24 — Model size × checking method (2026-11-05)

`run_vision_set.py --compare`, four profiles on the same 16 cases, the same vision model in all. Per-case scores are in `evals/vision/cases.md`.

| Profile | Planner | Checks | ✅ / ⚠️ / ❌ (12 main cases) | Hallucination checks | Time |
|---|---|---|---|---|---|
| small | 8B | one look | 3 / 7 / 2 | 4/4 | 6.4 min |
| large | 14B | one look | 3 / 8 / 1 | 4/4 | 7.5 min |
| small-accurate | 8B | second look + majority, tile scan, thinking vision model | 3 / 6 / 3 | 4/4 | 21.4 min |
| large-accurate | 14B | the same | 2 / 7 / 3 | 4/4 | 30.7 min |

1. 14B planning beats 8B planning (case 11: the 8B plan changed the question's language, then "exactly three fish").
2. The accurate profile as built is worse and 3-4× slower. The thinking vision model refused inferences, returned one empty answer and claimed "Gangnam, Seoul" from a sign. Agreement between two looks was shown as ✔ even when both were wrong, and the check was never compared with the prose answer.
3. Individual pieces helped where they were used narrowly: the second look caught invented pins, the tile scan read a sign correctly, and the accurate profiles produced the best answers so far for four cases, but not reliably.

More model calls do not buy accuracy by themselves; the extra calls must check something independent, and agreement must not be presented as correctness. The everyday profile stays `--fast` (8B main model, 14B planner, one look).

## Run 25 — Document set, first run (2026-11-06)

`run_eval_set.py --set documents --fast`: 19 cases (3 documents) in 19.2 minutes. Main questions ✅ 13, ⚠️ 3, ❌ 0; hallucination checks 3/3. Per-case results and fixes are in `evals/documents/cases.md`.

Text that the file already contains is the strongest source: every question answerable from slide text was correct and cited the right page, across Korean questions on English slides. The weak points were all in the vision path and the checks around it: transcriptions wrapped in a LaTeX document, the repetition guard cutting a page of equations, unneeded page readings, false "no citation" warnings on correct "not in the document" answers, and one invented equation in a practice question.

200 offline tests pass.

## Run 26 — Document set after the Run 25 fixes (2026-11-06)

19 cases in 11.2 minutes (Run 25: 19.2). Main questions ✅ 12, ⚠️ 4, ❌ 0 (first written as 14 and 4, a counting error; ✅ 13, ⚠️ 3 after the D05 regrade in Run 28); hallucination checks 3/3, now without false warnings. The question about an absent STM32 took 3.6 s instead of 258 s, and the practice questions no longer contain an invented equation. Two answers left out part of what the cited pages said (D03, D06); the answer prompt now asks for every part and every listed point, which is a prompt rule and not a guarantee. Per-case results are in `evals/documents/cases.md`.

201 offline tests pass.

## Run 27 — Document holdout (2026-11-07)

Three unseen lectures (biology, economics, deep learning), code frozen at `12d35a0`, run once: 24 cases in 15.1 minutes. Main questions ✅ 16, ⚠️ 2, ❌ 3 (76% correct); hallucination checks 3/3. The development set after two rounds of fixes was at 81% correct (Run 26, corrected in Run 28), so the accuracy carried over to new documents. The three failures are new types: image-only slides cannot be found by page selection, superscripts are lost in the text layer (10² read as 102), and figure transcriptions drop the labels that tie numbers to words. No answer invented a fact absent from the documents. Per-case results are in `evals/documents/cases.md`.

## Run 28 — Fixes from the document holdout, checked (2026-11-07)

Fixes: picture-only pages get a cached vision caption used in page selection; superscript digits are found from character positions in the PDF text layer and written as 10^2; figure readings keep each value with its label; numbers followed by Korean counters ("102개") are now checked.

| Set | Before | Run 28 | Time |
|---|---|---|---|
| Development (19 cases) | ✅ 13, ⚠️ 3, ❌ 0 (Run 26, corrected) | ✅ 14, ⚠️ 2, ❌ 0 | 18.3 min (11.2) |
| Holdout documents, now seen (24 cases) | ✅ 16, ⚠️ 2, ❌ 3 (Run 27) | ✅ 18, ⚠️ 3, ❌ 0 | 25.2 min (15.1) |

Hallucination checks 3/3 in both. All three holdout failures improved (GA7 and GC3 correct, GA6 found but one of four methods mislabelled). The prompt rule against merging separate points did not help. The cost is time: captioned pages are now selected and read in full. Correction: D05 was graded ⚠️ in Runs 25-26, but the slide defines f_s as the subcarrier spacing, so the answers were correct. Three bugs in the checks were found and fixed (a citation copied with the page note, a Korean "not in the document" phrasing, empty equation pairs). Because these documents have been seen, the next measure is a new holdout. Per-case results are in `evals/documents/cases.md`.

208 offline tests pass.

## Run 29 — Second document holdout: research papers (2026-11-07)

Two unseen papers (a two-column conference paper and a one-column journal paper), code frozen at `df47eb8`, run once: 24 cases in 11.1 minutes. Main questions ✅ 8, ⚠️ 2, ❌ 11 (38% correct); hallucination checks 3/3. The lecture holdout (Run 27) was 76%.

The design that worked for slides fails on papers. Page selection sees only the first line and 140 characters of each page, which on a dense paper page is the middle of a sentence, so tables, headings and captions further down are invisible; 9 of the 11 failures started with the wrong pages. The 10,000-character context is split over the selected pages, so three paper pages are each cut to their first third. Given the wrong pages, the answer model said the document does not cover the question, and the code accepted it: nine of the failures are false "not in the document" answers, which the hallucination checks cannot detect because that is exactly the answer they reward. Per-case results are in `evals/documents/cases.md`.

## Run 30 — Papers searched by passage, regression check (2026-11-08)

Fixes from Run 29: PDFs with long pages are read as papers and searched by passage (sections, table and figure captions, paragraphs) with the planner model and BM25 keyword search; whole passages are given instead of cut pages; a short "not in the document" answer triggers a second keyword search; papers flag vector figures and numbered equations; superscripts may rise half a character height.

| Set | Before | Run 30 | Time |
|---|---|---|---|
| Development (lectures) | ✅ 14, ⚠️ 2, ❌ 0 | ✅ 16, ⚠️ 0, ❌ 0 | 13.2 min |
| First holdout (lectures, seen) | ✅ 18, ⚠️ 3, ❌ 0 | ✅ 19, ⚠️ 2, ❌ 0 | 10.5 min |
| Second holdout (papers, seen) | ✅ 8, ⚠️ 2, ❌ 11 | ✅ 19, ⚠️ 0, ❌ 2 | 14.5 min |

"Not in the document" checks 3/3 in every set. The gate set before the run (no drop on the lecture sets) passed. The paper score is measured on documents that guided the fixes, so it overstates; a third holdout of new papers is the real test. Remaining failures: a fact only shown in a figure when the question does not mention a figure, and a vague answer from a badly chosen passage. Per-case results are in `evals/documents/cases.md`.

215 offline tests pass.

## Run 31 — Third document holdout: long papers (2026-11-08)

Two unseen papers, a 36-page two-column survey (ISAC) and a 43-page one-column tutorial (RIS), code frozen at `416364e`, run once: 27 cases in 32.3 minutes. Main questions ✅ 15, ⚠️ 5, ❌ 4 (62.5% correct); hallucination checks 3/3. ISAC 10 of 12, RIS 5 of 12.

| Holdout | Documents | Correct |
|---|---|---|
| Run 27 | Lecture slides | 76% |
| Run 29 | Two short papers, before passage search | 38% |
| Run 31 | Two long papers, after passage search | 62.5% |

The passage search carried over to unseen papers but not fully. Two of the four failures are a bug: passages offered to the answer but dropped by the 10,000-character budget counted as already checked, so the second search never returned to them. Other causes: index lines show only the start of long passages, the answer model adds acronym expansions the paper does not use, and one real fact was cited to the wrong page. A practice-question task on the 43-page paper took 15.5 minutes. Per-case results are in `evals/documents/cases.md`.

