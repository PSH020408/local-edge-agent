# Local LLM Agent

A tool-using agent that runs entirely on a MacBook Pro (Apple M4 Pro, 24 GB) with local models served by Ollama. No cloud APIs. The agent core uses only the Python standard library; the math tools use numpy, scipy, sympy and pint, the vision tools use Pillow, and the document tools use pypdfium2 and python-pptx.

Author: PARK, SEHO

## Motivation

An LLM is a probability-based decision engine that can only output text. This project wraps a local LLM with tools and an agent loop: the LLM handles judgment (what to do, which tool to use), and code handles exact execution. This makes tasks possible that the LLM could not do on its own, such as reading the clock, the file system or an image, and makes tasks it could only guess at, such as arithmetic, exact and efficient.

A second theme runs through the project: a rule only holds reliably when code enforces it. Rules written in prompts are followed inconsistently by small models, so constraints that matter for correctness are moved into code and shown in the terminal when they act ([docs/guardrails.md](docs/guardrails.md)).

See [docs/findings.md](docs/findings.md) for experiments and results, and [docs/roadmap.md](docs/roadmap.md) for the stage plan.

## Architecture

```
user input
   |
   +-- contains a document path (.pdf, .pptx)? --yes--> Document planner (agent/document_planner.py)
   |                                      pages are extracted as text; the planner model picks pages
   |                                      (slides) or passages (papers: sections, tables, figure captions);
   |                                      pages with equations or figures are read by the vision model;
   |                                      the answer cites [p.N] and code checks citations and numbers;
   |                                      "not in the document" is accepted only after a second search
   |
   +-- contains an image path? --yes--> Image question planner (agent/image_planner.py)
   |                                      1. plan: qwen3:14b splits the question into parts (JSON schema)
   |                                      2. execute: code makes one vision call per part
   |                                      3. check: code verifies every part was answered
   |                                      4. answer: code assembles the answer from the vision results
   |                                                      |
   no                                                     v
   v                                       qwen3-vl:8b-instruct (vision model)
Agent loop (agent/loop.py) <-- system prompt + tool schemas + history
   |
   v
OllamaClient (agent/llm.py) --HTTP--> Ollama server --> qwen3:14b / qwen3:8b (main)
   |
   v
tool calls? --yes--> ToolRegistry (agent/tools.py) runs the tool --> result goes back to the model
   |
   no
   v
final answer
```

- **Tool registry**: plain Python functions become tools. JSON schemas are generated from type hints and docstrings.
- **Guards in code**: argument validation, repeated-failure blocking, step limits, image preparation, two-reading verification for text in images, and the image planner. Each guard is listed with the run that motivated it in [docs/guardrails.md](docs/guardrails.md).
- **Safety**: file tools are sandboxed to the workspace folder; tools can require user confirmation.
- **Tracing**: every model call and tool result is written to `logs/*.jsonl`.

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
```

## Tests

```bash
python -m unittest discover -s tests -v          # offline tests with a scripted fake model
python scripts/run_eval_set.py --set documents --fast   # the document test set
python scripts/run_vision_set.py --fast          # the vision test set, fast profile (about 7 minutes)
python scripts/run_vision_set.py --accurate      # the same set, experimental accurate profile (much slower)
python scripts/run_vision_set.py --compare       # model size x checking method: small, large, small-accurate, large-accurate
```

The offline tests run without Ollama. The vision test set (12 cases and 4 hallucination checks, [evals/vision/cases.md](evals/vision/cases.md)) writes a full report to `logs/vision_runs/`; answers are scored by reading them. The set was used during development, so its scores are optimistic; a holdout set is the next check.

## Benchmarks

See [docs/benchmarks.md](docs/benchmarks.md).

## License

MIT License. See [LICENSE](LICENSE).
