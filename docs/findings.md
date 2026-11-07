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

## 8. Experiment 3: Giving a text-only agent eyes (Runs 11-23)

The main models are text-only. A separate vision model (`qwen3-vl:8b-instruct`) is called as a tool and returns text, so the main model never sees pixels.

What mattered, in the order it was found:

1. **Image size is a cost.** A 1932×2576 phone photo cost 4,044 input tokens and most of the response time. Images are fitted to a pixel budget (about 1.2 MP); below about 960 px the token cost stops falling, so small images are enlarged instead.
2. **Fine detail needs a zoom, and a zoom needs a target.** Small text in a full view is misread ("070-715-1544" for "(031)715-1544"). The vision model can locate a part (Qwen-VL boxes on a 0-1000 scale), and the agent crops and enlarges it. Locating works when the request names printed text ("Micro SD Card", "ESP-WROOM-32"). When the request is a description ("the OLED interface (SDA, SCL)"), the locator often returns the request itself as the label and a small wrong box, and every answer from such a view was wrong (Runs 18-21). Such boxes are now treated as not located.
3. **Reading twice turns a guess into a measured result.** `read_text_in_image` reads a tight and a wider crop and code compares them: confirmed, only punctuation differs, one reading cut off, extra nearby lines, or uncertain. Disagreement is shown, never hidden.
4. **Prompt rules were not enough for the 8B model.** It skipped parts of questions, asked every zoomed view the whole question and picked one of two different readings. The image question planner moved these rules into code: the plan is forced into a JSON schema, each part gets its own vision call, completeness is checked, and the answer is assembled by code.
5. **Zooming everything is as wrong as zooming nothing.** Counting, comparing curves, the flow of a conversation, humour and style need the whole image. Zooming them produced "one fish" and "a single comment" (Run 21). These parts are now always answered from the whole image, in one call.
6. **Test the full set after every change.** Runs 18-20 were tuned on two cases and broke four others. A one-command test runner (`scripts/run_vision_set.py`) made the full set practical: 16 cases in about 7 minutes.

Result on the 16-case set:

| | Run 13 (first full run) | Run 23 (end of the stage) |
|---|---|---|
| Correct ✅ | 2 | 4 |
| Mostly correct ⚠️ | 6 | 7 |
| Wrong ❌ | 4 | 1 |
| Hallucination checks | 3/4 | 4/4 |

What tools could not fix: the vision model's own reading of the whole image, such as which curve is highest in a chart, a cartoon character's expression, the number of fish and a key signature. These are the input for the next experiment, a vision model with thinking enabled (docs/roadmap.md, Stage 7).

### Trading time for accuracy (Run 24)

A second profile spent 3-4× more model calls per question: a second look with a majority vote, a tile scan, a thinking vision model and planning with thinking. It was less accurate. The thinking model refused inferences and once brought back a location guess from a sign; two looks that agreed on a wrong answer were shown as checked; and the check was never compared with the answer it was checking. The lesson: extra calls only help when they test something independent, and agreement must not be presented as correctness. Planning with 14B instead of 8B did help, so the everyday profile plans with 14B.

The 16 cases were used during development, so all scores here are optimistic. A holdout set of new images is the next check.

## 9. Experiment 4: Reading study documents (Runs 25-28)

Most lecture slides and notes already contain their text as data, so the document planner extracts it exactly and uses the vision model only for pages whose equations or figures are not in the text. Answers must cite a page after every claim, and code checks the citations and any numbers that do not appear in the document.

| | Development set (Run 26) | Holdout, unseen documents (Run 27) | After the fixes, development (Run 28) | After the fixes, seen holdout (Run 28) |
|---|---|---|---|---|
| Correct ✅ | 13 of 16 | 16 of 21 | 14 of 16 | 18 of 21 |
| Mostly correct ⚠️ | 3 | 2 | 2 | 3 |
| Wrong ❌ | 0 | 3 | 0 | 0 |
| "Not in the document" checks | 3/3 | 3/3 | 3/3 | 3/3 |

The Run 26 column is corrected: it was first written as 14 of 18, a counting error, and one answer (D05) was graded down for a symbol that the slide itself defines.

The holdout kept the accuracy but showed what the development set could not: an image-only slide has no text to be found by, a superscript disappears from the text layer (10² becomes 102), and a figure transcription can lose the labels that give its numbers meaning. Each of these is a place where the text layer and the picture disagree, which is where the next work goes.

The fixes followed those three places (Run 28). A page that is only a picture now gets a short caption from the vision model, cached on disk, so page selection can find it. Superscripts are recovered from the positions of the characters: a digit whose bottom sits well above the character before it is an exponent. Figure readings must keep each number with its label. The two code fixes worked; of the two prompt changes, the label rule fixed its case and the rule against merging separate points did not. Rules in code held; rules in prompts were followed only some of the time, the same pattern as in the vision experiments.
