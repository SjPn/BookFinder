"""Extract readable text samples from local FB2 archives."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

_FB2_DIR = Path(__file__).resolve().parents[2] / "data" / "books" / "fb2"
_TAG_RE = re.compile(r"<[^>]+>")


def fb2_path_for_fw_id(fw_id: str, base_dir: Path | None = None) -> Path:
    root = base_dir or _FB2_DIR
    return root / f"{fw_id}.fb2.zip"


def _strip_xml(xml_text: str) -> str:
    text = _TAG_RE.sub(" ", xml_text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _read_fb2_xml_from_zip(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path) as archive:
        fb2_names = [name for name in archive.namelist() if name.lower().endswith(".fb2")]
        if not fb2_names:
            raise ValueError(f"No .fb2 file inside {zip_path}")
        raw = archive.read(fb2_names[0])
    for encoding in ("utf-8", "cp1251", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _extract_body_text(xml_text: str) -> str:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return _strip_xml(xml_text)

    parts: list[str] = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag in {"p", "v", "subtitle", "text-author"} and element.text:
            parts.append(element.text.strip())
        if element.tail and element.tail.strip():
            parts.append(element.tail.strip())
    if parts:
        return re.sub(r"\s+", " ", " ".join(parts)).strip()
    return _strip_xml(xml_text)


def sample_text(text: str, max_chars: int = 10000) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    third = max_chars // 3
    middle_start = max(0, len(cleaned) // 2 - third // 2)
    return "\n...\n".join(
        [
            cleaned[:third],
            cleaned[middle_start : middle_start + third],
            cleaned[-third:],
        ]
    )


def load_fb2_sample(fw_id: str, *, max_chars: int = 10000, base_dir: Path | None = None) -> str:
    zip_path = fb2_path_for_fw_id(fw_id, base_dir=base_dir)
    if not zip_path.exists():
        return ""
    xml_text = _read_fb2_xml_from_zip(zip_path)
    body = _extract_body_text(xml_text)
    return sample_text(body, max_chars=max_chars)
