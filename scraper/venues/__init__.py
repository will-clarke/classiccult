"""Venue registry. Each venue module exposes VENUE_ID, VENUE_NAME, VENUE_URL, scrape()."""
from . import prince_charles, castle, genesis, barbican, ica, phoenix, rio, garden

VENUES = [prince_charles, castle, genesis, barbican, ica, phoenix, rio, garden]

# Not registered (require a headless browser to clear a Cloudflare JS challenge):
#   - closeup  : parser complete in closeup.py, only the fetch layer is blocked
#   - bfi      : live showtimes behind Cloudflare; CMS API data is stale (no module)
