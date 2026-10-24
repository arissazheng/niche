"""Lookbook photos are served only through short-lived signed links, so a leaked photo URL stops working.

Stored image URLs stay plain (".../uploads/<id>.jpg"); every response that hands one to a browser signs it. Expiry is
rounded to the hour so a photo's link stays the same for a while and the browser can cache it.
"""
import hashlib
import hmac
import re
import secrets
import time
from pathlib import Path

VALID_FOR = 3600  # seconds; a link works for one to two hours
NAME = re.compile(r'^[0-9a-f-]{36}\.jpg$')


class Signer:
    def __init__(self, settings):
        self.key = self._key(Path(settings.upload_dir))

    @staticmethod
    def _key(upload_dir: Path):
        # Kept next to the uploads (outside them, so it's never served) and reused across restarts.
        path = upload_dir.parent / '.upload_key'
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(secrets.token_hex(32))
            path.chmod(0o600)
        return path.read_text().strip().encode()

    def _sig(self, name, expires):
        return hmac.new(self.key, f'{name}:{expires}'.encode(), hashlib.sha256).hexdigest()[:32]

    def sign(self, url):
        base, _, name = url.rpartition('/uploads/')
        if not base or not NAME.match(name):
            return url
        expires = (int(time.time()) // VALID_FOR + 2) * VALID_FOR
        return f'{base}/uploads/{name}?exp={expires}&sig={self._sig(name, expires)}'

    def valid(self, name, expires, sig):
        return (bool(NAME.match(name)) and expires > time.time()
                and hmac.compare_digest(self._sig(name, expires), sig or ''))

    def image(self, image: dict):
        return {**image, 'url': self.sign(image['url'])}
