"""Run full DNA build until every catalog book is processed.

Keeps retrying on crashes, LM Studio restarts, and transient LLM errors.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.catalog import works_count
from bookfinder.dna_store import DNA_DIR, build_index

LOG = ROOT / "data" / "processed" / "dna_supervisor.log"
BUILD_LOG = ROOT / "data" / "processed" / "dna_build.log"
STATUS = ROOT / "data" / "processed" / "dna_full_status.json"
LOCK = ROOT / "data" / "processed" / "dna_build.lock"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def count_ok_profiles() -> int:
    return len(list(DNA_DIR.glob("*.json")))


def progress_line() -> str:
    total = works_count()
    done = count_ok_profiles()
    pct = (done / total * 100) if total else 0.0
    return f"обработано {done}/{total} ({pct:.2f}%)"


def write_status(**fields: object) -> None:
    payload = {
        "updated_at": utc_now(),
        "catalog_total": works_count(),
        "profiles_ok": count_ok_profiles(),
        **fields,
    }
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def log(message: str) -> None:
    line = f"[{utc_now()}] {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def ensure_lm_studio() -> None:
    try:
        subprocess.run(["lms", "server", "start", "-p", "1234"], check=False, capture_output=True, text=True)
    except FileNotFoundError:
        log("WARN: lms CLI not found; assuming LM Studio server is already running")

    for model_key, identifier in (
        ("qwen/qwen2.5-vl-7b", "qwen-chat"),
        ("text-embedding-nomic-embed-text-v1.5", "nomic-embed"),
    ):
        try:
            subprocess.run(
                ["lms", "load", model_key, "-y", "--identifier", identifier],
                check=False,
                capture_output=True,
                text=True,
                timeout=600,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            log(f"WARN: could not preload {identifier}: {exc}")


def run_build_pass() -> int:
    env = {
        **os.environ,
        "PYTHONPATH": "src",
        "PYTHONUNBUFFERED": "1",
        "LLM_BACKEND": "lmstudio",
        "LMSTUDIO_HOST": "http://127.0.0.1:1234",
        "LMSTUDIO_CHAT_MODEL": "qwen-chat",
        "LMSTUDIO_EMBED_MODEL": "nomic-embed",
    }
    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "scripts" / "build_dna.py"),
        "--delay",
        "0.1",
        "--reindex-every",
        "100",
    ]
    log(f"starting pass: {' '.join(cmd)} | {progress_line()}")

    stop = threading.Event()

    def poll_progress() -> None:
        while not stop.wait(60):
            line = progress_line()
            log(line)
            write_status(state="running", progress=line)

    watcher = threading.Thread(target=poll_progress, daemon=True)
    watcher.start()
    try:
        with BUILD_LOG.open("a", encoding="utf-8") as handle:
            completed = subprocess.run(cmd, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
    finally:
        stop.set()
        watcher.join(timeout=1)
    return int(completed.returncode)


def main() -> None:
    if LOCK.exists():
        try:
            old_pid = int(LOCK.read_text(encoding="utf-8").strip())
            log(f"removing stale lock from pid {old_pid}")
        except ValueError:
            pass
    LOCK.write_text(str(os.getpid()), encoding="utf-8")

    total = works_count()
    log(f"DNA full run started. catalog={total}")
    write_status(state="running")

    pass_no = 0
    try:
        while count_ok_profiles() < total:
            pass_no += 1
            done = count_ok_profiles()
            log(f"pass {pass_no}: {progress_line()}")
            write_status(state="running", pass_no=pass_no, progress=progress_line())

            ensure_lm_studio()
            code = run_build_pass()
            build_index()

            done = count_ok_profiles()
            log(f"pass {pass_no} finished code={code} | {progress_line()}")
            write_status(
                state="running",
                pass_no=pass_no,
                progress=progress_line(),
                last_exit_code=code,
            )

            if done >= total:
                break
            time.sleep(15)

        log("all books processed, building neighbors")
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_dna_neighbors.py"), "--reindex"],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": "src"},
            check=False,
        )
        build_index()
        write_status(state="completed", done=count_ok_profiles())
        log(f"COMPLETED | {progress_line()}")
    finally:
        if LOCK.exists():
            LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
