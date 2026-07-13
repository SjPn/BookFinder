"""Run full DNA build until every catalog book is processed.

Anti-hang guarantees:
- short batches (--books-per-pass)
- skip known failures (--skip-failed)
- per-book timeout in build_dna (--max-book-seconds)
- supervisor kills stalled child processes (--stall-minutes)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.catalog import works_count
from bookfinder.dna_store import DNA_DIR, build_index, read_heartbeat, touch_heartbeat

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
        subprocess.run(["lms", "server", "start", "-p", "1234"], check=False, capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        log("WARN: lms CLI not found or slow; assuming LM Studio server is already running")

    for model_key in (
        "deepseek-coder-v2-lite-instruct",
        "text-embedding-nomic-embed-text-v1.5",
    ):
        try:
            subprocess.run(
                ["lms", "load", model_key, "-y"],
                check=False,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            log(f"WARN: could not preload {model_key}: {exc}")


def _heartbeat_age_sec() -> float | None:
    beat = read_heartbeat()
    if not beat or not beat.get("updated_at"):
        return None
    try:
        updated = datetime.fromisoformat(str(beat["updated_at"]))
        return (datetime.now(timezone.utc) - updated).total_seconds()
    except ValueError:
        return None


def run_build_pass(
    *,
    books_per_pass: int,
    skip_failed: bool,
    delay: float,
    max_book_seconds: int,
    stall_minutes: int,
) -> int:
    env = {
        **os.environ,
        "PYTHONPATH": "src",
        "PYTHONUNBUFFERED": "1",
        "LLM_BACKEND": "lmstudio",
        "LMSTUDIO_HOST": "http://127.0.0.1:1234",
        "LMSTUDIO_CHAT_MODEL": os.environ.get("LMSTUDIO_CHAT_MODEL") or "deepseek-coder-v2-lite-instruct",
        "LMSTUDIO_EMBED_MODEL": os.environ.get("LMSTUDIO_EMBED_MODEL") or "text-embedding-nomic-embed-text-v1.5",
        "LLM_TIMEOUT_SEC": str(min(90, max_book_seconds)),
    }
    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "scripts" / "build_dna.py"),
        "--delay",
        str(delay),
        "--reindex-every",
        "25",
        "--max-new",
        str(books_per_pass),
        "--max-book-seconds",
        str(max_book_seconds),
    ]
    if skip_failed:
        cmd.append("--skip-failed")

    log(f"starting pass: {' '.join(cmd)} | {progress_line()}")
    touch_heartbeat(note="pass_start", profiles_ok=count_ok_profiles())

    stall_limit = max(60, stall_minutes * 60)
    last_done = count_ok_profiles()
    last_progress_at = time.monotonic()

    with BUILD_LOG.open("a", encoding="utf-8") as handle:
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
        try:
            while proc.poll() is None:
                time.sleep(15)
                done = count_ok_profiles()
                beat_age = _heartbeat_age_sec()
                if done > last_done:
                    last_done = done
                    last_progress_at = time.monotonic()
                    line = progress_line()
                    log(line)
                    write_status(state="running", progress=line)
                elif time.monotonic() - last_progress_at >= stall_limit:
                    log(
                        f"STALL: no new profiles for {stall_minutes} min "
                        f"(heartbeat_age={beat_age}, killing pid={proc.pid})"
                    )
                    proc.kill()
                    proc.wait(timeout=15)
                    touch_heartbeat(note="stall_killed", profiles_ok=done)
                    return 124
                elif beat_age is not None and beat_age > stall_limit:
                    log(f"STALL: heartbeat stale {int(beat_age)}s (killing pid={proc.pid})")
                    proc.kill()
                    proc.wait(timeout=15)
                    touch_heartbeat(note="heartbeat_stale", profiles_ok=done)
                    return 124
        except KeyboardInterrupt:
            proc.kill()
            proc.wait(timeout=10)
            raise

    return int(proc.returncode or 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Supervised full DNA build with anti-hang watchdog")
    parser.add_argument("--books-per-pass", type=int, default=40, help="Stop each pass after N new profiles")
    parser.add_argument("--skip-failed", action="store_true", default=True)
    parser.add_argument("--no-skip-failed", action="store_false", dest="skip_failed")
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--max-book-seconds", type=int, default=120, help="Per-book LLM timeout")
    parser.add_argument("--stall-minutes", type=int, default=5, help="Kill pass if no progress this long")
    parser.add_argument("--skip-neighbors", action="store_true", default=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if LOCK.exists():
        try:
            old_pid = int(LOCK.read_text(encoding="utf-8").strip())
            log(f"removing stale lock from pid {old_pid}")
        except ValueError:
            pass
    LOCK.write_text(str(os.getpid()), encoding="utf-8")

    total = works_count()
    log(
        f"DNA full run started. catalog={total} "
        f"batch={args.books_per_pass} stall={args.stall_minutes}m book_timeout={args.max_book_seconds}s"
    )
    write_status(state="running")

    pass_no = 0
    try:
        while count_ok_profiles() < total:
            pass_no += 1
            before = count_ok_profiles()
            log(f"pass {pass_no}: {progress_line()}")
            write_status(state="running", pass_no=pass_no, progress=progress_line())

            ensure_lm_studio()
            code = run_build_pass(
                books_per_pass=args.books_per_pass,
                skip_failed=args.skip_failed,
                delay=args.delay,
                max_book_seconds=args.max_book_seconds,
                stall_minutes=args.stall_minutes,
            )
            build_index()

            after = count_ok_profiles()
            gained = after - before
            log(f"pass {pass_no} finished code={code} gained={gained} | {progress_line()}")
            write_status(
                state="running",
                pass_no=pass_no,
                progress=progress_line(),
                last_exit_code=code,
                last_pass_gained=gained,
            )

            if after >= total:
                break
            if gained <= 0 and code == 0:
                log("WARN: pass made no progress and queue may be exhausted; sleeping before retry")
            time.sleep(10)

        if not args.skip_neighbors:
            log("all books processed, building neighbors")
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "build_dna_neighbors.py"), "--reindex"],
                cwd=ROOT,
                env={**os.environ, "PYTHONPATH": "src"},
                check=False,
                timeout=3600,
            )
        build_index()
        write_status(state="completed", done=count_ok_profiles())
        log(f"COMPLETED | {progress_line()}")
    finally:
        if LOCK.exists():
            LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
