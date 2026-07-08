"""Check that local Ollama is ready for DNA pipeline (alias for check_llm.py)."""

from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("check_llm.py")), run_name="__main__")
