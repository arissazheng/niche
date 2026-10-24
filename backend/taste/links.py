"""Reading product links pasted into the shopping chat ("find me something similar to <url>").

Pages are fetched with sourcing.safe_fetch (public hosts only, size-capped) and reduced to the metadata link
previews use: Open Graph / Twitter tags, <title>, and schema.org Product JSON-LD. Page text is untrusted.
"""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from pydantic import BaseModel
from sourcing import safe_fetch
from sourcing.claude import fetch_image

MAX_LINKS = 2
MAX_HTML_BYTES = 2 * 1024 * 1024
URL = re.compile(r'https?://[^\s<>"\'`]+', re.I)


def extract_urls(text, limit=MAX_LINKS):
    urls = []
    for match in URL.findall(text or ''):
        url = match.rstrip('.,;:!?)]}\'"')
        if url not in urls:
            urls.append(url)
    return urls[:limit]


class _Meta(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta, self.title, self.ld = {}, '', []
        self._in_title = self._in_ld = False
        self._ld_text = ''

    def handle_starttag(self, tag, attrs):
        attrs = {k.lower(): v for k, v in attrs if v is not None}
        if tag == 'meta':
            key = (attrs.get('property') or attrs.get('name') or '').lower()
            if key and 'content' in attrs and key not in self.meta:
                self.meta[key] = attrs['content'].strip()
        elif tag == 'title':
            self._in_title = True
        elif tag == 'script' and attrs.get('type', '').lower() == 'application/ld+json':
            self._in_ld, self._ld_text = True, ''

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False
        elif tag == 'script' and self._in_ld:
            self._in_ld = False
            self.ld.append(self._ld_text)

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()
        if self._in_ld:
            self._ld_text += data


def _ld_product(blocks):
    def walk(node):
        if isinstance(node, list):
            for item in node:
                yield from walk(item)
        elif isinstance(node, dict):
            kind = node.get('@type')
            if kind == 'Product' or (isinstance(kind, list) and 'Product' in kind):
                yield node
            yield from walk(node.get('@graph', []))
    for text in blocks:
        try:
            data = json.loads(text)
        except ValueError:
            continue
        for product in walk(data):
            return product
    return {}


def _first_image(value):
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get('url') or value.get('contentUrl')
    return value if isinstance(value, str) else None


def parse_meta(html, base_url):
    """Title, description, image URL and site name from a product page (Open Graph, Twitter, JSON-LD, <title>)."""
    parser = _Meta()
    try:
        parser.feed(html)
    except Exception:  # HTMLParser tolerates most junk; never let a page break the chat
        pass
    meta, product = parser.meta, _ld_product(parser.ld)
    title = product.get('name') or meta.get('og:title') or meta.get('twitter:title') or parser.title
    description = (product.get('description') or meta.get('og:description') or meta.get('twitter:description')
                   or meta.get('description'))
    image = _first_image(product.get('image')) or meta.get('og:image') or meta.get('twitter:image')
    site = meta.get('og:site_name') or (urlsplit(base_url).hostname or '').removeprefix('www.')
    clean = lambda s, n: re.sub(r'\s+', ' ', s).strip()[:n] if isinstance(s, str) else None
    # Product evidence: schema.org Product data, an og:type of product, or product price tags.
    is_product = bool(product) or 'product' in meta.get('og:type', '').lower() or any(
        k in meta for k in ('product:price:amount', 'og:price:amount', 'product:price'))
    return {'title': clean(title, 200), 'description': clean(description, 600),
            'image_url': urljoin(base_url, image) if image else None, 'site': clean(site, 80), 'product': is_product}


class LinkedItem(BaseModel):
    url: str
    site: str | None = None
    title: str | None = None
    description: str | None = None
    readable: bool = False
    image: dict | None = None  # Claude image block; not sent to the browser

    def summary(self):
        return self.model_dump(exclude={'image'})


async def read_link(url) -> LinkedItem:
    async with safe_fetch.client() as http:
        fetched = await safe_fetch.fetch(http, url, MAX_HTML_BYTES)
        if not fetched or 'html' not in fetched[2].lower():
            return LinkedItem(url=url, site=urlsplit(url).hostname)
        body, final_url, _ = fetched
        meta = parse_meta(body.decode('utf-8', errors='replace'), final_url)
        image = await fetch_image(http, meta['image_url']) if meta['image_url'] else None
    return LinkedItem(url=url, site=meta['site'], title=meta['title'], description=meta['description'],
                      # Titles alone (homepages, search pages, parked domains) aren't evidence of a product: need a
                      # product photo, or product markup plus a title.
                      readable=bool(image or (meta['product'] and meta['title'])), image=image)
