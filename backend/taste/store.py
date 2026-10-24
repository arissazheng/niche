import uuid
from sourcing.store import Store, now
from .models import Profile, TasteImage

# Persists taste state alongside sourcing jobs in the same SQLite file.
# SpacetimeDB becomes the live, subscribed copy (see spacetime/README.md); this stays the API's record.


class TasteStore:
    def __init__(self, store: Store):
        self.store = store
        with store.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, data TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS images (id TEXT PRIMARY KEY, profile_id TEXT, data TEXT, created_at TEXT);
            ''')

    def create_profile(self, onboarding):
        profile = Profile(id=str(uuid.uuid4()), onboarding=onboarding, updated_at=now())
        self.save_profile(profile)
        return profile

    def save_profile(self, profile: Profile):
        profile.updated_at = now()
        with self.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO profiles VALUES (?,?,?)',
                (profile.id, profile.model_dump_json(), profile.updated_at))
        return profile

    def profile(self, ident) -> Profile | None:
        with self.store.connect() as db:
            row = db.execute('SELECT data FROM profiles WHERE id=?', (ident,)).fetchone()
        return None if row is None else Profile.model_validate_json(row[0])

    def save_image(self, image: TasteImage):
        with self.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO images VALUES (?,?,?,?)',
                (image.id, image.profile_id, image.model_dump_json(), image.created_at))
        return image

    def image(self, ident) -> TasteImage | None:
        with self.store.connect() as db:
            row = db.execute('SELECT data FROM images WHERE id=?', (ident,)).fetchone()
        return None if row is None else TasteImage.model_validate_json(row[0])

    def images(self, profile_id) -> list[TasteImage]:
        with self.store.connect() as db:
            rows = db.execute('SELECT data FROM images WHERE profile_id=? ORDER BY created_at', (profile_id,)).fetchall()
        return [TasteImage.model_validate_json(r[0]) for r in rows]

    def delete_image(self, ident):
        with self.store.connect() as db:
            db.execute('DELETE FROM images WHERE id=?', (ident,))

    def event(self, profile_id, kind, payload):
        self.store.event(profile_id, kind, payload)
