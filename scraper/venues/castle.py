"""The Castle Cinema (Homerton, Hackney).

Exposes clean schema.org ScreeningEvent JSON-LD on each /programme/ page
(startDate, duration, workPresented). The /listings/ index gives the set of
current programmes; we fetch each and read its structured data - a different,
more robust approach than HTML scraping.
"""
from __future__ import annotations

import re
import time

from bs4 import BeautifulSoup

from .base import Film, Screening, get

VENUE_ID = "castle"
VENUE_NAME = "The Castle Cinema"
VENUE_URL = "https://thecastlecinema.com/listings/"
_BASE = "https://thecastlecinema.com"

_PROG_RE = re.compile(r"/programme/(\d+)/([a-z0-9-]+)/")
_YEAR_IN_NAME = re.compile(r"\((19|20)\d{2}\)")
_YEAR_TRAILING = re.compile(r"-((?:19|20)\d{2})$")
_PRESENTS = re.compile(r"^.{0,45}?\bpresents?\b:?\s*", re.I)
_DURATION = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?")


def _clean_title(name: str) -> tuple[str, int | None]:
    """'Violet Hour presents: Mulholland Dr. (2001)' -> ('Mulholland Dr.', 2001)."""
    year = None
    ym = _YEAR_IN_NAME.search(name)
    if ym:
        year = int(ym.group(0).strip("()"))
        name = _YEAR_IN_NAME.sub("", name)
    name = _PRESENTS.sub("", name)
    return re.sub(r"\s+", " ", name).strip(" :-"), year


def _runtime(iso: str | None) -> str | None:
    if not iso:
        return None
    m = _DURATION.fullmatch(iso)
    if not m:
        return None
    h, mins = int(m.group(1) or 0), int(m.group(2) or 0)
    total = h * 60 + mins
    return f"{total}mins" if total else None


def _programme_urls(html: str) -> list[str]:
    seen, urls = set(), []
    for m in _PROG_RE.finditer(html):
        path = m.group(0)
        if path not in seen:
            seen.add(path)
            urls.append(_BASE + path)
    return urls


def scrape() -> list[Film]:
    import json

    listing = get(VENUE_URL).text
    by_title: dict[str, Film] = {}

    for url in _programme_urls(listing):
        slug_m = _PROG_RE.search(url)
        slug = slug_m.group(2) if slug_m else ""
        try:
            page = get(url).text
        except Exception:
            continue
        soup = BeautifulSoup(page, "html.parser")
        events = []
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
            except Exception:
                continue
            for it in data if isinstance(data, list) else [data]:
                if isinstance(it, dict) and it.get("@type") == "ScreeningEvent":
                    events.append(it)
        if not events:
            continue

        raw_name = events[0].get("name") or events[0].get("workPresented", {}).get("name") or slug
        title, year = _clean_title(raw_name)
        if year is None:
            tm = _YEAR_TRAILING.search(slug)
            if tm:
                year = int(tm.group(1))
        runtime = _runtime(events[0].get("duration"))

        film = by_title.get(title)
        if not film:
            film = Film(title=title, year=year, runtime=runtime, film_url=url)
            by_title[title] = film

        for ev in events:
            start = ev.get("startDate") or ""
            m = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})", start)
            if not m:
                continue
            date, hh, mm = m.group(1), int(m.group(2)), m.group(3)
            ampm = "am" if hh < 12 else "pm"
            h12 = hh % 12 or 12
            disp = f"{h12}:{mm} {ampm}"
            film.screenings.append(Screening(
                venue=VENUE_ID,
                date=date,
                time=f"{hh:02d}:{mm}",
                display_time=disp,
                booking_url=ev.get("url"),
            ))
        time.sleep(0.3)  # be polite between page fetches

    return [f for f in by_title.values() if f.screenings]
