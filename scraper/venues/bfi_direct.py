"""BFI Southbank.

The richest classic/repertory programme in London. Listings live in a Tessitura
"Online" system (whatson.bfi.org.uk) behind a Cloudflare JS challenge.

The win: each film page embeds its performances as a Tessitura `searchResults`
JS array in the raw HTML (no JS rendering needed) - so once we can fetch the
page, parsing is plain regex/JSON. Columns are stable:

    [5]=title  [7]="Monday 29 June 2026 18:15"  [8]="18:15"
    [17]="Big screen classics,Digital,English subtitles"  [18]=booking link

The only obstacle is Cloudflare. cf_clearance is bound to the IP that solved it,
so clearing and fetching must happen on the same host. Three fetch backends, in
order of preference (whichever is configured):

  1. FLARESOLVERR_URL  - a self-hosted FlareSolverr instance (recommended; runs
                         well on a homelab/docker box on a residential IP).
  2. BFI_COOKIE (+ BFI_UA) - a cf_clearance cookie string captured on this host.
  3. Playwright        - best-effort headed Chromium (often blocked on
                         datacenter/CI IPs).

If none can fetch, scrape() returns [] and the rest of the aggregate is fine.
Year/poster come from TMDB enrichment (BFI's classic titles disambiguate well).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time

import requests
from bs4 import BeautifulSoup

from .base import Film, Screening

VENUE_ID = "bfi"
VENUE_NAME = "BFI Southbank"
VENUE_URL = "https://whatson.bfi.org.uk/Online/default.asp"
_BASE = "https://whatson.bfi.org.uk/Online/"
_DEFAULT_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36")

CATEGORIES = ["big-screen-classics", "rereleases"]
_FORMAT_TAGS = {"35mm", "70mm", "4k", "digital", "imax"}


def _permalink_url(slug: str) -> str:
    return f"{_BASE}default.asp?BOparam::WScontent::loadArticle::permalink={slug}"


# ---------- fetch backends -------------------------------------------------

def _flaresolverr_getter(endpoint: str):
    def get(url):
        try:
            r = requests.post(endpoint, json={"cmd": "request.get", "url": url,
                                              "maxTimeout": 60000}, timeout=90)
            sol = r.json().get("solution", {})
            return sol.get("response") if sol.get("status") == 200 else None
        except Exception:
            return None
    return get


def _cookie_getter(cookie: str):
    sess = requests.Session()
    sess.headers.update({"User-Agent": os.environ.get("BFI_UA", _DEFAULT_UA), "Cookie": cookie})
    def get(url):
        try:
            r = sess.get(url, timeout=30)
            return r.text if r.status_code == 200 else None
        except Exception:
            return None
    return get


# ---------- parsing (proven against live BFI HTML) -------------------------

def _extract_search_results(html: str) -> list:
    i = html.find("searchResults")
    if i < 0:
        return []
    j = html.find("[", i)
    depth, k = 0, j
    while k < len(html):
        if html[k] == "[":
            depth += 1
        elif html[k] == "]":
            depth -= 1
            if depth == 0:
                break
        k += 1
    try:
        return json.loads(html[j:k + 1])
    except Exception:
        return []


def _parse_when(text: str):
    """'Monday 29 June 2026 18:15' -> (iso_date, '18:15', '6:15 pm')."""
    try:
        d = dt.datetime.strptime(text.strip(), "%A %d %B %Y %H:%M")
    except ValueError:
        return None
    ampm = "am" if d.hour < 12 else "pm"
    return d.date().isoformat(), f"{d.hour:02d}:{d.minute:02d}", f"{d.hour % 12 or 12}:{d.minute:02d} {ampm}"


def _formats(tags: str) -> list[str]:
    out = []
    for t in (tags or "").split(","):
        t = t.strip()
        if t.lower() in _FORMAT_TAGS:
            out.append(t)
        elif t.lower() == "english subtitles":
            out.append("SUB")
    return out


def _permalinks(html: str, exclude: set[str]) -> list[str]:
    slugs = re.findall(r"loadArticle::permalink=([a-z0-9-]+)", html)
    seen, out = set(), []
    for s in slugs:
        if s in exclude or s in seen or s.endswith("-intro"):
            continue
        seen.add(s)
        out.append(s)
    return out


def _director(html: str):
    soup = BeautifulSoup(html, "html.parser")
    for h in soup.select(".Film-info__information__heading"):
        if h.get_text(strip=True).lower() == "director":
            nxt = h.find_next_sibling()
            return nxt.get_text(" ", strip=True) if nxt else None
    return None


def _parse_film(html: str, slug: str) -> Film | None:
    rows = _extract_search_results(html)
    today = dt.date.today().isoformat()
    title = None
    screenings: list[Screening] = []
    for r in rows:
        if len(r) < 19:
            continue
        title = title or r[5]
        parsed = _parse_when(r[7])
        if not parsed or parsed[0] < today:
            continue
        date, time24, disp = parsed
        booking = r[18]
        if booking and not booking.startswith("http"):
            booking = _BASE + booking
        screenings.append(Screening(
            venue=VENUE_ID, date=date, time=time24, display_time=disp,
            booking_url=booking or _permalink_url(slug),
            formats=_formats(r[17]),
        ))
    if not screenings:
        return None
    return Film(title=(title or slug).strip(), director=_director(html),
                film_url=_permalink_url(slug), screenings=screenings)


# ---------- entrypoint -----------------------------------------------------

def _run(get) -> list[Film]:
    """Collect film permalinks from the category pages, parse each film."""
    seen: set[str] = set()
    slugs: list[str] = []
    for cat in CATEGORIES:
        html = get(_permalink_url(cat))
        if not html:
            continue
        for s in _permalinks(html, exclude={cat}):
            if s not in seen:
                seen.add(s)
                slugs.append(s)

    films: list[Film] = []
    for slug in slugs:
        html = get(_permalink_url(slug))
        if html and (film := _parse_film(html, slug)):
            films.append(film)
        time.sleep(0.2)
    return films


def scrape() -> list[Film]:
    if endpoint := os.environ.get("FLARESOLVERR_URL"):
        print("[bfi] fetch backend: flaresolverr")
        return _run(_flaresolverr_getter(endpoint))

    if cookie := os.environ.get("BFI_COOKIE"):
        print("[bfi] fetch backend: cookie")
        return _run(_cookie_getter(cookie))

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[bfi] no fetch backend - set FLARESOLVERR_URL or BFI_COOKIE, or install playwright; skipping")
        return []

    print("[bfi] fetch backend: playwright (best-effort; often blocked on datacenter IPs)")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False,
                                    args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = browser.new_context(locale="en-GB").new_page()

        def get(url):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_function("() => !/just a moment/i.test(document.title)", timeout=30000)
                return page.content()
            except Exception:
                return None

        try:
            return _run(get)
        finally:
            browser.close()
