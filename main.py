"""Interactive command-line entry point for the local agent.

Usage:
    python3 main.py            # main model
    python3 main.py --fast     # fast model for quick checks
    python3 main.py --model qwen3:8b
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

from agent import Agent, LLMError, OllamaClient, TraceLogger, build_default_registry

ROOT = Path(__file__).resolve().parent
DIM, CYAN, RESET = "\033[2m", "\033[36m", "\033[0m"


def load_config(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def confirm(name: str, args: dict) -> bool:
    answer = input(f"{CYAN}Allow {name}({json.dumps(args, ensure_ascii=False)})? [y/N] {RESET}")
    return answer.strip().lower() == "y"


def show_tool_call(name: str, args: dict, result: str) -> None:
    preview = result if len(result) < 200 else result[:200] + "..."
    print(f"{DIM}  -> {name}({json.dumps(args, ensure_ascii=False)})\n     {preview}{RESET}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local LLM agent")
    parser.add_argument("--config", default=str(ROOT / "config.toml"))
    parser.add_argument("--model", help="override the model name")
    parser.add_argument("--fast", action="store_true", help="use the fast model from config")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    llm_cfg, agent_cfg = cfg["llm"], cfg["agent"]
    model = args.model or (llm_cfg["fast_model"] if args.fast else llm_cfg["model"])

    llm = OllamaClient(
        model=model,
        host=llm_cfg["host"],
        think=llm_cfg.get("think", False),
        options={"temperature": llm_cfg.get("temperature", 0.2), "num_ctx": llm_cfg.get("num_ctx", 8192)},
    )
    workspace = (ROOT / agent_cfg.get("workspace", ".")).resolve()
    registry = build_default_registry(workspace)
    logger = TraceLogger(ROOT / agent_cfg["log_dir"]) if agent_cfg.get("log_dir") else None
    agent = Agent(
        llm,
        registry,
        max_steps=agent_cfg.get("max_steps", 8),
        confirm=confirm,
        on_tool_call=show_tool_call,
        logger=logger,
    )

    print(f"Model: {model} | Tools: {', '.join(registry.names())} | Workspace: {workspace}")
    print("Commands: /reset  /tools  /exit\n")
    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input == "/exit":
            break
        if user_input == "/reset":
            agent.reset()
            print("(conversation cleared)")
            continue
        if user_input == "/tools":
            for tool in registry.schemas():
                print(f"- {tool['function']['name']}: {tool['function']['description']}")
            continue
        try:
            print(f"agent> {agent.run(user_input)}\n")
        except LLMError as exc:
            print(f"Error: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
