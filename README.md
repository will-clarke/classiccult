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
| Prince Charles Cinema | HTML scrape (jacro plugin) | Densest classic/rep programming; year, director, runtime inline |
| The Garden Cinema | HTML scrape (WordPress) | Per-film pages; year + runtime reliable |
| Phoenix Cinema | Savoy `var Events` JSON | Full metadata incl. year/director/synopsis |
| Rio Cinema | Savoy `var Events` JSON | Full metadata incl. year/director/synopsis |
| Genesis Cinema | HTML scrape (Admit One) | No release year in source → filled by TMDB |
| Barbican | HTML scrape (Drupal, `?day=` walk) | No release year in source → filled by TMDB |
| ICA | HTML scrape (Spektrix-backed page) | Year/director parsed from credits line |
| The Castle Cinema | schema.org `ScreeningEvent` JSON-LD | No release year in source → filled by TMDB |

Adding a venue = one file in `scraper/venues/` exposing `VENUE_ID`, `VENUE_NAME`,
`VENUE_URL`, and `scrape() -> list[Film]`, then add it to `scraper/venues/__init__.py`.
(`scraper/venues/savoy.py` is a shared helper used by Phoenix + Rio, not a venue itself.)

### Blocked — need a headless browser (not yet active)
- **Close-Up** — Cloudflare JS challenge blocks plain `requests`. A complete, verified parser lives in `scraper/venues/closeup.py` (unregistered); only the fetch layer needs a headless browser / cloudscraper to activate.
- **BFI Southbank** — live showtimes are behind a Cloudflare JS challenge; the open CMS JSON:API exists but its performance data is stale (nothing since 2022). No module written.

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

## Deploy (free, via Cloudflare Pages)

1. Push this repo to GitHub (`will-clarke/classiccult`).
2. Cloudflare dashboard → **Workers & Pages → Create → Pages → Connect to Git** → select the repo.
3. Build settings — **Framework preset: None**, **Build command: *(empty)***, **Build output directory: `docs`**, **Production branch: `main`**.
4. Deploy. Every push redeploys, including the daily scraper bot commit, so the live site refreshes itself.

Data refresh runs independently on GitHub Actions (`.github/workflows/scrape.yml`): daily at 06:00 UTC (and on demand via *Actions → Run workflow*), it scrapes every registered venue and commits a fresh `screenings.json` — which triggers a Cloudflare redeploy. (For the bot's commit to push, enable Settings → Actions → General → *Workflow permissions* → **Read and write**.)

`"classic"` is defined in `scraper/scrape.py` as released ≥ `CLASSIC_AGE` (default 20) years ago. The site defaults to *Classics only*; toggle it off to see everything.

> Showtimes are scraped from each cinema's public listings for personal use. Always
> confirm on the venue's own site before travelling. Not affiliated with any cinema.
