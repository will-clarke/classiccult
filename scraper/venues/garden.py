"""The Garden Cinema (Holborn / Covent Garden).

The Garden runs its ticketing on Savoy Systems (booking links point at
bookings.thegardencinema.co.uk/TheGardenCinema.dll/...), but - unlike Phoenix
and Rio - its public site is a bespoke WordPress build that renders showtimes
in its own HTML rather than exposing the Savoy ``var Events`` JSON listing. So
this venue is scraped from the WordPress film pages directly, not via the
shared savoy helper.

The homepage links every current film at /film/<slug>/. Each film page carries
a stats line (directors, country, year, runtime), a BBFC rating, a synopsis,
and a list of dated screening panels with booking links. robots.txt returns a
404 (no rules), so the film pages are fair game.
"""
from __future__ import annotations

import datetime as dt
import html as _html
import re
import time

from bs4 import BeautifulSoup

from .base import Film, Screening, get, parse_time

VENUE_ID = "garden"
VENUE_NAME = "The Garden Cinema"
VENUE_URL = "https://www.thegardencinema.co.uk/"
_FILM_RE = re.compile(r"https://www\.thegardencinema\.co\.uk/film/[a-z0-9-]+/")

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
# A film page title is "<Title> (<year>) <CERT>" or "<Title> <CERT>".
_TITLE_YEAR_RE = re.compile(r"\s*\((19|20)\d{2}\)\s*")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_RUNTIME_RE = re.compile(r"\b(\d{1,3})\s*m(?:in)?s?\b", re.I)


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", _html.unescape(text)).strip()
    return text or None


def _parse_abbrev_date(text: str, today: dt.date) -> str | None:
    """'Sat 08 Aug' -> ISO date, inferring the year (handles Dec->Jan rollover)."""
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})", text)
    if not m:
        return None
    day = int(m.group(1))
    month = _MONTHS.get(m.group(2).lower())
    if not month:
        return None
    for year in (today.year, today.year + 1, today.year - 1):
        try:
            cand = dt.date(year, month, day)
        except ValueError:
            continue
        if -14 <= (cand - today).days <= 330:
            return cand.isoformat()
    return None


def _film_urls(homepage_html: str) -> list[str]:
    seen, urls = set(), []
    for url in _FILM_RE.findall(homepage_html):
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _parse_meta(soup) -> dict:
    """Read directors / country / year / runtime from the stats line.

    Stats tail looks like: 'George Cukor, USA, 1949, 101m.' (an optional
    'Part of <season>' prefix sits before it inside the same block).
    """
    meta: dict = {}
    stats = soup.select_one(".film-detail__film__stats")
    if stats:
        # The free-text line is the last non-empty line of the block.
        lines = [ln.strip() for ln in stats.get_text("\n").split("\n") if ln.strip()]
        tail = lines[-1] if lines else ""
        ym = _YEAR_RE.search(tail)
        if ym:
            meta["year"] = int(ym.group(0))
        rm = _RUNTIME_RE.search(tail)
        if rm:
            meta["runtime"] = f"{rm.group(1)}mins"
        # Split into comma parts; the year part anchors the layout:
        # everything before it (minus the last comma part = country) is directors.
        parts = [p.strip() for p in tail.split(",") if p.strip()]
        year_idx = next((i for i, p in enumerate(parts)
                         if _YEAR_RE.fullmatch(p.strip())), None)
        if year_idx is not None and year_idx >= 1:
            meta["country"] = _clean(parts[year_idx - 1])
            directors = parts[:year_idx - 1]
            if directors:
                meta["director"] = _clean(", ".join(directors))
    rating = soup.select_one(".film-detail__film__rating")
    if rating:
        meta["certificate"] = _clean(rating.get_text())
    return meta


def _parse_title(soup) -> tuple[str | None, int | None]:
    el = soup.select_one(".film-detail__title")
    raw = _clean(el.get_text(" ")) if el else None
    if not raw:
        return None, None
    year = None
    ym = _TITLE_YEAR_RE.search(raw)
    if ym:
        year = int(ym.group(0).strip(" ()"))
        raw = _TITLE_YEAR_RE.sub(" ", raw)
    # Drop a trailing certificate token (U, PG, 12A, 15, 18, TBC...).
    raw = re.sub(r"\s+(U|PG|12A?|15|18|R18|TBC)\s*$", "", raw, flags=re.I)
    return _clean(raw), year


def _parse_screenings(soup, today: dt.date) -> list[Screening]:
    screenings: list[Screening] = []
    for panel in soup.select(".screening-panel"):
        date_el = panel.select_one(".screening-panel__date-title")
        if not date_el:
            continue
        date = _parse_abbrev_date(date_el.get_text(), today)
        if not date or date < today.isoformat():
            continue
        for time_el in panel.select(".screening-time"):
            a = time_el.find("a")
            parsed = parse_time(time_el.get_text())
            if not parsed:
                continue
            time_24, _ = parsed
            # parse_time keeps the raw text as display; rebuild a clean one.
            hh, mm = int(time_24[:2]), time_24[3:]
            ampm = "am" if hh < 12 else "pm"
            display = f"{hh % 12 or 12}:{mm} {ampm}"
            href = a.get("href") if a else None
            classes = (a.get("class") or []) if a else []
            sold_out = any("sold" in c.lower() for c in classes) or not href
            formats = [_clean(t.get_text()) for t in panel.select(".screening-tag")]
            formats = [f.replace("ext-", "") for f in formats if f]
            screenings.append(Screening(
                venue=VENUE_ID,
                date=date,
                time=time_24,
                display_time=display,
                booking_url=href if not sold_out else None,
                formats=formats,
                sold_out=sold_out,
            ))
    return screenings


def scrape() -> list[Film]:
    today = dt.date.today()
    home = get(VENUE_URL).text
    films: list[Film] = []

    for i, url in enumerate(_film_urls(home)):
        if i:
            time.sleep(0.3)
        try:
            page = get(url).text
        except Exception:
            continue
        soup = BeautifulSoup(page, "html.parser")

        title, title_year = _parse_title(soup)
        if not title:
            continue
        screenings = _parse_screenings(soup, today)
        if not screenings:
            continue

        meta = _parse_meta(soup)
        syn_el = soup.select_one(".film-detail__synopsis") or soup.select_one(".synopsis")
        synopsis = _clean(syn_el.get_text(" ")) if syn_el else None
        img = soup.select_one(".film-detail__image__wrapper img")
        poster = img.get("src") if (img and img.get("src")) else None

        films.append(Film(
            title=title,
            year=meta.get("year") or title_year,
            director=meta.get("director"),
            runtime=meta.get("runtime"),
            country=meta.get("country"),
            certificate=meta.get("certificate"),
            poster=poster if (poster and poster.startswith("http")) else None,
            film_url=url,
            synopsis=synopsis[:600] if synopsis else None,
            screenings=screenings,
        ))

    return films
