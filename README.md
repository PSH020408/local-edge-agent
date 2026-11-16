# Local Edge Agent

An edge AI agent that runs entirely on my own devices: a MacBook Pro (Apple M4 Pro, 24 GB unified memory) as the compute node and an iPhone as a client. Local models are served by Ollama; no cloud APIs. The agent core uses only the Python standard library.

Author: PARK, SEHO

## Motivation

The project treats the MacBook as one large embedded device. Instead of imitating what a cloud chatbot does, it uses the hardware at hand (battery, power and thermal sensors, the Wi-Fi radio, storage, the efficiency and performance cores) to solve engineering problems:

- **Sense**: read the machine's own telemetry in one uniform format, sampled in the background on the efficiency cores.
- **Decide**: diagnose in code (measure, compute, classify, rank causes), with lightweight models where a rule is not enough: robust statistics for anomalies, a small classifier, a fitted indoor propagation model.
- **Act**: propose fixes and apply them only after confirmation; keep the agent's own workload within power, thermal and memory limits (feedback control, admission control).
- **Explain**: a small local language model writes the answer from the structured result. It never computes or invents a number; numbers in answers are checked against the measurements by code.

Example: "why is my Wi-Fi so slow?" goes straight to the Wi-Fi agent, which reads the radio, runs a 10-second test, finds whether the Wi-Fi link, the router, the internet provider or DNS is the slow segment, and answers which uses (gaming, video calls, messaging) the link can carry and what to change.

A theme from the first stages carries over: a rule only holds reliably when code enforces it. Constraints that matter for correctness are moved from prompts into code ([docs/guardrails.md](docs/guardrails.md)).

## Status

| Part | State |
|---|---|
| Agent core: tool calling, time and engineering math tools, traces | Done (Stages 0-2) |
| Vision: images, text in images, two-reading verification | Done (Stage 3) |
| Documents: PDF and PowerPoint reading with cited, code-checked answers; equations read from the page image; tables, statements and charts | Done (Stages 4-5); Stage 6 closing |
| Device layer and battery agent | Planned, Stage 7 |
| Wi-Fi and network agent | Planned, Stage 8 |
| Coverage planning on a floor plan | Planned, Stage 9 |
| Chip-aware optimisation: small models, admission control, thermal and power feedback control | Planned, Stage 10 |
| iPhone client (Shortcuts and Siri; Bluetooth as a stretch goal) | Planned, Stage 11 |

Plan and dates: [docs/roadmap.md](docs/roadmap.md). Progress and design decisions: [docs/devlog.md](docs/devlog.md). Experiments and results: [docs/findings.md](docs/findings.md), [docs/benchmarks.md](docs/benchmarks.md).

## Architecture

Target design (the device parts are being built from Stage 7):

```
iPhone (Shortcut / Siri) --local HTTP--+
                                       v
user question --> router (code, rules first; small model only if the rules do not decide)
                    |
    +---------------+----------------+-----------------+------------------+
    v               v                v                 v                  v
 battery agent   Wi-Fi agent    performance agent   document planner   agent loop
    |               |                |              (Stages 4-6)       (tools, Stages 0-3)
    +-------+-------+----------------+
            v
 telemetry layer (agent/device/): battery, power, thermal, memory, storage, Wi-Fi radio
 background sampler at background priority (efficiency cores) --> logs for baselines and models
            |
            v
 diagnosis in code: measure -> compute -> classify -> rank causes -> propose actions (confirmed)
            |
            v
 small local model writes the answer; code checks its numbers against the measurements
```

Document and image questions use the pipeline built in Stages 3-6:

```
user input
   |
   +-- contains a document path (.pdf, .pptx)? --yes--> Document planner (agent/document_planner.py)
   |                                      pages are extracted as text; the planner model picks pages
   |                                      (slides) or passages (papers: sections, tables, figure captions);
   |                                      pages with equations, figures or charts are read by the vision model;
   |                                      statement totals and calculations are done by code;
   |                                      the answer cites [p.N] and code checks citations and numbers;
   |                                      "not in the document" is accepted only after a second search
   |
   +-- contains an image path? --yes--> Image question planner (agent/image_planner.py)
   |                                      plan parts (JSON schema), one vision call per part,
   |                                      check every part was answered, assemble the answer
   no
   v
Agent loop (agent/loop.py) --> OllamaClient (agent/llm.py) --HTTP--> Ollama --> qwen3 models
   |
tool calls --> ToolRegistry (agent/tools.py) --> result back to the model --> final answer
```

- **Tool registry**: plain Python functions become tools. JSON schemas are generated from type hints and docstrings.
- **Guards in code**: argument validation, repeated-failure blocking, step limits, two-reading verification, citation and number checks. Each guard is listed with the run that motivated it in [docs/guardrails.md](docs/guardrails.md).
- **Safety**: file tools are sandboxed to the workspace folder; tools that change something require confirmation; device readers are read-only.
- **Profiling**: every model call is logged with its load, prompt and generation time and the memory held (`logs/model_calls.jsonl`, summarised by `scripts/profile_calls.py`).

## Setup

```bash
./scripts/setup_ollama.sh          # installs Ollama via Homebrew and pulls a model
ollama pull qwen3:14b
ollama pull qwen3:8b
ollama pull qwen3-vl:8b-instruct   # vision model

python3 -m venv .venv              # Python 3.11+
source .venv/bin/activate
pip install -r requirements.txt
```

## Tools

| Group | Tools |
|---|---|
| Time and date (`agent/time_tools.py`) | `get_current_time`, `convert_timezone`, `add_to_date`, `date_difference`, `date_info`, `resolve_date` |
| Math (`agent/math_tools.py`) | `calculator` (engineering functions, lists, sequences, decibels, complex numbers, number bases, physical constants), `convert_units`, `calculate_with_units` (formulas with units) |
| Vision (`agent/vision_tools.py`) | `describe_image`: a separate vision model answers a question about an image; with a focus, the part is located, cropped and enlarged first. `read_text_in_image`: one piece of text is located and read twice at two zoom levels, and code compares the readings (confirmed / uncertain). Images are converted (GIF, WebP, transparent PNG, rotated phone photos) and fitted to a pixel budget |
| Documents (`agent/document_tools.py`, `agent/document_planner.py`) | `read_document`: PDF and PowerPoint text page by page, with tables and speaker notes, headers and footers removed. Questions that name a document go to the document planner, which answers with page citations |
| Formulas (`agent/formula_tools.py`) | `read_equation`, used by the document planner: a numbered equation is located from the text layer (a displayed equation without a number from its layout and the words around it), cropped twice, read twice by the vision model, compared by code after normalising the LaTeX, and checked against the image by a third call (confirmed / close / disagree / check failed) |
| Files (`agent/builtin_tools.py`) | `list_files`, `read_file` |

## Usage

```bash
source .venv/bin/activate
python main.py          # main model (qwen3:14b)
python main.py --fast       # profile "fast": qwen3:8b; image questions are still planned by qwen3:14b
python main.py --accurate   # experimental profile, see below
```

Profiles are defined in `config.toml`. The `accurate` profile is an experiment: factual answers about an image are asked again on a different view and compared in code (a third look decides by majority), large images are scanned in zoomed tiles first, and counting and comparing questions go to the thinking variant of the vision model (`ollama pull qwen3-vl:8b`). In Run 24 it was 3-4× slower and less accurate than `--fast`; the causes are recorded in [docs/benchmarks.md](docs/benchmarks.md) and the redesign is planned in [docs/roadmap.md](docs/roadmap.md). Use `--fast` for real work.

Commands inside the session: `/tools`, `/reset`, `/exit`. Put the image or document path in the question, for example:

```
evals/vision/images/10_night_street_photo.jpg Describe this photo and read the signs.
notes/lecture4.pdf 13페이지 수식을 설명해 줘
notes/lecture4.pdf 이 강의로 시험 문제 3개를 만들어 줘
papers/paper.pdf Write equation (3) in LaTeX and explain each symbol.
```

## Tests

```bash
python -m unittest discover -s tests -v          # offline tests with a scripted fake model
python scripts/run_eval_set.py --set documents --fast   # the document test set
python scripts/run_eval_set.py --set documents --cases evals/documents/equations.toml --fast   # questions about equations
python scripts/run_eval_set.py --set documents --cases evals/documents/tables.toml --fast   # tables, statements and charts
python scripts/profile_calls.py                    # where the time of the model calls went
python scripts/run_formula_set.py                  # formula transcription: page reading against two crops, graded by code
python scripts/run_vision_set.py --fast          # the vision test set, fast profile (about 7 minutes)
python scripts/run_vision_set.py --accurate      # the same set, experimental accurate profile (much slower)
python scripts/run_vision_set.py --compare       # model size x checking method: small, large, small-accurate, large-accurate
```

The offline tests run without Ollama. The vision test set (12 cases and 4 hallucination checks, [evals/vision/cases.md](evals/vision/cases.md)) writes a full report to `logs/vision_runs/`; answers are scored by reading them. The set was used during development, so its scores are optimistic; a holdout set is the next check.

## Benchmarks

See [docs/benchmarks.md](docs/benchmarks.md).

## License

MIT License. See [LICENSE](LICENSE).
