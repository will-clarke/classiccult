"""Prince Charles Cinema (Leicester Square) - the densest classic/rep programming in London.

Server-rendered WordPress + 'jacro' cinema plugin. Listing page embeds film
metadata (year, runtime, director) and full showtimes directly in the HTML.
robots.txt only disallows /wp-admin/ and /booknow/ - the listing is fair game.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .base import Film, Screening, get, parse_human_date, parse_time

VENUE_ID = "pcc"
VENUE_NAME = "Prince Charles Cinema"
VENUE_URL = "https://princecharlescinema.com/whats-on/"

_FILM_ID_RE = re.compile(r"/film/(\d+)/")


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _parse_meta(content) -> dict:
    """Pull year / runtime / country / certificate from the running-time spans."""
    meta: dict = {}
    rt = content.select_one(".running-time")
    if rt:
        for span in rt.find_all("span"):
            val = _clean(span.get_text())
            if not val:
                continue
            if re.fullmatch(r"(19|20)\d{2}", val):
                meta["year"] = int(val)
            elif re.search(r"min", val, re.I):
                meta["runtime"] = val
            elif re.fullmatch(r"\(?(U|PG|12A?|15|18|R18|TBC)\)?", val, re.I):
                meta["certificate"] = val.strip("()")
            elif "country" not in meta and re.fullmatch(r"[A-Za-z .,/&-]+", val):
                meta["country"] = val
    info = content.select_one(".film-info")
    if info:
        for span in info.find_all("span"):
            t = _clean(span.get_text()) or ""
            if t.lower().startswith("directed by"):
                meta["director"] = _clean(t[len("directed by"):])
    return meta


def _parse_screenings(outer) -> list[Screening]:
    screenings: list[Screening] = []
    current_date: str | None = None
    ul = outer.select_one("ul.performance-list-items")
    if not ul:
        return screenings
    for el in ul.children:
        name = getattr(el, "name", None)
        if name == "div" and "heading" in (el.get("class") or []):
            current_date = parse_human_date(el.get_text())
        elif name == "li":
            if not current_date:
                continue
            a = el.find("a")
            time_span = el.select_one(".time")
            if not time_span:
                continue
            parsed = parse_time(time_span.get_text())
            if not parsed:
                continue
            time_24, display = parsed
            classes = a.get("class", []) if a else []
            sold_out = "soldfilm_book_button" in classes or not (a and a.get("href"))
            formats = [_clean(t.get_text()) for t in el.select(".movietag .tag")]
            formats = [f for f in formats if f]
            screenings.append(Screening(
                venue=VENUE_ID,
                date=current_date,
                time=time_24,
                display_time=display,
                booking_url=a.get("href") if (a and not sold_out) else None,
                formats=formats,
                sold_out=sold_out,
            ))
    return screenings


def scrape() -> list[Film]:
    html = get(VENUE_URL).text
    soup = BeautifulSoup(html, "html.parser")
    films: list[Film] = []
    for outer in soup.select(".film_list-outer"):
        content = outer.select_one(".jacrofilm-list-content")
        if not content:
            continue
        title_el = content.select_one(".liveeventtitle")
        title = _clean(title_el.get_text()) if title_el else None
        if not title:
            continue
        film_url = title_el.get("href") if title_el else None
        img = outer.select_one(".film_img img")
        poster = img.get("src") if img else None
        synopsis_el = content.select_one(".jacro-formatted-text")
        synopsis = _clean(synopsis_el.get_text(" ")) if synopsis_el else None

        meta = _parse_meta(content)
        screenings = _parse_screenings(outer)
        if not screenings:
            continue  # past/placeholder entries with no upcoming showtimes

        films.append(Film(
            title=title,
            year=meta.get("year"),
            director=meta.get("director"),
            runtime=meta.get("runtime"),
            country=meta.get("country"),
            certificate=meta.get("certificate"),
            poster=poster,
            film_url=film_url,
            synopsis=synopsis[:600] if synopsis else None,
            screenings=screenings,
        ))
    return films
