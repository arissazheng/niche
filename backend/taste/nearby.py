"""Shops near you: real nearby stores worth checking for a search, from Gemini with Grounding with Google Maps.

Only the shopper's ZIP code and the search brief are sent, and only when they turned the feature on. Gemini can't see
store inventory, so these are shops whose kind fits the search (vintage, consignment, boutiques), not stock checks.
Each shop keeps the Google Maps place link Gemini cites for it; Google's terms require showing it next to the shop.
"""
import asyncio
import logging
import re
import time
import httpx

log = logging.getLogger(__name__)
API = 'https://generativelanguage.googleapis.com/v1beta/interactions'
CACHE_SECONDS = 6 * 3600
PROMPT = '''Suggest up to 4 real clothing shops near US ZIP code {zip} that are worth visiting for: {brief}
Prefer independent boutiques, vintage, thrift and consignment shops over chain and department stores, and never
suggest Shein, Fashion Nova or other fast-fashion pop-ups. Only shops that exist on Google Maps, within about 10 miles.
Answer with one shop per line, exactly "Shop name — why it fits (under 15 words)". No other text.'''


class NearbyError(Exception):
    pass


class Nearby:
    def __init__(self, settings):
        self.settings = settings
        self.cache: dict[tuple, tuple[float, list]] = {}
        self.running: dict[tuple, asyncio.Task] = {}  # lookups started with the search, awaited by the results page

    def warm(self, zip_code, brief):
        """Start the lookup as the search starts, so it's ready when the results are."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # called outside the event loop: the results page starts it instead
        task = asyncio.ensure_future(self.shops(zip_code, brief))
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)  # errors surface on await

    @property
    def enabled(self):
        return bool(self.settings.gemini_api_key)

    async def shops(self, zip_code, brief):
        key = (zip_code, brief.lower().strip())
        hit = self.cache.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
        if key not in self.running:
            self.running[key] = asyncio.ensure_future(self._lookup(key, zip_code, brief))
            self.running[key].add_done_callback(lambda _: self.running.pop(key, None))
        return await asyncio.shield(self.running[key])

    async def _lookup(self, key, zip_code, brief):
        async with httpx.AsyncClient(timeout=60) as http:
            response = await http.post(API, headers={'x-goog-api-key': self.settings.gemini_api_key}, json={
                'model': self.settings.gemini_model,
                'input': PROMPT.format(zip=zip_code, brief=brief[:300]),
                'tools': [{'type': 'google_maps'}]})
        data = response.json()
        if 'error' in data:
            raise NearbyError(data['error'].get('code') or 'gemini_error')
        shops = parse(data)
        self.cache[key] = (time.time(), shops)
        return shops


def parse(data):
    """Lines of "Name — why", each paired with the Google Maps place Gemini cited for it. Uncited lines are dropped:
    a shop with no Maps source may not exist."""
    text, places = '', []
    for step in data.get('steps') or []:
        if step.get('type') != 'model_output':
            continue
        for block in step.get('content') or []:
            if block.get('type') == 'text':
                text += block.get('text') or ''
                # Each place is cited twice: the place itself, and "Review of …"; keep the place.
                places += [{**a, 'name': re.sub(r'\s+-\s+Google Maps$', '', a.get('name') or '')}
                           for a in block.get('annotations') or []
                           if a.get('type') == 'place_citation' and a.get('url')
                           and not (a.get('name') or '').startswith('Review of')]
    shops = []
    for line in text.splitlines():
        match = re.match(r'^\s*(?:[-*\d.]+\s*)?\**(.+?)\**\s+[—–-]\s+(.+)$', line)
        if not match:
            continue
        name, why = match.group(1).strip(), match.group(2).strip()
        place = next((p for p in places if similar(p.get('name') or '', name)), None)
        if place:
            shops.append({'name': place.get('name') or name, 'why': why[:160], 'maps_url': place['url']})
    return shops[:4]


def similar(a, b):
    a, b = re.sub(r'[^a-z0-9]', '', a.lower()), re.sub(r'[^a-z0-9]', '', b.lower())
    return bool(a and b) and (a in b or b in a)
