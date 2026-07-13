"""Backfill tropes for existing DNA profiles (heuristic and/or local LLM)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.book_dna import (
    BookDNAProfile,
    build_tropes_prompt,
    derive_tropes_from_axes,
    embedding_text,
    utc_now_iso,
)
from bookfinder.catalog import get_work
from bookfinder.dna_store import DNA_DIR, build_index, profile_path, save_profile
from bookfinder.llm_client import create_llm_client
from bookfinder.ollama_client import OllamaError, extract_json_object


def needs_backfill(profile: BookDNAProfile) -> bool:
    return not profile.tropes


def apply_heuristic(profile: BookDNAProfile, genres: list[str] | None) -> list[str]:
    return derive_tropes_from_axes(profile.axes.model_dump(), genres)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill DNA tropes via heuristic and/or local LLM")
    parser.add_argument("--limit", type=int, default=0, help="Max profiles to update (0 = all missing)")
    parser.add_argument("--work-id", default="", help="Single work id")
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--backend", default="")
    parser.add_argument("--chat-model", default="")
    parser.add_argument("--embed-model", default="")
    parser.add_argument("--force", action="store_true", help="Rewrite even if tropes exist")
    parser.add_argument(
        "--heuristic-only",
        action="store_true",
        help="Fill tropes from axes/genres without calling the LLM",
    )
    parser.add_argument(
        "--no-embed",
        action="store_true",
        help="Skip re-embedding after trope update (faster heuristic pass)",
    )
    args = parser.parse_args()

    paths = sorted(DNA_DIR.glob("*.json"))
    if args.work_id:
        paths = [profile_path(args.work_id)]

    ok = skip = fail = 0
    client = None
    if not args.heuristic_only:
        client = create_llm_client(
            backend=args.backend or None,
            chat_model=args.chat_model or None,
            embed_model=args.embed_model or None,
        )
        client.__enter__()
        client.ensure_models()

    try:
        for path in paths:
            if args.limit > 0 and ok >= args.limit:
                break
            try:
                profile = BookDNAProfile.model_validate(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, ValueError):
                fail += 1
                continue

            if not args.force and not needs_backfill(profile):
                skip += 1
                continue

            work = get_work(profile.work_id) or {}
            genres = list(work.get("genres") or [])
            tropes: list[str] = []

            try:
                if args.heuristic_only or client is None:
                    tropes = apply_heuristic(profile, genres)
                else:
                    prompt = build_tropes_prompt(
                        title=profile.title or str(work.get("title") or ""),
                        authors=profile.authors or list(work.get("authors") or []),
                        genres=genres,
                        ai_summary=profile.ai_summary,
                        themes=profile.themes,
                        catalog_description=str(work.get("description") or ""),
                    )
                    raw = client.chat(
                        prompt,
                        system="Ты возвращаешь только JSON. tropes — только ключи из списка.",
                    )
                    payload = extract_json_object(raw)
                    tropes = list(payload.get("tropes") or [])
                    if not tropes:
                        tropes = apply_heuristic(profile, genres)

                if not tropes:
                    skip += 1
                    continue

                profile.tropes = BookDNAProfile.model_validate(
                    {
                        "work_id": profile.work_id,
                        "axes": profile.axes.model_dump(),
                        "tropes": tropes,
                    }
                ).tropes
                profile.updated_at = utc_now_iso()
                if client is not None and not args.no_embed:
                    profile.embedding = client.embed(embedding_text(profile))
                save_profile(profile)
                ok += 1
                print(f"ok {profile.title}: {', '.join(profile.tropes)}", flush=True)
            except (OllamaError, ValueError, json.JSONDecodeError) as exc:
                fail += 1
                print(f"fail {profile.work_id}: {exc}", flush=True)

            if args.delay > 0:
                time.sleep(args.delay)
    finally:
        if client is not None:
            client.__exit__(None, None, None)

    index = build_index()
    print(
        json.dumps({"ok": ok, "skip": skip, "fail": fail, "indexed": index["count"]}, ensure_ascii=False),
        flush=True,
    )


if __name__ == "__main__":
    main()
