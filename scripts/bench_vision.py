"""Measure how the image size sent to the vision model affects speed and answers.

Sends one image at several longest-side sizes and prints input tokens, time and the
answer for each, so the max_side setting in config.toml can be chosen from data.

Usage (from the project root, with the venv active):
    python scripts/bench_vision.py evals/vision/images/10_night_street_photo.jpg "Read any signs you can see."
    python scripts/bench_vision.py IMAGE QUESTION --sizes 640 960 1280 1920 --model qwen3-vl:8b-instruct
    python scripts/bench_vision.py IMAGE QUESTION --region right   # zoom into the right half first
"""

from __future__ import annotations

import argparse
import base64
import sys
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import OllamaClient  # noqa: E402
from agent.vision_tools import VISION_SYSTEM_PROMPT, prepare_image  # noqa: E402


def main() -> None:
    cfg = tomllib.loads((ROOT / "config.toml").read_text())
    parser = argparse.ArgumentParser(description="Vision speed vs. image size")
    parser.add_argument("image")
    parser.add_argument("question")
    parser.add_argument("--sizes", nargs="+", type=int, default=[640, 960, 1280, 1920])
    parser.add_argument("--model", default=cfg.get("vision", {}).get("model", "qwen3-vl:8b-instruct"))
    parser.add_argument("--region", default="full", help="full, right, top-left, ... or 'left,top,right,bottom' fractions")
    args = parser.parse_args()

    client = OllamaClient(
        model=args.model,
        host=cfg["llm"]["host"],
        think=False,
        options={"temperature": 0.1, "num_ctx": cfg.get("vision", {}).get("num_ctx", 8192)},
        keep_alive="5m",
    )
    path = Path(args.image)
    print(f"Model: {args.model}\nImage: {path.name}\nRegion: {args.region}\nQuestion: {args.question}\n")

    # Warm-up so the first measured size does not include model loading time.
    warm = prepare_image(path, 256)
    client.chat([{"role": "user", "content": "OK", "images": [base64.b64encode(warm.data).decode()]}])

    rows = []
    for size in args.sizes:
        image = prepare_image(path, size, args.region)
        messages = [
            {"role": "system", "content": VISION_SYSTEM_PROMPT},
            {"role": "user", "content": args.question, "images": [base64.b64encode(image.data).decode()]},
        ]
        start = time.perf_counter()
        response = client.chat(messages)
        seconds = time.perf_counter() - start
        tokens = response["stats"].get("prompt_tokens")
        answer = (response["message"].get("content") or "").strip()
        sent = f"{image.sent_size[0]}x{image.sent_size[1]}"
        rows.append((size, sent, tokens, seconds))
        print(f"=== max_side {size} -> {sent}, {tokens} input tokens, {seconds:.1f} s\n{answer}\n")

    print("| max_side | Sent size | Input tokens | Seconds |")
    print("|---|---|---|---|")
    for size, sent, tokens, seconds in rows:
        print(f"| {size} | {sent} | {tokens} | {seconds:.1f} |")


if __name__ == "__main__":
    main()
