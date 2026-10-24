import json
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, status TEXT, request TEXT, result TEXT, created_at TEXT);
            CREATE TABLE IF NOT EXISTS events (job_id TEXT, at TEXT, kind TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS feedback (job_id TEXT, at TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, expires REAL, payload TEXT);
            CREATE TABLE IF NOT EXISTS prefetch (profile_id TEXT PRIMARY KEY, expires REAL, payload TEXT);
            ''')

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def create(self, request):
        ident = str(uuid.uuid4())
        with self.connect() as db:
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?)', (ident, 'queued', json.dumps(request), '{}', now()))
        return ident

    def update(self, ident, status, result):
        with self.connect() as db:
            db.execute('UPDATE jobs SET status=?,result=? WHERE id=?', (status, json.dumps(result), ident))

    def get(self, ident):
        with self.connect() as db:
            row = db.execute('SELECT id,status,result,created_at FROM jobs WHERE id=?', (ident,)).fetchone()
        return None if row is None else dict(search_id=row[0], status=row[1], **json.loads(row[2]), created_at=row[3])

    def pending(self):
        with self.connect() as db:
            return db.execute("SELECT id,request FROM jobs WHERE status='queued'").fetchall()

    def recover(self):
        # A crash may leave chargeable external runs in flight; never silently replay them.
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='interrupted' WHERE status='running'")

    def event(self, ident, kind, payload):
        with self.connect() as db:
            db.execute('INSERT INTO events VALUES (?,?,?,?)', (ident, now(), kind, json.dumps(payload)))

    def feedback(self, ident, payload):
        with self.connect() as db:
            db.execute('INSERT INTO feedback VALUES (?,?,?)', (ident, now(), json.dumps(payload)))

    def cached(self, key):
        import time
        with self.connect() as db:
            row = db.execute('SELECT payload FROM cache WHERE key=? AND expires>?', (key,time.time())).fetchone()
        return json.loads(row[0]) if row else None

    def cache(self, key, payload, ttl=300):
        import time
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)', (key,time.time()+ttl,json.dumps(payload)))

    def save_prefetch(self, profile_id, listings, ttl=6*3600):
        import time
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO prefetch VALUES (?,?,?)', (profile_id,time.time()+ttl,json.dumps(listings)))

    def prefetched(self, profile_id):
        import time
        with self.connect() as db:
            row = db.execute('SELECT payload FROM prefetch WHERE profile_id=? AND expires>?', (profile_id,time.time())).fetchone()
        return json.loads(row[0]) if row else []
