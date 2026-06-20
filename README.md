# ClassicCult

A zero-backend website listing **classic & cult films screening in London cinemas**.
A scheduled scraper runs on GitHub Actions, writes a static `screenings.json`, and a
plain HTML/JS site reads it. Nothing to host, nothing to pay for.

```
GitHub Actions (daily cron)              ← the only "compute"
  └─ python -m scraper.scrape
       ├─ scrapes each venue
       ├─ (optional) TMDB enrichment for missing years/posters
       └─ writes docs/data/screenings.json  ──commit──┐
                                                       ▼
        docs/ (static site)  ── served by GitHub Pages ──▶ visitors
```

## Venues

| Venue | Method | Notes |
|-------|--------|-------|
| Prince Charles Cinema | HTML scrape | Densest classic programming; year/director/runtime inline |
| The Castle Cinema | schema.org `ScreeningEvent` JSON-LD | Years absent in source → filled by TMDB |

Adding a venue = one file in `scraper/venues/` exposing `VENUE_ID`, `VENUE_NAME`,
`VENUE_URL`, and `scrape() -> list[Film]`, then add it to `scraper/venues/__init__.py`.

Candidate venues already scouted (not yet implemented):
- **Savoy Systems** sites (Garden Cinema, Rio Dalston, Phoenix East Finchley) — one parser could cover several, but showtimes live on a separate `savoysystems.co.uk` ticketing domain.
- **ICA** — Spektrix.
- **BFI Southbank** — largest classic programme; JS-heavy, needs investigation.

## Run locally

```bash
pip install -r scraper/requirements.txt
python -m scraper.scrape                 # writes docs/data/screenings.json
cd docs && python -m http.server 8765    # open http://localhost:8765
```

### Optional: TMDB enrichment

Fills missing release years (so the *Classics only* filter works for venues whose
listings omit the year) and missing posters.

1. Get a free key: <https://www.themoviedb.org/settings/api>
2. Local: `export TMDB_API_KEY=...` before running the scraper.
3. CI: add it as a repository secret named `TMDB_API_KEY`.

Without a key the scrape still runs; enrichment is simply skipped. Results are cached
in `scraper/.tmdb_cache.json` so re-runs don't re-hit the API.

## Deploy (free)

1. Push this repo to GitHub.
2. **Settings → Pages → Build and deployment → Deploy from a branch**, branch `main`, folder `/docs`.
3. The `Scrape listings` workflow runs daily (and on demand via *Actions → Run workflow*), commits a fresh `screenings.json`, and Pages serves the update.

`"classic"` is defined in `scraper/scrape.py` as released ≥ `CLASSIC_AGE` (default 20) years ago. The site defaults to *Classics only*; toggle it off to see everything.

> Showtimes are scraped from each cinema's public listings for personal use. Always
> confirm on the venue's own site before travelling. Not affiliated with any cinema.
