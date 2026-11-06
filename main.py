"""Interactive command-line entry point for the local agent.

Usage:
    python3 main.py            # main model
    python3 main.py --fast     # fast model for quick checks
    python3 main.py --model qwen3:8b
    python3 main.py --fast --planner-model qwen3:8b   # also plan image questions with the fast model
    python3 main.py --accurate # accuracy over speed: verified image answers (profiles in config.toml)
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

from agent import Agent, LLMError, OllamaClient, TraceLogger, build_default_registry
from agent.display import format_event, format_tool_call
from agent.document_planner import DocumentQuestionPlanner
from agent.image_planner import ImageQuestionPlanner, PlannerOptions
from agent.vision_tools import VisionConfig

ROOT = Path(__file__).resolve().parent
DIM, CYAN, RESET = "\033[2m", "\033[36m", "\033[0m"


def load_config(path: Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def confirm(name: str, args: dict) -> bool:
    answer = input(f"{CYAN}Allow {name}({json.dumps(args, ensure_ascii=False)})? [y/N] {RESET}")
    return answer.strip().lower() == "y"


def show_tool_call(name: str, args: dict, result: str) -> None:
    print(format_tool_call(name, args, result))


def resolve_profile(cfg: dict, name: str | None) -> dict:
    """Settings of a profile from config.toml ([profiles.fast], [profiles.accurate]); {} for none."""
    if not name:
        return {}
    profiles = cfg.get("profiles", {})
    if name not in profiles:
        raise SystemExit(f"Unknown profile '{name}'. Profiles in config.toml: {', '.join(profiles) or 'none'}")
    return dict(profiles[name], name=name)


def build_session(
    cfg: dict,
    model: str,
    planner_model: str | None = None,
    use_planner: bool = True,
    on_tool_call=show_tool_call,
    on_event=lambda m: print(format_event(m)),
    interactive: bool = True,
    profile: dict | None = None,
):
    """Create the agent, the registry and the image planner. Shared by main() and scripts/run_vision_set.py."""
    profile = profile or {}
    llm_cfg, agent_cfg = cfg["llm"], cfg["agent"]
    llm = OllamaClient(
        model=model,
        host=llm_cfg["host"],
        think=llm_cfg.get("think", False),
        options={"temperature": llm_cfg.get("temperature", 0.2), "num_ctx": llm_cfg.get("num_ctx", 8192)},
    )
    workspace = (ROOT / agent_cfg.get("workspace", ".")).resolve()
    vision_cfg = cfg.get("vision", {})
    vision_client, vision_config = None, None
    if vision_cfg.get("enabled", False):
        vision_config = VisionConfig(
            model=vision_cfg.get("model", "qwen3-vl:8b-instruct"),
            max_side=profile.get("vision_max_side", vision_cfg.get("max_side", 1280)),
            keep_alive=str(vision_cfg.get("keep_alive", "5m")),
            num_ctx=profile.get("vision_num_ctx", vision_cfg.get("num_ctx", 8192)),
            num_predict=vision_cfg.get("num_predict", 1200),
            reasoning_model=profile.get("reasoning_vision_model", ""),
        )
        vision_client = OllamaClient(
            model=vision_config.model,
            host=llm_cfg["host"],
            think=False,
            options={"temperature": 0.1, "num_ctx": vision_config.num_ctx, "num_predict": vision_config.num_predict},
            keep_alive=vision_config.keep_alive,
        )
    reasoning_client = None
    if vision_client is not None and vision_config.reasoning_model:
        # Qwen recommends sampling (not near-zero temperature) for thinking; the token limit
        # covers the thinking text as well as the answer.
        reasoning_client = OllamaClient(
            model=vision_config.reasoning_model,
            host=llm_cfg["host"],
            think=True,
            options={"temperature": 0.6, "top_p": 0.95, "num_ctx": vision_config.num_ctx,
                     "num_predict": profile.get("reasoning_num_predict", 6000)},
            timeout=900,
            keep_alive=vision_config.keep_alive,
        )
    registry = build_default_registry(workspace, vision_client, vision_config, reasoning_client)
    logger = TraceLogger(ROOT / agent_cfg["log_dir"]) if agent_cfg.get("log_dir") else None
    agent = Agent(
        llm,
        registry,
        max_steps=agent_cfg.get("max_steps", 8),
        confirm=confirm if interactive else (lambda name, args: False),
        on_tool_call=on_tool_call,
        logger=logger,
    )

    planner_model = planner_model or profile.get("planner_model") or agent_cfg.get("planner_model") or model
    planner_llm = llm
    planner_think = profile.get("planner_think", llm_cfg.get("think", False))
    if planner_model != model or planner_think != llm_cfg.get("think", False):
        planner_llm = OllamaClient(
            model=planner_model,
            host=llm_cfg["host"],
            think=planner_think,
            options={"temperature": llm_cfg.get("temperature", 0.2), "num_ctx": llm_cfg.get("num_ctx", 8192)},
        )
    image_planner = document_planner = None
    if use_planner and agent_cfg.get("image_planner", True) and registry.vision is not None:
        options = PlannerOptions(
            verify=profile.get("verify", False),
            scan_tiles=profile.get("scan_tiles", False),
            reasoning_vision=bool(vision_config and vision_config.reasoning_model),
        )
        image_planner = ImageQuestionPlanner(
            planner_llm, registry, workspace, on_tool_call=on_tool_call, on_event=on_event, options=options
        )
    if use_planner and agent_cfg.get("document_planner", True):
        # Document answers come from the planner model too: it reads the pages and must cite them.
        document_planner = DocumentQuestionPlanner(
            planner_llm, registry, workspace, on_tool_call=on_tool_call, on_event=on_event
        )
    planner = QuestionRouter(document_planner, image_planner) if (image_planner or document_planner) else None
    return agent, planner, registry, workspace, vision_config, planner_model


class QuestionRouter:
    """Questions with a document path go to the document planner, with an image path to the image planner.

    Anything else returns None and goes to the agent loop.
    """

    def __init__(self, documents: DocumentQuestionPlanner | None, images: ImageQuestionPlanner | None) -> None:
        self.documents, self.images = documents, images
        self.options = images.options if images else PlannerOptions()

    def run(self, question: str) -> str | None:
        answer = self.documents.run(question) if self.documents else None
        if answer is None and self.images:
            answer = self.images.run(question)
        return answer


def profile_name(args) -> str | None:
    return args.profile or ("accurate" if args.accurate else "fast" if args.fast else None)


def select_model(cfg: dict, args, profile: dict) -> str:
    llm_cfg = cfg["llm"]
    if args.model:
        return args.model
    if profile.get("model"):
        return profile["model"]
    return llm_cfg["fast_model"] if args.fast else llm_cfg["model"]


def describe_setup(model: str, vision_config, planner, planner_model: str, profile: dict) -> str:
    parts = [f"Model: {model}"]
    if profile:
        parts.insert(0, f"Profile: {profile['name']}")
    if vision_config:
        parts.append(f"Vision: {vision_config.model}" + (f" + {vision_config.reasoning_model} (thinking)" if vision_config.reasoning_model else ""))
    if planner and planner.images:
        extras = [name for name, on in (("verify", planner.options.verify), ("tile scan", planner.options.scan_tiles)) if on]
        parts.append(f"Image planner: {planner_model}" + (f" ({', '.join(extras)})" if extras else ""))
    if planner and planner.documents:
        parts.append(f"Documents: {planner_model}")
    return " | ".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local LLM agent")
    parser.add_argument("--config", default=str(ROOT / "config.toml"))
    parser.add_argument("--model", help="override the model name")
    parser.add_argument("--fast", action="store_true", help="profile 'fast' from config.toml")
    parser.add_argument("--accurate", action="store_true", help="profile 'accurate' from config.toml")
    parser.add_argument("--profile", help="any profile name from config.toml")
    parser.add_argument("--planner-model", help="override the model that plans image questions")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    profile = resolve_profile(cfg, profile_name(args))
    model = select_model(cfg, args, profile)
    agent, planner, registry, workspace, vision_config, planner_model = build_session(
        cfg, model, args.planner_model, profile=profile
    )

    print(f"{describe_setup(model, vision_config, planner, planner_model, profile)} | Tools: {', '.join(registry.names())} | Workspace: {workspace}")
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
            answer = planner.run(user_input) if planner else None
            if answer is not None:
                agent.remember(user_input, answer)
            else:
                answer = agent.run(user_input)
            print(f"agent> {answer}\n")
        except LLMError as exc:
            print(f"Error: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
