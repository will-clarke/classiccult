"""Clusterflick open-data source (MIT - https://github.com/clusterflick).

Some venues sit behind a Cloudflare challenge that blocks datacenter / CI IPs
(notably BFI Southbank), so they can't be scraped from GitHub Actions directly.
Clusterflick aggregates 300+ London venues - running the Cloudflare-gated ones
from a residential Raspberry Pi cluster - and publishes a daily MIT-licensed
`combined-data.json` GitHub release. We download that with a plain GET (no
Cloudflare in our path) and map the venues we want.

Per the MIT licence we credit Clusterflick in the site footer + README.

The combined dataset is normalised: top-level `movies`, each with `year`,
`posterPath` (a TMDB path), and `performances` ({time epoch-ms, bookingUrl,
showingId, status}); `showings[showingId]` carries `venueId`, `category`, and
an `overview` with directors/duration/classification.
"""
from __future__ import annotations

import datetime as dt
import functools

import requests

from .base import Film, Screening

_RELEASES_API = "https://api.github.com/repos/clusterflick/data-combined/releases/latest"
_TMDB_IMG = "https://image.tmdb.org/t/p/w500"
_FILM_CATEGORIES = {"movie", "shorts", "multiple-movies"}

ATTRIBUTION = "BFI Southbank listings via Clusterflick (clusterflick.com), MIT-licensed."


@functools.lru_cache(maxsize=1)
def combined() -> dict:
    """Download the latest combined dataset once per run (shared across venues)."""
    rel = requests.get(_RELEASES_API, timeout=30,
                       headers={"Accept": "application/vnd.github+json"}).json()
    asset = next(a for a in rel.get("assets", []) if a["name"] == "combined-data.json")
    print(f"[clusterflick] release {rel.get('tag_name')} ({asset['size'] // 1_000_000}MB)")
    return requests.get(asset["browser_download_url"], timeout=180).json()


def films_for(cf_venue_id: str, our_venue_id: str) -> list[Film]:
    """Return Films screening at the given Clusterflick venue, mapped to our model."""
    data = combined()
    today = dt.date.today().isoformat()
    films: list[Film] = []

    for mv in data.get("movies", {}).values():
        showings = mv.get("showings", {})
        screenings: list[Screening] = []
        director = certificate = runtime = film_url = None

        for perf in mv.get("performances", []):
            sh = showings.get(perf.get("showingId"), {})
            if sh.get("venueId") != cf_venue_id:
                continue
            if (sh.get("category") or "movie") not in _FILM_CATEGORIES:
                continue
            t = perf.get("time")
            if not t:
                continue
            when = dt.datetime.fromtimestamp(t / 1000)
            date_iso = when.date().isoformat()
            if date_iso < today:
                continue

            ov = sh.get("overview") or {}
            director = director or (", ".join(ov["directors"]) if ov.get("directors") else None)
            certificate = certificate or ov.get("classification")
            if runtime is None and ov.get("duration"):
                runtime = f"{round(ov['duration'] / 60000)}mins"
            film_url = film_url or sh.get("url")

            ampm = "am" if when.hour < 12 else "pm"
            screenings.append(Screening(
                venue=our_venue_id,
                date=date_iso,
                time=f"{when.hour:02d}:{when.minute:02d}",
                display_time=f"{when.hour % 12 or 12}:{when.minute:02d} {ampm}",
                booking_url=perf.get("bookingUrl"),
                sold_out=bool((perf.get("status") or {}).get("soldOut")),
            ))

        if not screenings:
            continue
        raw_year = mv.get("year")
        year = int(raw_year) if str(raw_year).strip().isdigit() else None
        films.append(Film(
            title=(mv.get("title") or "Untitled").strip(),
            year=year,
            director=director,
            runtime=runtime,
            certificate=certificate,
            poster=(_TMDB_IMG + mv["posterPath"]) if mv.get("posterPath") else None,
            film_url=film_url,
            screenings=screenings,
        ))
    return films
