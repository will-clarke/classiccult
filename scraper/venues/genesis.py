"""Genesis Cinema (Mile End, London).

Runs an 'Admit One' (A1) cinema platform. The /whatson page is server-rendered
Tailwind HTML (~620KB, no JSON-LD or embedded JSON blob). Listings are grouped
into one panel per day: <div id="panel_YYYYMMDD" class="whatson_panel">. Each
film card carries an <h2> title, a /customFilmImages/ poster, a /ratings/UK/...
certificate image, a "Running time: N mins" line, a synopsis, and a grid of
showtime buttons (a.perfButton) linking to admit-one.co.uk seat selection.

The page renders each card's showtimes twice (mobile + desktop layouts), so we
dedupe screenings by (date, perfCode). robots.txt disallows nothing.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import Film, Screening, get

VENUE_ID = "genesis"
VENUE_NAME = "Genesis Cinema"
VENUE_URL = "https://www.genesiscinema.co.uk/whatson"
_BASE = "https://www.genesiscinema.co.uk"

_PANEL_DATE_RE = re.compile(r"panel_(\d{4})(\d{2})(\d{2})")
_PERFCODE_RE = re.compile(r"perfCode=(\d+)")
_RUNTIME_RE = re.compile(r"(\d+)\s*mins?", re.I)
_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_CERT_RE = re.compile(r"/ratings/[^/]+/([A-Za-z0-9]+?)(?:lrg)?\.(?:png|jpg|svg)", re.I)


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _panel_date(panel) -> str | None:
    m = _PANEL_DATE_RE.search(panel.get("id") or "")
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def _abs(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http"):
        return url
    return _BASE + "/" + url.lstrip("./").lstrip("/")


def _poster(card) -> str | None:
    for img in card.find_all("img"):
        src = img.get("src") or ""
        if "customFilmImages" in src or "/filmImages" in src:
            return _abs(src)
    return None


def _certificate(card) -> str | None:
    for img in card.find_all("img"):
        m = _CERT_RE.search(img.get("src") or "")
        if m:
            return m.group(1)
    return None


def _runtime(card) -> str | None:
    txt = card.get_text(" ", strip=True)
    m = _RUNTIME_RE.search(txt)
    return f"{m.group(1)}mins" if m else None


def _synopsis(card, title: str | None) -> str | None:
    """Pick the longest paragraph that isn't a UI label or the title."""
    best = None
    for p in card.find_all("p"):
        t = _clean(p.get_text(" "))
        if not t or len(t) < 25:
            continue
        low = t.lower()
        if low.startswith("running time") or t == title:
            continue
        if best is None or len(t) > len(best):
            best = t
    return best[:600] if best else None


def _formats(button) -> list[str]:
    fmts: list[str] = []
    for img in button.find_all("img"):
        m = re.search(r"perftypeIcons/[^/]*?_([a-z0-9-]+)\.svg", img.get("src") or "", re.I)
        if m:
            fmts.append(m.group(1).replace("-", " ").title())
    return fmts


def _screenings(card, date: str) -> list[Screening]:
    seen: set[str] = set()
    out: list[Screening] = []
    for a in card.select("a.perfButton"):
        href = a.get("href") or ""
        code_m = _PERFCODE_RE.search(href)
        code = code_m.group(1) if code_m else None
        time_m = _TIME_RE.search(a.get_text(" ", strip=True))
        if not time_m:
            continue
        hh, mm = int(time_m.group(1)), time_m.group(2)
        if hh > 23:
            continue
        key = f"{code or ''}-{hh:02d}:{mm}"
        if key in seen:
            continue
        seen.add(key)
        ampm = "am" if hh < 12 else "pm"
        h12 = hh % 12 or 12
        sold_out = "soldOutOverride" in str(a)
        out.append(Screening(
            venue=VENUE_ID,
            date=date,
            time=f"{hh:02d}:{mm}",
            display_time=f"{h12}:{mm} {ampm}",
            booking_url=_abs(href) if href and not sold_out else None,
            formats=_formats(a),
            sold_out=sold_out,
        ))
    return out


def scrape() -> list[Film]:
    soup = BeautifulSoup(get(VENUE_URL).text, "html.parser")
    by_title: dict[str, Film] = {}

    for panel in soup.select("div.whatson_panel"):
        date = _panel_date(panel)
        if not date:
            continue
        for card in panel.select("div.bg-white"):
            if not card.select_one("a.perfButton"):
                continue
            h2 = card.find("h2")
            title = _clean(h2.get_text()) if h2 else None
            if not title:
                continue
            screenings = _screenings(card, date)
            if not screenings:
                continue

            ev = card.find("a", href=re.compile(r"event/\d+"))
            film_url = _abs(ev.get("href")) if ev else None

            film = by_title.get(title)
            if not film:
                film = Film(
                    title=title,
                    runtime=_runtime(card),
                    certificate=_certificate(card),
                    poster=_poster(card),
                    film_url=film_url,
                    synopsis=_synopsis(card, title),
                )
                by_title[title] = film
            film.screenings.extend(screenings)

    return [f for f in by_title.values() if f.screenings]
