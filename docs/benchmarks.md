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
