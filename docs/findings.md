# Findings: From a Local LLM to a Local Agent

Author: PARK, SEHO
Date: 2026-10-29

## 1. Motivation

An LLM is a probability-based decision engine that can only output text. On its own, it cannot read the clock, open a file, or guarantee an exact calculation.

An agent wraps the LLM with **tools** and a **loop**. The LLM handles **judgment** (what needs to be done, which tool to use, what to do with the result), while **code** handles exact execution. As a result:

- Tasks the LLM could not do at all become possible (access to real-world information and actions).
- Tasks the LLM was only guessing at (such as arithmetic) become exact and efficient.

## 2. Environment

| Item | Value |
|---|---|
| Machine | MacBook Pro, Apple M4 Pro (14-core CPU, 20-core GPU), 24 GB unified memory |
| Runtime | Ollama 0.40.11, installed with Homebrew (CLI only, no desktop app) |
| Server flags | `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0` |
| Models | `qwen3:14b` (main, 9.3 GB), `qwen3:8b` (fast, 5.2 GB); both support `tools` and `thinking` |
| Agent | Python 3.11, standard library only |

### Why these models

- On a 24 GB Mac, roughly 16-18 GB is usable by the GPU. Agents accumulate long contexts (system prompt, tool schemas, history, tool results), so the KV cache needs headroom.
- Larger models (27B-32B) fit but leave little room for context. A 14B model is the best balance for this machine.
- The models must support tool calling. A model without it does not raise an error when given tools; it silently answers in prose.
- Two models serve two roles: the 8B model for fast iteration while developing, and the 14B model for quality checks.

## 3. Experiment 1: Model size vs. speed

- Prompt: "Explain what an AI agent is in about 100 words."
- Ollama `/api/chat`, `stream: false`, `think: false`. Script: `scripts/bench_speed.sh`

| Model | Load time | Generation | Total |
|---|---|---|---|
| qwen3:8b | 1.1 s | **43.0 tok/s** | 3.8 s |
| qwen3:14b | 3.8 s | **25.5 tok/s** | 8.2 s |

**Result:** The 8B model generates about 1.7x faster. Both are well above human reading speed (about 5-10 tok/s). Speed matters more for agents than for chat, because one task can require several model calls.

Prompt-eval speed was excluded: with a ~20-token prompt, fixed overhead dominates the measurement. It will be re-measured with realistic agent prompts.

## 4. Experiment 2: Plain model vs. agent with tools

- Prompt: "What time is it? And calculate 1847*293/3 exactly." (asked in Korean)
- Model: qwen3:8b in both cases

| | Plain model (`ollama run`, thinking on) | Agent (`main.py --fast`, thinking off) |
|---|---|---|
| Current time | Could not answer | Correct, from the system clock |
| 1847 × 293 ÷ 3 | Correct (180,390.33...) | Correct, computed exactly |
| How | Hundreds of reasoning tokens; re-checked the multiplication three times | Two tool calls (`get_current_time`, `calculator`) in a single step |

Agent trace:

```
you> 지금 몇 시야? 그리고 1847*293/3 정확히 계산해줘
  -> get_current_time({})
     2026-10-29 15:23:27 KST (Thursday)
  -> calculator({"expression": "1847*293/3"})
     180390.33333333334
agent> 지금은 2026년 10월 29일 15시 23분 27초 (목요일)입니다. 1847 × 293 ÷ 3의 결과는 180390.33333333334입니다.
```

**Result:**

- **Capability:** The plain model cannot know the current time no matter how long it reasons. The tool made an impossible task possible.
- **Reliability:** The plain model got the arithmetic right this time, but correctness is not guaranteed and degrades with harder problems. With a tool, execution is deterministic.
- **Efficiency:** The agent replaced a long chain of self-verification with one short tool request.
- **Judgment:** The model correctly identified two separate sub-tasks and issued both tool calls in parallel.

Follow-up: the final answer repeated a raw floating-point value. Numeric tool output should be formatted before it is returned to the model.

## 5. How a tool works

Example: `calculator` in `agent/builtin_tools.py`.

1. **Write a plain Python function.** Type hints and the docstring describe the tool. The docstring is sent to the model, so it also tells the model *when* to use the tool ("Use this instead of doing math yourself").
2. **Convert it to a JSON schema automatically.** `agent/tools.py` reads the function name, type hints and docstring and builds the schema sent with each request. Adding a tool only requires writing a documented function.
3. **Execute safely.** The model replies with a request such as `{"name": "calculator", "arguments": {"expression": "1847*293/3"}}`. The agent validates the arguments and runs the function.
   - `eval()` is not used: it would execute arbitrary code, such as `__import__('os').system(...)`.
   - The expression is parsed into a syntax tree with `ast`, and only numbers and `+ - * / // % **` are evaluated. Anything else is rejected, and large exponents are capped.

```
Python function + docstring
   -> JSON schema (automatic)
   -> sent to the model with the user's message
   -> model requests a tool call
   -> agent validates and executes it
   -> result is returned to the model
   -> model answers or calls another tool
```

## 6. Key takeaways

1. The LLM decides; code executes. Deterministic work belongs in tools, not in the model's reasoning.
2. The core value of tools is new capability, not only efficiency.
3. Tool descriptions are part of the prompt. How a docstring is written directly affects whether the model uses the tool.
4. Bigger is not better on a 24 GB machine. Context headroom and speed matter as much as model size.
5. Tools must be safe by design: sandboxed paths, argument validation, user confirmation for risky actions, and a step limit.

## 7. Next steps

- Define the first real custom tasks and build tools for them.
- Format numeric tool output.
- Build an evaluation set (20-30 tasks) to compare tool-call accuracy, speed and memory across 8B, 14B and 20B models.
- Re-measure prompt-eval speed with realistic agent prompts.
- Swap the backend to MLX and compare against Ollama.
