"""Unified local LLM client — Ollama or LM Studio."""

from __future__ import annotations

import os
from typing import Protocol

from bookfinder.lmstudio_client import LMStudioClient
from bookfinder.ollama_client import OllamaClient, OllamaError, extract_json_object

DEFAULT_BACKEND = "ollama"


class LLMClient(Protocol):
    host: str
    chat_model: str
    embed_model: str

    def chat(self, prompt: str, *, system: str = "", temperature: float = 0.2) -> str: ...

    def embed(self, text: str) -> list[float]: ...

    def ensure_models(self) -> None: ...

    def list_models(self) -> list[str]: ...

    def close(self) -> None: ...


def create_llm_client(
    *,
    backend: str | None = None,
    chat_model: str | None = None,
    embed_model: str | None = None,
) -> LLMClient:
    selected = (backend or os.environ.get("LLM_BACKEND") or DEFAULT_BACKEND).strip().casefold()
    if selected in {"lmstudio", "lm-studio", "openai"}:
        return LMStudioClient(chat_model=chat_model or None, embed_model=embed_model or None)
    if selected in {"ollama", ""}:
        return OllamaClient(chat_model=chat_model or None, embed_model=embed_model or None)
    raise OllamaError(f"Unknown LLM_BACKEND: {selected!r}. Use ollama or lmstudio.")


__all__ = ["LLMClient", "create_llm_client", "OllamaError", "extract_json_object"]
