# Local LLM Agent

A tool-using agent that runs entirely on a MacBook Pro (Apple M4 Pro, 24 GB) with a local LLM served by Ollama. No cloud APIs, no third-party Python dependencies.

Author: PARK, SEHO

## Motivation

An LLM is a probability-based decision engine that can only output text. This project wraps a local LLM with tools and an agent loop: the LLM handles judgment (what to do, which tool to use), and code handles exact execution. This makes tasks possible that the LLM could not do on its own, such as reading the clock or the file system, and makes tasks it could only guess at, such as arithmetic, exact and efficient.

See [docs/findings.md](docs/findings.md) for experiments and results.

## Architecture

```
user input
   |
   v
Agent loop (agent/loop.py) <-- system prompt + tool schemas + history
   |
   v
OllamaClient (agent/llm.py) --HTTP--> Ollama server --> qwen3:14b / qwen3:8b
   |
   v
tool calls? --yes--> ToolRegistry (agent/tools.py) runs the tool --> result goes back to the model
   |
   no
   v
final answer
```

- **Tool registry**: plain Python functions become tools. JSON schemas are generated from type hints and docstrings.
- **Safety**: file tools are sandboxed to the workspace folder; tools can require user confirmation; the loop stops after `max_steps`.
- **Tracing**: every model call and tool result is written to `logs/*.jsonl`.

## Setup

```bash
./scripts/setup_ollama.sh          # installs Ollama via Homebrew and pulls a model
ollama pull qwen3:14b
ollama pull qwen3:8b
```

## Usage

```bash
python3 main.py          # main model (qwen3:14b)
python3 main.py --fast   # fast model (qwen3:8b) for quick checks
```

Commands inside the session: `/tools`, `/reset`, `/exit`.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Tests use a scripted fake model, so they run without Ollama.

## Benchmarks

See [docs/benchmarks.md](docs/benchmarks.md).

## License

MIT License. See [LICENSE](LICENSE).
