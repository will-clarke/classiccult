"""BFI Southbank - the UK's leading repertory cinema.

Sourced via Clusterflick open data (see clusterflick.py). BFI's own listings sit
behind a Cloudflare challenge that blocks datacenter/CI IPs, so we can't scrape it
directly from GitHub Actions. Clusterflick fetches BFI from residential IPs and
publishes the data daily under MIT; we consume that, fully on CI.

A direct Tessitura `searchResults` scraper (works from a residential IP / homelab,
not CI) is kept in `bfi_direct.py` as an unregistered alternative.
"""
from . import clusterflick

VENUE_ID = "bfi"
VENUE_NAME = "BFI Southbank"
VENUE_URL = "https://whatson.bfi.org.uk/"

_CF_VENUE_ID = "bfi.org.uk-southbank"


def scrape():
    return clusterflick.films_for(_CF_VENUE_ID, VENUE_ID)
