import sqlite3
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

STARTERS = [("aja-wilson", "A’ja Wilson"), ('breanna-stewart', 'Breanna Stewart'),
            ('sabrina-ionescu', 'Sabrina Ionescu'), ('kelsey-plum', 'Kelsey Plum'),
            ('kelsey-mitchell', 'Kelsey Mitchell')]

def now():
    return datetime.now(timezone.utc).isoformat()

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()

def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30, factory=ClosingConnection)
    db.row_factory = sqlite3.Row
    db.executescript('''
    CREATE TABLE IF NOT EXISTS players(id TEXT PRIMARY KEY, name TEXT NOT NULL, tracked INTEGER DEFAULT 1, espn_id TEXT, team_id TEXT);
    CREATE TABLE IF NOT EXISTS records(mode TEXT, kind TEXT, player_id TEXT, record_id TEXT, payload TEXT, PRIMARY KEY(mode,kind,player_id,record_id));
    CREATE TABLE IF NOT EXISTS forecasts(id INTEGER PRIMARY KEY, mode TEXT, player_id TEXT, event_id TEXT, created_at TEXT, payload TEXT);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    ''')
    for ident, name in STARTERS:
        db.execute('INSERT OR IGNORE INTO players(id,name) VALUES (?,?)', (ident, name))
    db.execute("INSERT OR IGNORE INTO settings VALUES ('mode','demo')")
    db.commit()
    return db

def records(db, mode, kind, player_id=None):
    sql = 'SELECT payload FROM records WHERE mode=? AND kind=?'
    args = [mode, kind]
    if player_id:
        sql += ' AND player_id=?'
        args.append(player_id)
    return [json.loads(r[0]) for r in db.execute(sql, args)]

def put(db, mode, kind, player_id, record_id, payload):
    db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?,?)', (mode, kind, player_id, record_id, json.dumps(payload)))

def seed_demo(db):
    if db.execute("SELECT 1 FROM settings WHERE key='demo_seeded'").fetchone():
        return
    rng = random.Random(42)
    at = datetime.now(timezone.utc)
    for j, (ident, name) in enumerate(STARTERS):
        for season in (at.year - 1, at.year):
            for i in range(32):
                # Synthetic dates are always in the past; these are not actual WNBA fixtures.
                game_at = at - timedelta(days=(at.year - season) * 365 + (33-i) * 3)
                minutes = round(max(18, min(39, rng.gauss(33, 3))), 1)
                appeared = i != 12
                payload = {'id': f'demo-{season}-{i}', 'game_at': game_at.isoformat(),
                           'available_at': (game_at + timedelta(hours=3)).isoformat(),
                           'retrieved_at': at.isoformat(), 'source_url': None,
                           'minutes': minutes if appeared else 0, 'points': max(0, round(rng.gauss(minutes * (.78-j*.055), 6))) if appeared else 0,
                           'appeared': appeared, 'opponent': 'Synthetic opponent', 'home': i % 2 == 0}
                put(db, 'demo', 'logs', ident, payload['id'], payload)
        if j != 4:
            event = {'id': f'demo-next-{j}', 'game_at': (at + timedelta(days=1, hours=j)).isoformat(),
                     'opponent': 'Demo opponent', 'home': j % 2 == 0, 'retrieved_at': at.isoformat(), 'source_url': None}
            put(db, 'demo', 'schedule', ident, event['id'], event)
        if j in (0, 2, 3):
            status = {0:'available', 2:'questionable', 3:'out'}[j]
            report = {'id': f'demo-news-{j}', 'published_at': (at-timedelta(hours=2)).isoformat(),
                      'retrieved_at': at.isoformat(), 'source_url': None, 'status': status,
                      'confirmed': True, 'minutes_cap': None, 'title': f'SYNTHETIC example: {status}',
                      'text': 'Fictional report to demonstrate the availability timeline. This is not a real injury or team announcement.'}
            put(db, 'demo', 'news', ident, report['id'], report)
    db.execute("INSERT INTO settings VALUES ('demo_seeded',?)", (now(),))
    db.commit()
