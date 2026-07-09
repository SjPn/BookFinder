"""HTTP client for local Ollama (chat + embeddings)."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import httpx

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_CHAT_MODEL = "qwen2.5:7b"
DEFAULT_EMBED_MODEL = "nomic-embed-text"


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(
        self,
        host: str | None = None,
        chat_model: str | None = None,
        embed_model: str | None = None,
        timeout_sec: float = 90.0,
        max_retries: int = 2,
    ) -> None:
        self.host = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
        self.chat_model = chat_model or os.environ.get("OLLAMA_CHAT_MODEL") or DEFAULT_CHAT_MODEL
        self.embed_model = embed_model or os.environ.get("OLLAMA_EMBED_MODEL") or DEFAULT_EMBED_MODEL
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self._client = httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=timeout_sec, write=30.0, pool=10.0)
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OllamaClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def ping(self) -> dict[str, Any]:
        response = self._client.get(f"{self.host}/api/tags")
        response.raise_for_status()
        return response.json()

    def list_models(self) -> list[str]:
        payload = self.ping()
        return [item.get("name", "") for item in payload.get("models", []) if item.get("name")]

    def ensure_models(self) -> None:
        available = set(self.list_models())
        missing = [model for model in (self.chat_model, self.embed_model) if model not in available]
        if missing:
            raise OllamaError(
                f"Missing Ollama models: {', '.join(missing)}. Run: ollama pull {' '.join(missing)}"
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
        raise OllamaError(f"Ollama request failed: {last_error}") from last_error

    def chat(self, prompt: str, *, system: str = "", temperature: float = 0.2) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.chat_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        data = self._post_json("/api/chat", payload)
        message = data.get("message") or {}
        content = message.get("content")
        if not content:
            raise OllamaError("Empty Ollama chat response")
        return str(content)

    def embed(self, text: str) -> list[float]:
        payload = {"model": self.embed_model, "input": text}
        data = self._post_json("/api/embed", payload)
        embeddings = data.get("embeddings")
        if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
            return [float(x) for x in embeddings[0]]
        embedding = data.get("embedding")
        if isinstance(embedding, list):
            return [float(x) for x in embedding]
        raise OllamaError("Empty Ollama embedding response")


_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def extract_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    block = _JSON_BLOCK.search(raw)
    if block:
        raw = block.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise OllamaError("Model response does not contain JSON object")
    return json.loads(raw[start : end + 1])
