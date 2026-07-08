"""HTTP client for LM Studio (OpenAI-compatible API)."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from bookfinder.ollama_client import OllamaError, extract_json_object

DEFAULT_HOST = "http://127.0.0.1:1234"
DEFAULT_CHAT_MODEL = "qwen2.5-7b-instruct"
DEFAULT_EMBED_MODEL = "nomic-embed-text"


class LMStudioClient:
    def __init__(
        self,
        host: str | None = None,
        chat_model: str | None = None,
        embed_model: str | None = None,
        timeout_sec: float = 180.0,
        max_retries: int = 3,
    ) -> None:
        base = (host or os.environ.get("LMSTUDIO_HOST") or DEFAULT_HOST).rstrip("/")
        self.host = base if base.endswith("/v1") else f"{base}/v1"
        self.chat_model = chat_model or os.environ.get("LMSTUDIO_CHAT_MODEL") or DEFAULT_CHAT_MODEL
        self.embed_model = embed_model or os.environ.get("LMSTUDIO_EMBED_MODEL") or DEFAULT_EMBED_MODEL
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self._client = httpx.Client(timeout=self.timeout_sec)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> LMStudioClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def list_models(self) -> list[str]:
        response = self._client.get(f"{self.host}/models")
        response.raise_for_status()
        payload = response.json()
        models: list[str] = []
        for item in payload.get("data") or []:
            model_id = item.get("id")
            if model_id:
                models.append(str(model_id))
        return models

    def ensure_models(self) -> None:
        available = set(self.list_models())
        if not available:
            raise OllamaError(
                "LM Studio returned no models. Load chat + embedding models in LM Studio "
                "(Developer → Local Server → Start Server)."
            )
        missing: list[str] = []
        for model in (self.chat_model, self.embed_model):
            if model not in available and not any(model in name for name in available):
                missing.append(model)
        if missing:
            raise OllamaError(
                f"Missing LM Studio models: {', '.join(missing)}. "
                f"Loaded: {', '.join(sorted(available)[:8])}"
            )

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self._client.post(f"{self.host}{path}", json=payload)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(min(2**attempt, 8))
        raise OllamaError(f"LM Studio request failed: {last_error}") from last_error

    def chat(self, prompt: str, *, system: str = "", temperature: float = 0.2) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.chat_model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        data = self._post_json("/chat/completions", payload)
        choices = data.get("choices") or []
        if not choices:
            raise OllamaError("Empty LM Studio chat response")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not content:
            raise OllamaError("Empty LM Studio chat response")
        return str(content)

    def embed(self, text: str) -> list[float]:
        payload = {"model": self.embed_model, "input": text}
        data = self._post_json("/embeddings", payload)
        rows = data.get("data") or []
        if not rows:
            raise OllamaError("Empty LM Studio embedding response")
        embedding = rows[0].get("embedding")
        if not isinstance(embedding, list):
            raise OllamaError("Empty LM Studio embedding response")
        return [float(x) for x in embedding]


__all__ = ["LMStudioClient", "extract_json_object", "OllamaError"]
