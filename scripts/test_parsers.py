import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bookfinder.parsers import fantlab, fantasy_worlds, livelib

raw = ROOT / "data" / "raw"

for t in (1, 2, 4):
    html = (raw / f"fantlab_type{t}.html").read_text(encoding="utf-8", errors="ignore")
    books = fantlab.parse_rating_page(html, work_type=t)
    print(f"type{t}: {len(books)} first={books[0].title if books else 'n/a'}")

html = (raw / "fantlab_rating.html").read_text(encoding="utf-8", errors="ignore")
books = fantlab.parse_rating_page(html, work_type=1)
print(f"rating.html: {len(books)}")

for name in ("fw_hyperion.html", "fw_book.html"):
    path = raw / name
    if path.exists():
        book = fantasy_worlds.parse_book_page(path.read_text(encoding="utf-8", errors="ignore"))
        print(f"{name}: {book.title} rating={book.rating} fl={fantasy_worlds.extract_fantlab_id(path.read_text(encoding='utf-8', errors='ignore'))}")

home = raw / "fw_home.html"
if home.exists():
    top = fantasy_worlds.parse_home_top(home.read_text(encoding="utf-8", errors="ignore"))
    print(f"fw_home: {len(top)}")
