"""Phoenix Cinema (East Finchley).

Runs on the Savoy Systems platform - the public site IS the Savoy
"PhoenixCinemaLondon.dll" web app. The /WhatsOn page embeds a complete
``var Events`` JSON listing (every current film + performances), which we parse
via the shared savoy helper. robots.txt redirects to the homepage (no rules).
"""
from __future__ import annotations

from .base import Film
from .savoy import scrape_savoy

VENUE_ID = "phoenix"
VENUE_NAME = "Phoenix Cinema"
VENUE_URL = "https://www.phoenixcinema.co.uk/PhoenixCinemaLondon.dll/WhatsOn"


def scrape() -> list[Film]:
    return scrape_savoy(VENUE_ID, VENUE_NAME, VENUE_URL)
