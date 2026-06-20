"""Shared helpers for venue scrapers."""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field, asdict

import requests

USER_AGENT = "repertory-london-bot/1.0 (+https://github.com/; personal hobby film-listings aggregator)"

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})


def get(url: str, **kwargs) -> requests.Response:
    """Polite GET with a sane timeout and our identifying UA."""
    kwargs.setdefault("timeout", 30)
    resp = _session.get(url, **kwargs)
    resp.raise_for_status()
    return resp


@dataclass
class Screening:
    venue: str          # venue id, e.g. "pcc"
    date: str           # ISO date "2026-06-23"
    time: str           # 24h sortable "12:15"
    display_time: str   # human "12:15 pm"
    booking_url: str | None = None
    formats: list[str] = field(default_factory=list)  # ["4K", "35mm", "SUB"]
    sold_out: bool = False


@dataclass
class Film:
    title: str
    year: int | None = None
    director: str | None = None
    runtime: str | None = None
    country: str | None = None
    certificate: str | None = None
    poster: str | None = None
    film_url: str | None = None
    synopsis: str | None = None
    screenings: list[Screening] = field(default_factory=list)


def to_dict(film: Film) -> dict:
    return asdict(film)


_MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"], start=1)
}


def parse_human_date(text: str, today: dt.date | None = None) -> str | None:
    """Parse 'Saturday 20th June' (no year) -> ISO date, inferring the year.

    A weekday prefix is optional. The year is chosen so the date lands within
    the next ~11 months (handles the Dec->Jan rollover at year boundaries).
    """
    today = today or dt.date.today()
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)", text)
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
        # accept dates from a little in the past up to ~11 months ahead
        if -14 <= (cand - today).days <= 330:
            return cand.isoformat()
    return None


def parse_time(text: str) -> tuple[str, str] | None:
    """'12:15 pm' -> ('12:15', '12:15 pm'). Returns (sortable_24h, display)."""
    text = text.strip()
    m = re.search(r"(\d{1,2}):(\d{2})\s*([ap]\.?m\.?)?", text, re.I)
    if not m:
        return None
    hour, minute = int(m.group(1)), m.group(2)
    ampm = (m.group(3) or "").replace(".", "").lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute}", text
