"""Explicit health check for the configured real remote model."""

from __future__ import annotations

import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def main() -> int:
    from somni_graph_quiz.app.real_llm_check import run_real_llm_check

    result = run_real_llm_check()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if bool(result.get("success")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
