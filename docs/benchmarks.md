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
