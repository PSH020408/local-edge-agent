"""Check where the vision model thinks something is, and save the result as images.

Prints the raw location answer and the parsed box, then saves to logs/vision/:
  <name>_box.jpg    the full image with the box drawn in red
  <name>_crop.jpg   the zoomed crop that read_text_in_image would read
Open these files to confirm the box lands on the right spot.

Usage (from the project root, with the venv active):
    python scripts/vision_locate.py evals/vision/images/10_night_street_photo.jpg "the shop sign on the right side"
"""

from __future__ import annotations

import argparse
import base64
import io
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageOps  # noqa: E402

from agent import OllamaClient  # noqa: E402
from agent.vision_tools import LOCATE_PROMPT, padded_region, parse_boxes, prepare_image  # noqa: E402


def main() -> None:
    cfg = tomllib.loads((ROOT / "config.toml").read_text())
    vision = cfg.get("vision", {})
    parser = argparse.ArgumentParser(description="Show where the vision model locates a target")
    parser.add_argument("image")
    parser.add_argument("target")
    parser.add_argument("--model", default=vision.get("model", "qwen3-vl:8b-instruct"))
    args = parser.parse_args()

    client = OllamaClient(
        model=args.model,
        host=cfg["llm"]["host"],
        think=False,
        options={"temperature": 0.1, "num_ctx": vision.get("num_ctx", 8192)},
    )
    path = Path(args.image)
    overview = prepare_image(path, vision.get("max_side", 1280))
    message = {"role": "user", "content": LOCATE_PROMPT.format(target=args.target), "images": [base64.b64encode(overview.data).decode()]}
    answer = (client.chat([message])["message"].get("content") or "").strip()
    print(f"Sent: {overview.sent_size[0]}x{overview.sent_size[1]}\nRaw answer:\n{answer}\n")

    boxes = parse_boxes(answer, overview.sent_size)
    if not boxes:
        print("No box found.")
        return
    box = boxes[0]
    print("Parsed box (fractions):", ", ".join(f"{v:.3f}" for v in box))
    print("Tight crop region:", padded_region(box, 0.15))

    out_dir = ROOT / "logs" / "vision"
    out_dir.mkdir(parents=True, exist_ok=True)
    full = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    width, height = full.size
    draw = ImageDraw.Draw(full)
    for i, (x1, y1, x2, y2) in enumerate(boxes):
        draw.rectangle([x1 * width, y1 * height, x2 * width, y2 * height], outline="red" if i == 0 else "orange", width=max(3, width // 300))
    full.thumbnail((1600, 1600))
    full.save(out_dir / f"{path.stem}_box.jpg", quality=90)
    crop = Image.open(io.BytesIO(prepare_image(path, vision.get("max_side", 1280), padded_region(box, 0.15)).data))
    crop.save(out_dir / f"{path.stem}_crop.jpg", quality=90)
    print(f"\nSaved: logs/vision/{path.stem}_box.jpg and logs/vision/{path.stem}_crop.jpg")


if __name__ == "__main__":
    main()
