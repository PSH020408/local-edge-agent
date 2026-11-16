"""Speed check on its own: is this Mac as fast as it normally is? (agent/device/speed_check.py)

    python scripts/speed_check.py

A 100-token generation with qwen3:14b, compared with the normal speed for the current energy mode; when
it is far below, the performance diagnosis runs and its findings are printed. Test-set runs
(scripts/run_eval_set.py) do this before they start.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.device.speed_check import before_long_run  # noqa: E402


def main() -> None:
    cfg = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))
    result = before_long_run(cfg["llm"]["host"])
    print(f"{result.verdict}: {result.message}")
    if result.load_seconds and result.load_seconds > 1:
        print(f"(model load {result.load_seconds:.1f} s before the check)")


if __name__ == "__main__":
    main()
