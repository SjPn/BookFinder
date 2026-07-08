"""Build book DNA profiles via local LLM (Ollama or LM Studio)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.book_dna import (
    ALL_AXES,
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
from bookfinder.dna_store import DNA_DIR, build_index, load_progress, profile_path, save_profile, save_progress, should_skip
from bookfinder.fb2_text import load_fb2_sample
from bookfinder.llm_client import create_llm_client
from bookfinder.ollama_client import OllamaError, extract_json_object
from bookfinder.reviews_store import get_reviews_for_work, work_ids_with_reviews

DATA = ROOT / "data" / "processed"
STORE = CatalogStore(DATA)


def count_profiles() -> int:
    return len(list(DNA_DIR.glob("*.json")))


def format_progress(
    *,
    catalog_total: int,
    pass_ok: int,
    pass_skip: int,
    pass_fail: int,
    queue_pos: int,
    queue_total: int,
) -> str:
    done = count_profiles()
    pct = (done / catalog_total * 100) if catalog_total else 0.0
    return (
        f"обработано {done}/{catalog_total} ({pct:.2f}%) | "
        f"очередь {queue_pos}/{queue_total} | "
        f"проход +{pass_ok} ok, {pass_skip} skip, {pass_fail} fail"
    )


def iter_work_ids(
    *,
    limit: int,
    only_fb2: bool,
    only_with_reviews: bool,
    work_id: str | None,
) -> list[str]:
    if work_id:
        return [work_id]

    if only_with_reviews:
        ids = work_ids_with_reviews(limit=limit or 0)
        if only_fb2:
            ensure_catalog_db(DATA)
            fb2_ids = set(STORE.list_work_ids(limit=0, only_fb2=True))
            ids = [work_id for work_id in ids if work_id in fb2_ids]
            if limit > 0:
                return ids[:limit]
        return ids

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


def clamp_axes(raw_axes: dict) -> dict[str, int]:
    clamped: dict[str, int] = {}
    for key in ALL_AXES:
        value = raw_axes.get(key, 5)
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = 5
        clamped[key] = max(1, min(10, number))
    return clamped


def analyze_work(
    client,
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
        axes=DNAAxes.model_validate(clamp_axes(payload.get("axes") or {})),
        labels=DNALabels.model_validate(payload.get("labels") or {}),
        themes=list(payload.get("themes") or []),
        ai_tagline=str(payload.get("ai_tagline") or "").strip(),
        ai_summary=str(payload.get("ai_summary") or "").strip(),
        reader_badge=str(payload.get("reader_badge") or "").strip(),
        ai_overview=list(payload.get("ai_overview") or []),
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


def _is_context_error(exc: Exception) -> bool:
    message = str(exc).casefold()
    return "400" in message or "context" in message or "too long" in message or "token" in message


def analyze_work_with_fallback(
    client,
    work_id: str,
    *,
    use_reviews: bool,
    use_text: bool,
) -> BookDNAProfile:
    attempts: list[tuple[bool, bool]] = []
    if use_text:
        attempts.append((use_reviews, True))
        attempts.append((use_reviews, False))
    else:
        attempts.append((use_reviews, False))
    if use_reviews and not use_text:
        attempts.append((False, False))

    last_error: Exception | None = None
    seen: set[tuple[bool, bool]] = set()
    for reviews_on, text_on in attempts:
        key = (reviews_on, text_on)
        if key in seen:
            continue
        seen.add(key)
        try:
            return analyze_work(client, work_id, use_reviews=reviews_on, use_text=text_on)
        except (OllamaError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            if not (_is_context_error(exc) or isinstance(exc, json.JSONDecodeError)):
                raise
    raise last_error or RuntimeError(f"Failed to analyze {work_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build book DNA profiles with local LLM")
    parser.add_argument("--limit", type=int, default=0, help="Max books to process (0 = all)")
    parser.add_argument("--work-id", default="", help="Process a single work id")
    parser.add_argument("--only-fb2", action="store_true", help="Only books with local FB2")
    parser.add_argument("--only-with-reviews", action="store_true", help="Only books with saved reviews")
    parser.add_argument("--force", action="store_true", help="Rebuild even if profile exists")
    parser.add_argument("--delay", type=float, default=0.0, help="Pause between books (seconds)")
    parser.add_argument("--backend", default="", help="ollama or lmstudio (default: LLM_BACKEND env)")
    parser.add_argument("--chat-model", default="")
    parser.add_argument("--embed-model", default="")
    parser.add_argument("--no-reviews", action="store_true")
    parser.add_argument("--no-text", action="store_true")
    parser.add_argument("--index-only", action="store_true", help="Rebuild dna_index.json only")
    parser.add_argument("--reindex-every", type=int, default=100, help="Rebuild dna_index.json every N successes (0=only at end)")
    args = parser.parse_args()

    if args.index_only:
        summary = build_index()
        print(json.dumps({"indexed": summary["count"]}, ensure_ascii=False))
        return

    work_ids = iter_work_ids(
        limit=args.limit,
        only_fb2=args.only_fb2,
        only_with_reviews=args.only_with_reviews,
        work_id=args.work_id or None,
    )
    if not work_ids:
        raise SystemExit("No works selected")

    progress = load_progress()
    ok = skip = fail = 0
    catalog_total = works_count()

    with create_llm_client(
        backend=args.backend or None,
        chat_model=args.chat_model or None,
        embed_model=args.embed_model or None,
    ) as client:
        client.ensure_models()
        print(
            f"LLM OK ({client.host}). Каталог: {catalog_total}. "
            f"Уже готово: {count_profiles()}. Очередь: {len(work_ids)}",
            flush=True,
        )

        for idx, work_id in enumerate(work_ids, start=1):
            if should_skip(work_id, force=args.force):
                skip += 1
                if skip == 1 or skip % 100 == 0:
                    print(format_progress(
                        catalog_total=catalog_total,
                        pass_ok=ok,
                        pass_skip=skip,
                        pass_fail=fail,
                        queue_pos=idx,
                        queue_total=len(work_ids),
                    ), flush=True)
                continue

            title = work_id
            try:
                work = get_work(work_id)
                if work:
                    title = str(work.get("title") or work_id)
                profile = analyze_work_with_fallback(
                    client,
                    work_id,
                    use_reviews=not args.no_reviews,
                    use_text=not args.no_text,
                )
                save_profile(profile)
                progress[work_id] = "ok"
                ok += 1
                progress_text = format_progress(
                    catalog_total=catalog_total,
                    pass_ok=ok,
                    pass_skip=skip,
                    pass_fail=fail,
                    queue_pos=idx,
                    queue_total=len(work_ids),
                )
                print(f"ok {title} | {progress_text}", flush=True)
            except (OllamaError, ValueError, json.JSONDecodeError) as exc:
                progress[work_id] = f"fail:{exc}"
                fail += 1
                progress_text = format_progress(
                    catalog_total=catalog_total,
                    pass_ok=ok,
                    pass_skip=skip,
                    pass_fail=fail,
                    queue_pos=idx,
                    queue_total=len(work_ids),
                )
                print(f"fail {title} | {progress_text}: {exc}", flush=True)

            if idx % 5 == 0:
                save_progress(progress)
            if args.reindex_every > 0 and ok > 0 and ok % args.reindex_every == 0:
                build_index()
                progress_text = format_progress(
                    catalog_total=catalog_total,
                    pass_ok=ok,
                    pass_skip=skip,
                    pass_fail=fail,
                    queue_pos=idx,
                    queue_total=len(work_ids),
                )
                print(f"reindexed | {progress_text}", flush=True)

            if args.delay > 0:
                time.sleep(args.delay)

    save_progress(progress)
    index = build_index()
    print(
        json.dumps(
            {
                "catalog_total": catalog_total,
                "profiles_total": count_profiles(),
                "processed": len(work_ids),
                "ok": ok,
                "skip": skip,
                "fail": fail,
                "indexed": index["count"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
