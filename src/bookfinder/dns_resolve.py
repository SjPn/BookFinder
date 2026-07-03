"""DNS helpers when local resolver poisons hosts (e.g. fantlab.ru -> 127.0.0.1)."""

from __future__ import annotations

import os
import socket
import subprocess
from functools import lru_cache
from urllib.parse import urlparse

PUBLIC_DNS = os.environ.get("BOOKFINDER_DNS", "8.8.8.8")

# Fallback IPs (refreshed via PUBLIC_DNS when poisoned).
HOST_FALLBACK_IP: dict[str, str] = {
    "fantlab.ru": "176.123.175.233",
    "api.fantlab.ru": "176.123.175.233",
    "www.kubikus.ru": "93.188.43.146",
    "kubikus.ru": "93.188.43.146",
    "bookmix.ru": "213.189.208.102",
    "www.bookmix.ru": "213.189.208.102",
}


@lru_cache(maxsize=128)
def resolve_via_public_dns(host: str) -> str | None:
    if host in HOST_FALLBACK_IP:
        return HOST_FALLBACK_IP[host]
    try:
        out = subprocess.run(
            ["nslookup", host, PUBLIC_DNS],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        addresses: list[str] = []
        for line in out.stdout.splitlines():
            if line.strip().lower().startswith("address:"):
                addr = line.split(":", 1)[1].strip()
                if addr != PUBLIC_DNS:
                    addresses.append(addr)
        return addresses[-1] if addresses else None
    except Exception:
        return HOST_FALLBACK_IP.get(host)


def local_ip(host: str) -> str | None:
    try:
        return socket.gethostbyname(host)
    except OSError:
        return None


def is_poisoned(host: str) -> bool:
    ip = local_ip(host)
    if not ip:
        return True
    return ip.startswith("127.") or ip in {"0.0.0.0", "::1"}


def prepare_request(url: str) -> tuple[str, dict[str, str], str | None]:
    """Return (url, extra_headers, sni_hostname) for HTTPS IP bypass."""
    parsed = urlparse(url)
    host = parsed.hostname
    if not host or not is_poisoned(host):
        return url, {}, None

    ip = resolve_via_public_dns(host)
    if not ip:
        return url, {}, None

    port = parsed.port
    netloc = f"{ip}:{port}" if port else ip
    bypass = parsed._replace(netloc=netloc).geturl()
    return bypass, {"Host": host}, host
