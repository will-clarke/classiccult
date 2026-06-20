"""Venue registry. Each venue module exposes VENUE_ID, VENUE_NAME, VENUE_URL, scrape()."""
from . import prince_charles, castle, genesis, barbican, ica, phoenix, rio, garden, bfi

VENUES = [prince_charles, castle, genesis, barbican, ica, phoenix, rio, garden, bfi]

# bfi is sourced via Clusterflick open data (clusterflick.py), since BFI's own
# listings are behind a Cloudflare challenge that blocks CI IPs. A direct
# Tessitura scraper for residential/homelab runs lives in bfi_direct.py.
# Not registered:
#   - closeup : Cloudflare-blocked; complete parser in closeup.py, fetch blocked
