"""Run the vision test set. Kept for the commands used in earlier runs; see run_eval_set.py.

    python scripts/run_vision_set.py --fast       (the same as run_eval_set.py --set vision --fast)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_eval_set import main  # noqa: E402

if __name__ == "__main__":
    if "--set" not in sys.argv:
        sys.argv[1:1] = ["--set", "vision"]
    main()
