"""Venue registry. Each venue module exposes VENUE_ID, VENUE_NAME, VENUE_URL, scrape()."""
from . import prince_charles, castle

VENUES = [prince_charles, castle]
