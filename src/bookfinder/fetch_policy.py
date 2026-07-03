"""Per-host fetch policies and circuit breaker state."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "data" / "processed" / "fetch_circuit.json"


@dataclass(frozen=True)
class HostPolicy:
    min_delay: float
    max_delay: float
    max_retries: int
    warmup_url: str | None
    default_referer: str | None
    connect_timeout: float = 45.0
    read_timeout: float = 180.0
    circuit_threshold: int = 8
    circuit_pause_sec: float = 300.0


POLICIES: dict[str, HostPolicy] = {
    "fantasy-worlds.net": HostPolicy(
        min_delay=0.7,
        max_delay=2.5,
        max_retries=8,
        warmup_url="https://fantasy-worlds.net/lib/",
        default_referer="https://fantasy-worlds.net/lib/",
        connect_timeout=30.0,
        read_timeout=120.0,
    ),
    "api.fantlab.ru": HostPolicy(
        min_delay=0.35,
        max_delay=1.8,
        max_retries=4,
        warmup_url="https://fantlab.ru/",
        default_referer="https://fantlab.ru/",
        connect_timeout=20.0,
        read_timeout=45.0,
        circuit_threshold=5,
        circuit_pause_sec=120.0,
    ),
    "fantlab.ru": HostPolicy(
        min_delay=0.5,
        max_delay=2.0,
        max_retries=10,
        warmup_url="https://fantlab.ru/",
        default_referer="https://fantlab.ru/",
        connect_timeout=60.0,
        read_timeout=120.0,
    ),
    "www.livelib.ru": HostPolicy(
        min_delay=4.0,
        max_delay=14.0,
        max_retries=4,
        warmup_url="https://www.livelib.ru/",
        default_referer="https://www.livelib.ru/",
        connect_timeout=45.0,
        read_timeout=120.0,
        circuit_threshold=3,
        circuit_pause_sec=600.0,
    ),
    "livelib.ru": HostPolicy(
        min_delay=4.0,
        max_delay=14.0,
        max_retries=4,
        warmup_url="https://www.livelib.ru/",
        default_referer="https://www.livelib.ru/",
        connect_timeout=45.0,
        read_timeout=120.0,
        circuit_threshold=3,
        circuit_pause_sec=600.0,
    ),
    "bookmix.ru": HostPolicy(
        min_delay=2.0,
        max_delay=6.0,
        max_retries=5,
        warmup_url="https://bookmix.ru/",
        default_referer="https://bookmix.ru/",
        connect_timeout=30.0,
        read_timeout=90.0,
    ),
    "www.bookmix.ru": HostPolicy(
        min_delay=2.0,
        max_delay=6.0,
        max_retries=5,
        warmup_url="https://bookmix.ru/",
        default_referer="https://bookmix.ru/",
        connect_timeout=30.0,
        read_timeout=90.0,
    ),
    "kubikus.ru": HostPolicy(
        min_delay=1.0,
        max_delay=3.0,
        max_retries=6,
        warmup_url="http://www.kubikus.ru/",
        default_referer="http://www.kubikus.ru/",
        connect_timeout=25.0,
        read_timeout=60.0,
    ),
    "www.kubikus.ru": HostPolicy(
        min_delay=1.0,
        max_delay=3.0,
        max_retries=6,
        warmup_url="http://www.kubikus.ru/",
        default_referer="http://www.kubikus.ru/",
        connect_timeout=25.0,
        read_timeout=60.0,
    ),
    "readrate.com": HostPolicy(
        min_delay=1.0,
        max_delay=3.0,
        max_retries=6,
        warmup_url="https://readrate.com/rus/",
        default_referer="https://readrate.com/rus/",
    ),
}

DEFAULT_POLICY = HostPolicy(
    min_delay=1.0,
    max_delay=4.0,
    max_retries=6,
    warmup_url=None,
    default_referer=None,
)


def host_key(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        return host
    return host


def policy_for(url: str) -> HostPolicy:
    key = host_key(url)
    if key in POLICIES:
        return POLICIES[key]
    bare = key.removeprefix("www.")
    for name, pol in POLICIES.items():
        if name.removeprefix("www.") == bare:
            return pol
    return DEFAULT_POLICY


class CircuitBreaker:
    def __init__(self, path: Path = STATE_PATH) -> None:
        self.path = path
        self._state: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            self._state = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self._state = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")

    def is_open(self, url: str) -> bool:
        key = host_key(url)
        entry = self._state.get(key, {})
        until = entry.get("open_until")
        if until and time.time() < until:
            return True
        if until and time.time() >= until:
            self._state[key] = {"failures": 0, "open_until": None}
            self._save()
        return False

    def pause_remaining(self, url: str) -> float:
        key = host_key(url)
        until = self._state.get(key, {}).get("open_until")
        if not until:
            return 0.0
        return max(0.0, until - time.time())

    def record_success(self, url: str) -> None:
        key = host_key(url)
        self._state[key] = {"failures": 0, "open_until": None}
        self._save()

    def record_failure(self, url: str) -> None:
        key = host_key(url)
        pol = policy_for(url)
        entry = self._state.get(key, {"failures": 0, "open_until": None})
        failures = int(entry.get("failures") or 0) + 1
        open_until = entry.get("open_until")
        if failures >= pol.circuit_threshold:
            open_until = time.time() + pol.circuit_pause_sec
            failures = 0
        self._state[key] = {"failures": failures, "open_until": open_until}
        self._save()
