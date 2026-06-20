"""Barbican Cinema (City of London) - strong repertory and classic programming.

Drupal site. The /whats-on/cinema listing is a Views block exposing a `day`
filter (?day=YYYY-MM-DD). Each day renders fully server-side as
`.cinema-listing-card` elements carrying the title, runtime, poster, synopsis
and that day's showtimes (with direct tickets.barbican.org.uk booking links).

The detail pages load their showtimes via JS, so we instead walk a forward
window of days through the listing's own date filter - no headless browser
needed - and merge each day's screenings per film.

robots.txt (User-agent: *) is Allow: / for the listing path; only /admin,
/search etc. are disallowed.
"""
from __future__ import annotations

import datetime as dt
import re
import time

from bs4 import BeautifulSoup

from .base import Film, Screening, get, parse_human_date, parse_time

VENUE_ID = "barbican"
VENUE_NAME = "Barbican"
VENUE_URL = "https://www.barbican.org.uk/whats-on/cinema"
_BASE = "https://www.barbican.org.uk"

# How many days ahead to walk, and how many consecutive empty days to tolerate
# before assuming the schedule has run out.
_WINDOW_DAYS = 28
_MAX_EMPTY_STREAK = 6


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _abs(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("http"):
        return url
    return _BASE + url


def _runtime(tags: list[str]) -> str | None:
    """The card tag holds runtime like '1hr 47mins' or '2 hr 45 min' or '67mins'."""
    for t in tags:
        m = re.search(r"(?:(\d+)\s*hr)?\s*(\d+)\s*min", t, re.I)
        if m:
            hours = int(m.group(1) or 0)
            mins = int(m.group(2))
            total = hours * 60 + mins
            if total:
                return f"{total}mins"
    return None


def _parse_card_screenings(card, date_iso: str) -> list[Screening]:
    """Read showtimes for the given day from one listing card."""
    screenings: list[Screening] = []
    for inst in card.select(".cinema-instance-list__instance"):
        a = inst.find("a")
        # Time text is the visible label, e.g. '11.00am' / '6.20pm'.
        raw = _clean(inst.get_text(" ")) or ""
        # base.parse_time wants a colon separator; Barbican uses a dot.
        raw = re.sub(r"(\d)\.(\d{2})\s*([ap]m)", r"\1:\2 \3", raw, flags=re.I)
        parsed = parse_time(raw)
        if not parsed:
            continue
        time_24, _ = parsed
        # Rebuild a clean display string from the 24h value.
        hh, mm = int(time_24[:2]), time_24[3:]
        ampm = "am" if hh < 12 else "pm"
        h12 = hh % 12 or 12
        display = f"{h12}:{mm} {ampm}"
        href = a.get("href") if a else None
        screenings.append(Screening(
            venue=VENUE_ID,
            date=date_iso,
            time=time_24,
            display_time=display,
            booking_url=_abs(href),
        ))
    return screenings


def _parse_day(html: str, date_iso: str, by_title: dict[str, Film]) -> int:
    """Merge one day's cards into by_title. Returns number of cards seen."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".cinema-listing-card")
    for card in cards:
        title_el = card.select_one(".cinema-listing-card__title a")
        title = _clean(title_el.get_text()) if title_el else None
        if not title:
            continue
        screenings = _parse_card_screenings(card, date_iso)
        if not screenings:
            continue

        film = by_title.get(title)
        if not film:
            tags = [_clean(t.get_text()) or "" for t in card.select(".cinema-listing-card__tag")]
            img = card.select_one(".cinema-listing-card__media img")
            synopsis_el = card.select_one(".cinema-listing-card__content p")
            film = Film(
                title=title,
                runtime=_runtime(tags),
                poster=_abs(img.get("src")) if img else None,
                film_url=_abs(title_el.get("href")),
                synopsis=(_clean(synopsis_el.get_text(" ")) or "")[:600] or None
                if synopsis_el else None,
            )
            by_title[title] = film
        film.screenings.extend(screenings)
    return len(cards)


def scrape() -> list[Film]:
    today = dt.date.today()
    by_title: dict[str, Film] = {}
    empty_streak = 0

    for offset in range(_WINDOW_DAYS):
        day = today + dt.timedelta(days=offset)
        url = f"{VENUE_URL}?day={day.isoformat()}"
        try:
            html = get(url).text
        except Exception:
            empty_streak += 1
            if empty_streak >= _MAX_EMPTY_STREAK:
                break
            time.sleep(0.3)
            continue

        seen = _parse_day(html, day.isoformat(), by_title)
        empty_streak = 0 if seen else empty_streak + 1
        if empty_streak >= _MAX_EMPTY_STREAK:
            break
        time.sleep(0.3)  # be polite between day fetches

    # Only films with upcoming screenings (every collected date is >= today).
    return [f for f in by_title.values() if f.screenings]
