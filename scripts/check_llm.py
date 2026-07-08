"""Check that local LLM backend is ready for DNA pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.llm_client import create_llm_client
from bookfinder.ollama_client import OllamaError


def main() -> None:
    with create_llm_client() as client:
        try:
            models = client.list_models()
            client.ensure_models()
            embed = client.embed("тестовая строка для эмбеддинга")
            chat = client.chat("Ответь одним словом: OK", temperature=0.0)
        except OllamaError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
            raise SystemExit(1) from exc

    print(
        json.dumps(
            {
                "ok": True,
                "host": client.host,
                "chat_model": client.chat_model,
                "embed_model": client.embed_model,
                "models": models,
                "embed_dim": len(embed),
                "chat_sample": chat.strip()[:40],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
