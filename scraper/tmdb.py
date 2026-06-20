"""Optional TMDB enrichment.

Fills missing release years (so the 'classic' filter works for venues whose
listings omit the year, e.g. The Castle) and missing posters. Entirely
optional: if TMDB_API_KEY is not set, enrichment is skipped and the scrape
still produces good data.

Get a free key at https://www.themoviedb.org/settings/api and set it as the
TMDB_API_KEY environment variable (a GitHub Actions secret in CI).

Results are cached to scraper/.tmdb_cache.json keyed by title so re-runs don't
re-hit the API and we stay well within rate limits.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import time

import requests

_CACHE_PATH = pathlib.Path(__file__).resolve().parent / ".tmdb_cache.json"
_IMG_BASE = "https://image.tmdb.org/t/p/w300"
_SEARCH = "https://api.themoviedb.org/3/search/movie"


def _load_cache() -> dict:
    try:
        return json.loads(_CACHE_PATH.read_text())
    except Exception:
        return {}


def _norm(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().lower()


def _lookup(session: requests.Session, key: str, title: str, year: int | None) -> dict | None:
    params = {"api_key": key, "query": title, "include_adult": "false"}
    if year:
        params["primary_release_year"] = year
    try:
        r = session.get(_SEARCH, params=params, timeout=20)
        r.raise_for_status()
        results = r.json().get("results", [])
    except Exception:
        return None
    if not results:
        return None
    # prefer an exact (case-insensitive) title match, else most popular
    exact = [m for m in results if _norm(m.get("title", "")) == _norm(title)]
    best = (exact or results)[0]
    rel = best.get("release_date") or ""
    return {
        "year": int(rel[:4]) if rel[:4].isdigit() else None,
        "poster": _IMG_BASE + best["poster_path"] if best.get("poster_path") else None,
        "tmdb_id": best.get("id"),
    }


def enrich(films: list) -> int:
    """Mutate Film objects in place. Returns count enriched. No-op without a key."""
    key = os.environ.get("TMDB_API_KEY")
    if not key:
        print("[tmdb] TMDB_API_KEY not set - skipping enrichment")
        return 0

    cache = _load_cache()
    session = requests.Session()
    enriched = 0
    for f in films:
        if f.year and f.poster:
            continue  # nothing missing
        ck = _norm(f.title) + (f"|{f.year}" if f.year else "")
        if ck not in cache:
            cache[ck] = _lookup(session, key, f.title, f.year) or {}
            time.sleep(0.05)  # gentle pacing
        hit = cache[ck]
        if not hit:
            continue
        if not f.year and hit.get("year"):
            f.year = hit["year"]
            enriched += 1
        if not f.poster and hit.get("poster"):
            f.poster = hit["poster"]

    try:
        _CACHE_PATH.write_text(json.dumps(cache, indent=0))
    except Exception:
        pass
    print(f"[tmdb] enriched {enriched} film(s)")
    return enriched
