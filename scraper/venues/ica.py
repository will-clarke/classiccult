"""ICA - Institute of Contemporary Arts (The Mall, London).

Arthouse / repertory programming. The site runs on the Spektrix ticketing
platform, but - unlike many Spektrix venues - showtimes are server-rendered
straight into each film's HTML page (no API/iframe needed for listings).

The /films index lists the current programme as ``.item.films`` anchors. Each
film page carries:
  - a ``.head.show.films .title`` heading,
  - a ``.caption`` credits line (``<i>Title</i>, dir. ..., Country YYYY, NNN min. CERT``),
  - a ``.performance-list`` of ``.performance.future`` blocks (date / venue / time),
  - a page-level ``/book/<id>`` link (Spektrix basket; per-show booking isn't exposed).

robots.txt only disallows /views/, /open-records-generator/ and *-dev paths;
/films is fair game.
"""
from __future__ import annotations

import re
import time

from bs4 import BeautifulSoup

from .base import Film, Screening, get, parse_human_date, parse_time

VENUE_ID = "ica"
VENUE_NAME = "ICA"
VENUE_URL = "https://www.ica.art/films"
_BASE = "https://www.ica.art"

_ITEM_RE = re.compile(r'class="item films "><a href="(/films/[a-z0-9-]+)"')
_BOOK_RE = re.compile(r'location\.href="(/book/\d+)"')
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_RUNTIME_RE = re.compile(r"\b(\d{1,3})\s*min", re.I)
_CERT_RE = re.compile(r"\b(U|PG|12A|12|15|18|R18)\b")
_DIR_RE = re.compile(r"\bdir(?:ected by|\.)?\s*(.+)", re.I)


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip(" ,.;:")
    return text or None


def _parse_caption(caption: str) -> dict:
    """Parse the credits line into structured fields.

    Format is comma-separated and varies, e.g.:
      'Enzo, dir. R. Campillo and G. Marchand, France/Belgium/Italy 2025,
       French ... subtitles, 102 mins'
      'Boogie Nights, dir. Paul Thomas Anderson, USA 1997, 155 min. 18'
    Strategy: split on commas; identify the director segment, the segment
    carrying the year (-> country + year), and pull runtime / certificate
    from anywhere. Title (segment 0, the italic) is taken from the heading.
    """
    meta: dict = {}
    parts = [p.strip() for p in caption.split(",") if p.strip()]

    # year + country: the segment containing a 4-digit year
    for p in parts:
        ym = _YEAR_RE.search(p)
        if ym:
            meta["year"] = int(ym.group(0))
            country = _clean(p[: ym.start()])
            if country:
                meta["country"] = country
            break

    # runtime (anywhere)
    rm = _RUNTIME_RE.search(caption)
    if rm:
        meta["runtime"] = f"{rm.group(1)}mins"

    # director: the segment beginning with "dir"
    for p in parts:
        dm = _DIR_RE.match(p)
        if dm:
            director = _clean(dm.group(1))
            # a single-segment caption may glue the country onto the director;
            # drop a trailing year token if one slipped in.
            if director:
                director = _clean(_YEAR_RE.split(director)[0])
            meta["director"] = director
            break

    # certificate: a classification token in/after the runtime segment
    cert_zone = caption[rm.end():] if rm else caption
    cm = _CERT_RE.search(cert_zone)
    if cm:
        meta["certificate"] = cm.group(1)
    return meta


def _parse_screenings(soup: BeautifulSoup, booking_url: str | None) -> list[Screening]:
    screenings: list[Screening] = []
    for perf in soup.select(".performance-list .performance.future"):
        date_el = perf.select_one(".date")
        time_el = perf.select_one(".time")
        if not date_el or not time_el:
            continue
        # strip leading weekday ("Tue, 23 Jun 2026" -> parse_human_date handles
        # "23 Jun 2026"); base helper infers year if absent but here it's explicit.
        date_text = re.sub(r"^[A-Za-z]+,\s*", "", date_el.get_text(strip=True))
        date = _parse_explicit_date(date_text) or parse_human_date(date_text)
        if not date:
            continue
        parsed = parse_time(time_el.get_text())
        if not parsed:
            continue
        time_24, display = parsed
        venue_el = perf.select_one(".venue")
        formats = []
        venue_name = _clean(venue_el.get_text()) if venue_el else None
        if venue_name:
            formats.append(venue_name)
        screenings.append(Screening(
            venue=VENUE_ID,
            date=date,
            time=time_24,
            display_time=display,
            booking_url=booking_url,
            formats=formats,
        ))
    return screenings


_EXPLICIT_DATE_RE = re.compile(r"(\d{1,2})\s+([A-Za-z]{3,})\s+((?:19|20)\d{2})")
_MONTHS = {
    m: i for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"], start=1)
}


def _parse_explicit_date(text: str) -> str | None:
    """'23 Jun 2026' -> '2026-06-23' (the ICA always gives an explicit year)."""
    m = _EXPLICIT_DATE_RE.search(text)
    if not m:
        return None
    day = int(m.group(1))
    month = _MONTHS.get(m.group(2)[:3].lower())
    if not month:
        return None
    import datetime as dt
    try:
        return dt.date(int(m.group(3)), month, day).isoformat()
    except ValueError:
        return None


def _film_urls(html: str) -> list[str]:
    seen, urls = set(), []
    for m in _ITEM_RE.finditer(html):
        path = m.group(1)
        if path not in seen:
            seen.add(path)
            urls.append(_BASE + path)
    return urls


def scrape() -> list[Film]:
    import datetime as dt

    today = dt.date.today().isoformat()
    listing = get(VENUE_URL).text
    films: list[Film] = []

    for url in _film_urls(listing):
        try:
            page = get(url).text
        except Exception:
            continue
        time.sleep(0.3)
        soup = BeautifulSoup(page, "html.parser")

        title_el = soup.select_one(".head.show.films .title")
        title = _clean(title_el.get_text()) if title_el else None
        if not title:
            continue

        book_m = _BOOK_RE.search(page)
        booking_url = _BASE + book_m.group(1) if book_m else None

        screenings = _parse_screenings(soup, booking_url)
        screenings = [s for s in screenings if s.date >= today]
        if not screenings:
            continue

        # caption credits line
        meta: dict = {}
        for cap in soup.select(".caption"):
            if cap.find("i"):
                meta = _parse_caption(cap.get_text(" ", strip=True))
                break

        og_img = soup.find("meta", property="og:image")
        poster = og_img.get("content") if og_img else None

        synopsis = None
        cap_node = next((c for c in soup.select(".caption") if c.find("i")), None)
        if cap_node:
            sib = cap_node.find_parent("div")
            # the synopsis is a sibling div following the caption/book row
            for nxt in (cap_node.find_all_next("div", limit=8)):
                txt = _clean(nxt.get_text(" ", strip=True))
                if txt and len(txt) > 80 and "book tickets" not in txt.lower():
                    synopsis = txt
                    break

        films.append(Film(
            title=title,
            year=meta.get("year"),
            director=meta.get("director"),
            runtime=meta.get("runtime"),
            country=meta.get("country"),
            certificate=meta.get("certificate"),
            poster=poster,
            film_url=url,
            synopsis=synopsis[:600] if synopsis else None,
            screenings=screenings,
        ))

    return films
