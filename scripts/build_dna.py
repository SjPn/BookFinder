"""Build book DNA profiles via local Ollama."""

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
    DNALabels,
    DNAAxes,
    DNAReviewsSummary,
    DNASources,
    PROMPT_VERSION,
    build_dna_prompt,
    embedding_text,
    utc_now_iso,
)
from bookfinder.catalog import get_work, works_count
from bookfinder.catalog_db import CatalogStore, ensure_catalog_db
from bookfinder.dna_store import build_index, load_progress, profile_path, save_profile, save_progress, should_skip
from bookfinder.fb2_text import load_fb2_sample
from bookfinder.ollama_client import OllamaClient, OllamaError, extract_json_object
from bookfinder.reviews_store import get_reviews_for_work

DATA = ROOT / "data" / "processed"
STORE = CatalogStore(DATA)


def iter_work_ids(
    *,
    limit: int,
    only_fb2: bool,
    work_id: str | None,
) -> list[str]:
    if work_id:
        return [work_id]

    ensure_catalog_db(DATA)
    if not STORE.available():
        raise SystemExit("catalog.db not found. Run: python scripts/export_runtime_catalog.py")

    return STORE.list_work_ids(limit=limit, only_fb2=only_fb2)


def review_snippets(work_id: str, fw_id: str | None, limit: int = 8) -> list[str]:
    payload = get_reviews_for_work(work_id, limit=limit, fw_id=fw_id)
    snippets: list[str] = []
    for review in payload.get("reviews") or []:
        text = str(review.get("text") or "").strip()
        if not text:
            continue
        snippets.append(text[:280])
        if len(snippets) >= limit:
            break
    return snippets


def analyze_work(
    client: OllamaClient,
    work_id: str,
    *,
    use_reviews: bool,
    use_text: bool,
) -> BookDNAProfile:
    work = get_work(work_id)
    if not work:
        raise ValueError(f"Work not found: {work_id}")

    fw_id = None
    fw_info = work.get("fantasy_worlds") or {}
    if fw_info.get("id"):
        fw_id = str(fw_info["id"])

    catalog_description = str(work.get("description") or "").strip()
    reviews = review_snippets(work_id, fw_id) if use_reviews else []
    text_sample = load_fb2_sample(fw_id) if (use_text and fw_id) else ""

    prompt = build_dna_prompt(
        title=str(work.get("title") or ""),
        authors=list(work.get("authors") or []),
        genres=list(work.get("genres") or []),
        catalog_description=catalog_description,
        review_snippets=reviews,
        text_sample=text_sample,
    )

    raw = client.chat(
        prompt,
        system="Ты возвращаешь только JSON. Все текстовые поля — на русском.",
    )
    payload = extract_json_object(raw)

    profile = BookDNAProfile(
        work_id=work_id,
        title=str(work.get("title") or ""),
        authors=list(work.get("authors") or []),
        axes=DNAAxes.model_validate(payload.get("axes") or {}),
        labels=DNALabels.model_validate(payload.get("labels") or {}),
        themes=list(payload.get("themes") or []),
        ai_tagline=str(payload.get("ai_tagline") or "").strip(),
        ai_summary=str(payload.get("ai_summary") or "").strip(),
        reviews_summary=DNAReviewsSummary.model_validate(payload.get("reviews_summary") or {}),
        sources=DNASources(
            annotation=0.85 if catalog_description else 0.0,
            reviews=min(0.9, 0.35 + 0.08 * len(reviews)) if reviews else 0.0,
            text=0.9 if text_sample else 0.0,
        ),
        chat_model=client.chat_model,
        prompt_version=PROMPT_VERSION,
        updated_at=utc_now_iso(),
    )

    profile.embedding_model = client.embed_model
    profile.embedding = client.embed(embedding_text(profile))
    return profile


def main() -> None:
    parser = argparse.ArgumentParser(description="Build book DNA profiles with Ollama")
    parser.add_argument("--limit", type=int, default=0, help="Max books to process (0 = all)")
    parser.add_argument("--work-id", default="", help="Process a single work id")
    parser.add_argument("--only-fb2", action="store_true", help="Only books with local FB2")
    parser.add_argument("--force", action="store_true", help="Rebuild even if profile exists")
    parser.add_argument("--delay", type=float, default=0.0, help="Pause between books (seconds)")
    parser.add_argument("--chat-model", default="")
    parser.add_argument("--embed-model", default="")
    parser.add_argument("--no-reviews", action="store_true")
    parser.add_argument("--no-text", action="store_true")
    parser.add_argument("--index-only", action="store_true", help="Rebuild dna_index.json only")
    args = parser.parse_args()

    if args.index_only:
        summary = build_index()
        print(json.dumps({"indexed": summary["count"]}, ensure_ascii=False))
        return

    work_ids = iter_work_ids(
        limit=args.limit,
        only_fb2=args.only_fb2,
        work_id=args.work_id or None,
    )
    if not work_ids:
        raise SystemExit("No works selected")

    progress = load_progress()
    ok = skip = fail = 0

    with OllamaClient(
        chat_model=args.chat_model or None,
        embed_model=args.embed_model or None,
    ) as client:
        client.ensure_models()
        print(f"Ollama OK. Works in catalog: {works_count()}. Queue: {len(work_ids)}")

        for idx, work_id in enumerate(work_ids, start=1):
            if should_skip(work_id, force=args.force):
                skip += 1
                continue

            title = work_id
            try:
                work = get_work(work_id)
                if work:
                    title = str(work.get("title") or work_id)
                profile = analyze_work(
                    client,
                    work_id,
                    use_reviews=not args.no_reviews,
                    use_text=not args.no_text,
                )
                save_profile(profile)
                progress[work_id] = "ok"
                ok += 1
                print(f"[{idx}/{len(work_ids)}] ok {title} -> {profile_path(work_id).name}")
            except (OllamaError, ValueError, json.JSONDecodeError) as exc:
                progress[work_id] = f"fail:{exc}"
                fail += 1
                print(f"[{idx}/{len(work_ids)}] fail {title}: {exc}")

            if idx % 10 == 0:
                save_progress(progress)

            if args.delay > 0:
                time.sleep(args.delay)

    save_progress(progress)
    index = build_index()
    print(
        json.dumps(
            {
                "processed": len(work_ids),
                "ok": ok,
                "skip": skip,
                "fail": fail,
                "indexed": index["count"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
