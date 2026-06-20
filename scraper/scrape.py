#!/usr/bin/env python3
"""Scrape London repertory cinemas -> docs/data/screenings.json.

Run: python -m scraper.scrape   (from repo root)
No backend: this runs on a schedule (GitHub Actions) and commits the JSON,
which the static site reads directly.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import traceback

from . import tmdb
from .venues import VENUES
from .venues.base import to_dict

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "data" / "screenings.json"

# A film is "classic" if released at least this many years before now.
CLASSIC_AGE = 20


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc)
    classic_before = now.year - CLASSIC_AGE

    venues_meta: list[dict] = []
    collected: list[tuple[str, object]] = []  # (venue_id, Film)
    errors: list[str] = []

    for mod in VENUES:
        vid, vname, vurl = mod.VENUE_ID, mod.VENUE_NAME, mod.VENUE_URL
        try:
            films = mod.scrape()
        except Exception as exc:  # one broken venue must not sink the run
            errors.append(f"{vid}: {exc}")
            traceback.print_exc()
            films = []
        n_screenings = sum(len(f.screenings) for f in films)
        print(f"[{vid}] {len(films)} films, {n_screenings} screenings")
        venues_meta.append({
            "id": vid, "name": vname, "url": vurl,
            "films": len(films), "screenings": n_screenings,
        })
        collected.extend((vid, f) for f in films)

    # optional: fill missing years/posters so 'classic' works for every venue
    tmdb.enrich([f for _, f in collected])

    films_out: list[dict] = []
    for vid, f in collected:
        d = to_dict(f)
        d["venue"] = vid
        d["classic"] = bool(f.year and f.year <= classic_before)
        films_out.append(d)

    payload = {
        "generated_at": now.isoformat(),
        "classic_before_year": classic_before,
        "venues": venues_meta,
        "films": films_out,
        "errors": errors,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    total = sum(len(f["screenings"]) for f in films_out)
    print(f"\nWrote {OUT.relative_to(ROOT)}: {len(films_out)} films, {total} screenings")
    if errors:
        print(f"WARNING: {len(errors)} venue(s) failed: {errors}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
