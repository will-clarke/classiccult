"""Shared scraper for cinemas on the Savoy Systems ticketing platform.

Several London independents run their public site directly off the Savoy
"<Venue>.dll" web app (e.g. Phoenix East Finchley, Rio Dalston). The "What's
On" page embeds a complete ``var Events = {...}`` JSON blob containing every
current film with full metadata and its performances - far more robust than
scraping the (carousel-only) rendered HTML.

This helper parses that blob. Venues whose public site does NOT expose the
JSON listing (e.g. The Garden Cinema, which renders showtimes in its own
WordPress markup) are scraped in their own module instead.
"""
from __future__ import annotations

import datetime as dt
import html as _html
import json
import re

from .base import Film, Screening, get

# var Events = {...};   (capture the start, then brace-match the object)
_EVENTS_RE = re.compile(r"var\s+Events\s*=\s*")
# Rating arrives as an <img ... alt="BBFC Rating: (15)"/> string.
_CERT_RE = re.compile(r"\(([^)]+)\)")
# Performance perk flags -> short format labels.
_FLAG_FORMATS = {"CC": "CC", "AD": "AD", "SU": "SUB", "BB": "BABY", "R": "RELAXED"}


def _extract_events(html: str) -> list[dict]:
    """Pull the films array out of the embedded ``var Events`` JSON object."""
    m = _EVENTS_RE.search(html)
    if not m:
        return []
    start = m.end()
    if start >= len(html) or html[start] != "{":
        return []
    depth = 0
    in_str = False
    esc = False
    end = None
    for i in range(start, len(html)):
        c = html[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
    if end is None:
        return []
    try:
        data = json.loads(html[start:end])
    except (ValueError, json.JSONDecodeError):
        return []
    events = data.get("Events") if isinstance(data, dict) else None
    return events if isinstance(events, list) else []


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", _html.unescape(str(text))).strip()
    return text or None


def _to_int(text) -> int | None:
    if text is None:
        return None
    m = re.search(r"(19|20)\d{2}", str(text))
    return int(m.group(0)) if m else None


def _runtime(text) -> str | None:
    """RunningTime is a minutes string like '145'."""
    m = re.search(r"\d+", str(text or ""))
    return f"{m.group(0)}mins" if m else None


def _certificate(rating) -> str | None:
    if not rating:
        return None
    m = _CERT_RE.search(str(rating))
    return _clean(m.group(1)) if m else None


def _base_dll(film_url: str | None, dll_base: str | None) -> str | None:
    """Resolve the '<Venue>.dll/' base used to absolutise relative booking URLs."""
    if dll_base:
        return dll_base
    if film_url:
        # ".../PhoenixCinemaLondon.dll/WhatsOn?f=1" -> ".../PhoenixCinemaLondon.dll/"
        m = re.match(r"(.*?\.dll/)", film_url)
        if m:
            return m.group(1)
    return None


def _parse_time(start_time, readable_date: str | None) -> tuple[str, str] | None:
    """StartTime is 'HHMM' (24h). Build sortable + human ('7:45 pm')."""
    digits = re.sub(r"\D", "", str(start_time or ""))
    if len(digits) == 3:
        digits = "0" + digits
    if len(digits) != 4:
        return None
    hh, mm = int(digits[:2]), digits[2:]
    if hh > 23:
        return None
    ampm = "am" if hh < 12 else "pm"
    h12 = hh % 12 or 12
    return f"{hh:02d}:{mm}", f"{h12}:{mm} {ampm}"


def scrape_savoy(
    venue_id: str,
    venue_name: str,
    whats_on_url: str,
    dll_base: str | None = None,
    today: dt.date | None = None,
) -> list[Film]:
    """Scrape a Savoy-hosted "What's On" page into a list of Films.

    Only films with at least one upcoming screening (date >= today) are kept.
    """
    today = today or dt.date.today()
    today_iso = today.isoformat()

    html = get(whats_on_url).text
    events = _extract_events(html)
    films: list[Film] = []

    for ev in events:
        if not isinstance(ev, dict):
            continue
        title = _clean(ev.get("Title"))
        if not title:
            continue
        film_url = _clean(ev.get("URL"))
        base = _base_dll(film_url, dll_base)

        screenings: list[Screening] = []
        for perf in ev.get("Performances") or []:
            if not isinstance(perf, dict):
                continue
            date = _clean(perf.get("StartDate"))
            if not date or date < today_iso:
                continue
            parsed = _parse_time(perf.get("StartTime"), perf.get("ReadableDate"))
            if not parsed:
                continue
            time_24, display = parsed

            notes = _clean(perf.get("Notes")) or ""
            sold_out = (
                str(perf.get("IsSoldOut", "")).upper() == "Y"
                or not perf.get("IsOpenForSale", True)
                or "sold out" in notes.lower()
            )
            formats = [label for flag, label in _FLAG_FORMATS.items()
                       if str(perf.get(flag, "")).upper() == "Y"]
            if notes and "sold out" not in notes.lower():
                formats.append(notes)

            booking_url = _clean(perf.get("URL"))
            if booking_url and not booking_url.startswith("http") and base:
                booking_url = base + booking_url

            screenings.append(Screening(
                venue=venue_id,
                date=date,
                time=time_24,
                display_time=display,
                booking_url=None if sold_out else booking_url,
                formats=formats,
                sold_out=sold_out,
            ))

        if not screenings:
            continue

        synopsis = _clean(ev.get("Synopsis"))
        poster = _clean(ev.get("ImageURL"))
        films.append(Film(
            title=title,
            year=_to_int(ev.get("Year")),
            director=_clean(ev.get("Director")),
            runtime=_runtime(ev.get("RunningTime")),
            country=_clean(ev.get("Country")),
            certificate=_certificate(ev.get("Rating")),
            poster=poster if (poster and poster.startswith("http")) else None,
            film_url=film_url,
            synopsis=synopsis[:600] if synopsis else None,
            screenings=screenings,
        ))

    return films
