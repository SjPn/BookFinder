"""Backfill reader_badge and ai_overview for existing DNA profiles."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.book_dna import BookDNAProfile, build_overview_prompt, embedding_text, utc_now_iso
from bookfinder.catalog import get_work
from bookfinder.dna_store import DNA_DIR, build_index, load_profile, profile_path, save_profile
from bookfinder.llm_client import create_llm_client
from bookfinder.ollama_client import OllamaError, extract_json_object


def needs_backfill(profile: BookDNAProfile) -> bool:
    return not profile.ai_overview or not profile.reader_badge.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill DNA overview fields via local LLM")
    parser.add_argument("--limit", type=int, default=0, help="Max profiles to update (0 = all missing)")
    parser.add_argument("--work-id", default="", help="Single work id")
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--backend", default="")
    parser.add_argument("--chat-model", default="")
    parser.add_argument("--embed-model", default="")
    parser.add_argument("--force", action="store_true", help="Rewrite even if overview exists")
    args = parser.parse_args()

    paths = sorted(DNA_DIR.glob("*.json"))
    if args.work_id:
        paths = [profile_path(args.work_id)]

    ok = skip = fail = 0
    with create_llm_client(
        backend=args.backend or None,
        chat_model=args.chat_model or None,
        embed_model=args.embed_model or None,
    ) as client:
        client.ensure_models()
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
            prompt = build_overview_prompt(
                title=profile.title or str(work.get("title") or ""),
                authors=profile.authors or list(work.get("authors") or []),
                genres=list(work.get("genres") or []),
                ai_tagline=profile.ai_tagline,
                ai_summary=profile.ai_summary,
                themes=profile.themes,
                catalog_description=str(work.get("description") or ""),
            )
            try:
                raw = client.chat(
                    prompt,
                    system="Ты возвращаешь только JSON. Все текстовые поля — на русском.",
                )
                payload = extract_json_object(raw)
                profile.reader_badge = str(payload.get("reader_badge") or profile.reader_badge or "").strip()
                overview = payload.get("ai_overview") or profile.ai_overview
                profile.ai_overview = BookDNAProfile.model_validate(
                    {"work_id": profile.work_id, "axes": profile.axes.model_dump(), "ai_overview": overview}
                ).ai_overview
                profile.updated_at = utc_now_iso()
                profile.embedding = client.embed(embedding_text(profile))
                save_profile(profile)
                ok += 1
                print(f"ok {profile.title}", flush=True)
            except (OllamaError, ValueError, json.JSONDecodeError) as exc:
                fail += 1
                print(f"fail {profile.work_id}: {exc}", flush=True)

            if args.delay > 0:
                time.sleep(args.delay)

    index = build_index()
    print(
        json.dumps({"ok": ok, "skip": skip, "fail": fail, "indexed": index["count"]}, ensure_ascii=False),
        flush=True,
    )


if __name__ == "__main__":
    main()
