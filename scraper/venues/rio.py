"""Rio Cinema (Dalston).

Runs on the Savoy Systems platform - the public site IS the Savoy "Rio.dll"
web app. The /WhatsOn page embeds a complete ``var Events`` JSON listing, which
we parse via the shared savoy helper. robots.txt redirects to the homepage
(no rules).
"""
from __future__ import annotations

from .base import Film
from .savoy import scrape_savoy

VENUE_ID = "rio"
VENUE_NAME = "Rio Cinema"
VENUE_URL = "https://riocinema.org.uk/Rio.dll/WhatsOn"


def scrape() -> list[Film]:
    return scrape_savoy(VENUE_ID, VENUE_NAME, VENUE_URL)
