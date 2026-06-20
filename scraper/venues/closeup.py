"""Close-Up Film Centre (Shoreditch, London) - arthouse / repertory.

The site runs on Concrete5 (ccm) and is **server-rendered HTML** - no JSON-LD,
no JSON API. The /film_programmes/ index lists current programmes as
``div.inner_block_3`` blocks, each with an ``h2 > a`` linking to a detail page
under ``/film_programmes/<year>/.../<slug>/``. Each detail page carries:
  - an ``h1`` / ``<title>`` heading (prefixed with a date range, e.g.
    "3 - 25 June 2026: Good Time"),
  - a credits ``<p>`` of the form "Director, YYYY, NN min",
  - a ``table#addform`` "Calendar" with one ``tr#row`` per showtime; cells are
    Title / Date ("Thursday 25.06.26", DD.MM.YY) / Time ("8:15 pm") / Book
    (a TicketSource link, or no link when a show is sold out / unbookable).

robots.txt allows /film_programmes/ (only Concrete5 system dirs are disallowed).

IMPORTANT - Cloudflare: this host sits behind a Cloudflare *managed* JS
challenge that returns HTTP 403 + an "Enable JavaScript" interstitial to plain
HTTP clients (verified with both our identifying UA and a desktop-browser UA).
``requests`` cannot solve a managed challenge, so fetches below will normally
403. The parsing logic is validated against the live DOM and will work as soon
as the bytes are reachable (e.g. via a headless-browser fetch layer). On a
challenge / network failure we degrade to an empty list rather than crash.
"""
from __future__ import annotations

import datetime as dt
import re
import time

import requests
from bs4 import BeautifulSoup

from .base import Film, Screening, parse_time

VENUE_ID = "closeup"
VENUE_NAME = "Close-Up"
VENUE_URL = "https://www.closeupfilmcentre.com/film_programmes/"
_BASE = "https://www.closeupfilmcentre.com"

# A desktop-browser UA gets us past trivial UA filters; it does NOT solve a
# Cloudflare managed JS challenge (see module docstring).
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 "
        "repertory-london-bot/1.0 (+personal hobby film-listings aggregator)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

_session = requests.Session()
_session.headers.update(_HEADERS)

_FILM_HREF_RE = re.compile(r"/film_programmes/\d{4}/")
# "Thursday 25.06.26" / "25.06.26" / "25.06.2026"  -> DD.MM.YY[YY]
_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})")
# credits line: "Josh & Benny Safdie, 2017, 99 min"
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_RUNTIME_RE = re.compile(r"(\d+)\s*min", re.I)
# leading "5 - 23 June 2026: " date-range prefix on titles
_TITLE_DATE_PREFIX_RE = re.compile(
    r"^\s*\d{1,2}\s*[-–]?\s*(?:\d{1,2}\s+)?[A-Za-z]+\s+\d{4}\s*:\s*", )


def _get(url: str) -> requests.Response | None:
    try:
        resp = _session.get(url, timeout=30)
        resp.raise_for_status()
    except Exception:
        return None
    if "Just a moment" in resp.text or "cf_chl" in resp.text:
        return None  # Cloudflare interstitial, not real content
    return resp


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _clean_title(raw: str | None) -> str | None:
    raw = _clean(raw)
    if not raw:
        return None
    # strip "CLOSE-UP | " page-title prefix and any leading date range
    raw = re.sub(r"^CLOSE-UP\s*\|\s*", "", raw, flags=re.I)
    raw = _TITLE_DATE_PREFIX_RE.sub("", raw)
    return _clean(raw)


def _parse_date(text: str, today: dt.date) -> str | None:
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if year < 100:
        year += 2000
    try:
        return dt.date(year, month, day).isoformat()
    except ValueError:
        return None


def _parse_meta(soup: BeautifulSoup) -> dict:
    """Pull director / year / runtime from the credits <p> (best-effort).

    Shape: ``<strong>Title<br></strong>Director, YYYY, NN min``. The title sits
    in the leading <strong>; the credits ("Director, YYYY, NN min") follow it.
    """
    meta: dict = {}
    for p in soup.find_all("p"):
        full = _clean(p.get_text(" "))
        if not full or len(full) > 200:
            continue
        if not (_YEAR_RE.search(full) and _RUNTIME_RE.search(full)):
            continue
        ym = _YEAR_RE.search(full)
        meta["year"] = int(ym.group(0))
        rt = _RUNTIME_RE.search(full)
        meta["runtime"] = f"{rt.group(1)}mins"
        # Drop the leading <strong> (the title) so only the credits remain.
        credits_text = full
        strong = p.find("strong")
        if strong:
            strong.extract()
            credits_text = _clean(p.get_text(" ")) or full
        # director = everything before the year in the credits line
        before_year = credits_text[: credits_text.find(ym.group(0))]
        director = _clean(before_year.rstrip(" ,"))
        if director:
            meta["director"] = director
        break
    return meta


def _parse_screenings(soup: BeautifulSoup, today: dt.date) -> list[Screening]:
    screenings: list[Screening] = []
    table = soup.find("table", id="addform")
    if not table:
        return screenings
    for row in table.find_all("tr", id="row"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        date_iso = _parse_date(cells[1].get_text(" "), today)
        if not date_iso or date_iso < today.isoformat():
            continue  # past or unparseable
        parsed = parse_time(cells[2].get_text(" "))
        if not parsed:
            continue
        time_24, display = parsed
        book_a = cells[-1].find("a", href=True) if cells else None
        booking_url = book_a["href"] if book_a else None
        sold_out = booking_url is None
        screenings.append(Screening(
            venue=VENUE_ID,
            date=date_iso,
            time=time_24,
            display_time=display,
            booking_url=booking_url,
            formats=[],
            sold_out=sold_out,
        ))
    return screenings


def _abs(href: str) -> str:
    return _BASE + href if href.startswith("/") else href


def _parse_listing(listing_html: str) -> tuple[list[str], dict[str, str]]:
    """Return (ordered film URLs, {url: poster}). Posters only live here."""
    soup = BeautifulSoup(listing_html, "html.parser")
    seen, urls = set(), []
    posters: dict[str, str] = {}
    for block in soup.select("div.inner_block_3"):
        a = block.select_one("a[href]")
        if not a or not _FILM_HREF_RE.search(a["href"]):
            continue
        url = _abs(a["href"])
        if url not in seen:
            seen.add(url)
            urls.append(url)
            img = block.select_one("img[src]")
            if img:
                posters[url] = _abs(img["src"])
    # fallback: any qualifying link, in case the block markup shifts
    for a in soup.select("a[href]"):
        if not _FILM_HREF_RE.search(a["href"]):
            continue
        url = _abs(a["href"])
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls, posters


def scrape() -> list[Film]:
    today = dt.date.today()
    listing = _get(VENUE_URL)
    if listing is None:
        return []  # blocked by Cloudflare managed challenge or unreachable

    urls, posters = _parse_listing(listing.text)

    films: list[Film] = []
    for url in urls:
        page = _get(url)
        time.sleep(0.3)
        if page is None:
            continue
        soup = BeautifulSoup(page.text, "html.parser")

        h1 = soup.find("h1")
        raw_title = (h1.get_text() if h1 else None) or (
            soup.title.get_text() if soup.title else None)
        title = _clean_title(raw_title)
        if not title:
            continue

        screenings = _parse_screenings(soup, today)
        if not screenings:
            continue  # no upcoming showtimes

        meta = _parse_meta(soup)

        # Synopsis = first sizeable <p> that isn't the credits line.
        synopsis = None
        for p in soup.find_all("p"):
            t = _clean(p.get_text(" "))
            if not t or len(t) <= 80:
                continue
            if _YEAR_RE.search(t) and _RUNTIME_RE.search(t):
                continue  # credits paragraph
            synopsis = t
            break

        films.append(Film(
            title=title,
            year=meta.get("year"),
            director=meta.get("director"),
            runtime=meta.get("runtime"),
            country=meta.get("country"),
            certificate=meta.get("certificate"),
            poster=posters.get(url),
            film_url=url,
            synopsis=synopsis[:600] if synopsis else None,
            screenings=screenings,
        ))
    return films
