"""Public ESPN adapter plus strict, transactional CSV import."""
import csv
import io
import json
import math
import re
import urllib.request
import urllib.parse
import unicodedata
from datetime import datetime, timedelta, timezone
from model import instant
from store import now, put

BASE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/wnba'
KINDS = {'logs': ['player_id','id','game_at','available_at','minutes','points','appeared','source_url'],
         'schedule': ['player_id','id','game_at','opponent','home','source_url'],
         'news': ['player_id','id','published_at','title','text','status','confirmed','source_url'],
         'team_stats': ['player_id','id','published_at','team','metric','value','source_url']}

def source_url(value):
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('A public http(s) source_url without credentials is required.')
    return value

def boolean(value):
    if str(value).lower() not in ('true','false','1','0'):
        raise ValueError('Boolean fields must be true/false or 1/0.')
    return str(value).lower() in ('true','1')

def number(value, low, high, integer=False):
    try:
        n = float(value)
    except (TypeError,ValueError) as exc:
        raise ValueError('Enter a valid number.') from exc
    if not math.isfinite(n) or not low <= n <= high or (integer and not n.is_integer()):
        raise ValueError(f'Number must be {low}–{high}' + (' and an integer.' if integer else '.'))
    return int(n) if integer else n

def import_csv(db, kind, contents):
    if kind not in KINDS:
        raise ValueError('Unknown import type.')
    reader = csv.DictReader(io.StringIO(contents))
    if not reader.fieldnames or not set(KINDS[kind]) <= set(reader.fieldnames):
        raise ValueError('Required columns: ' + ', '.join(KINDS[kind]))
    known = {r[0] for r in db.execute('SELECT id FROM players')}
    parsed = []
    for line, row in enumerate(reader, 2):
        try:
            if len(parsed) >= 20000:
                raise ValueError('Import limit is 20,000 rows.')
            if row['player_id'] not in known or not row['id'].strip():
                raise ValueError('Unknown player_id or missing record id.')
            r = {k: (v.strip() if v is not None else '') for k,v in row.items() if k is not None}
            r['source_url'] = source_url(r['source_url'])
            r['retrieved_at'] = now()
            if kind in ('logs','schedule'):
                instant(r['game_at'])
            if kind == 'logs':
                instant(r['available_at'])
                if instant(r['available_at']) < instant(r['game_at']):
                    raise ValueError('A game result cannot be available before its game.')
                if instant(r['available_at']) > instant(now()) or instant(r['game_at']) > instant(now()):
                    raise ValueError('Game logs must be historical, with availability at or before now.')
                r['minutes'] = number(r['minutes'], 0, 70)
                r['points'] = number(r['points'], 0, 150, True)
                r['appeared'] = boolean(r['appeared'])
                if not r['appeared'] and (r['minutes'] or r['points']):
                    raise ValueError('A missed game must have zero minutes and points; it is excluded from scoring.')
                if r['appeared'] and not r['minutes']:
                    raise ValueError('An appearance needs positive minutes.')
            if kind == 'schedule':
                r['home'] = boolean(r['home'])
            if kind in ('news','team_stats'):
                instant(r['published_at'])
                if instant(r['published_at']) > instant(now()):
                    raise ValueError('Publication timestamp cannot be in the future.')
            if kind == 'news':
                if r['status'] not in ('available','questionable','out','unknown'):
                    raise ValueError('Status must be available, questionable, out or unknown.')
                r['confirmed'] = boolean(r['confirmed'])
                r['minutes_cap'] = number(r['minutes_cap'], 0, 70) if r.get('minutes_cap') else None
            if kind == 'team_stats':
                r['value'] = number(r['value'], -10000, 10000)
            if kind == 'logs':
                existing = db.execute("SELECT payload FROM records WHERE mode='live' AND kind='logs' AND player_id=? AND record_id=?",(r['player_id'],r['id'])).fetchone()
                if existing:
                    old = json.loads(existing[0])
                    if any(old.get(k) != r.get(k) for k in ('game_at','available_at','minutes','points','appeared')):
                        raise ValueError('Existing game log snapshots cannot be revised in place. Use a new database for corrected historical data; preserve the original snapshot for audit.')
                if any(x['player_id']==r['player_id'] and x['id']==r['id'] for x in parsed):
                    raise ValueError('Duplicate player/game ID within the CSV.')
            parsed.append(r)
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f'Row {line}: {exc}') from exc
    if not parsed:
        raise ValueError('The CSV contains no records.')
    for r in parsed:
        put(db, 'live', kind, r['player_id'], r['id'], r)
    db.commit()
    return len(parsed)

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent':'WNBA-Personal-Forecast/1.0','Accept':'application/json'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)

def normalize(name):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', name).lower())

def refresh(db, history_days=0):
    """No injury inference: availability is sourced via manual report imports only.

    Boxscores use retrieval time for available_at; this deliberately prevents
    retrospectively fetched final statistics leaking into historical backtests.
    """
    tracked = list(db.execute('SELECT * FROM players WHERE tracked=1'))
    teams = fetch(BASE+'/teams')['sports'][0]['leagues'][0]['teams']
    identity = {}
    for entry in teams:
        team = entry['team']
        roster = fetch(BASE+f"/teams/{team['id']}/roster")
        for athlete in roster.get('athletes', []):
            # Some ESPN sports group athletes by position.
            athletes = athlete.get('items', [athlete])
            for a in athletes:
                identity[normalize(a.get('fullName', a.get('displayName','')))] = (str(a['id']), str(team['id']))
    matched = []
    for player in tracked:
        match = identity.get(normalize(player['name']))
        if match:
            db.execute('UPDATE players SET espn_id=?,team_id=? WHERE id=?', (*match,player['id']))
            matched.append((dict(player), *match))
    if not matched:
        raise ValueError('No tracked players matched current ESPN rosters. Import stable IDs via CSV instead.')
    timestamp = now()
    count = 0
    # Build new schedule first; replace only after all required requests succeed.
    schedule = []
    logs = []
    for offset in range(-history_days, 15):
        date = (datetime.now(timezone.utc)+timedelta(days=offset)).strftime('%Y%m%d')
        url = BASE+'/scoreboard?dates='+date
        board = fetch(url)
        for event in board.get('events', []):
            competition = event['competitions'][0]
            competitors = competition['competitors']
            done = competition.get('status',event.get('status',{})).get('type',{}).get('completed',False)
            involved = [(p,aid,tid) for p,aid,tid in matched if tid in [str(c['team']['id']) for c in competitors]]
            if not involved:
                continue
            if not done and instant(event['date']) > instant(timestamp):
                for p,aid,tid in involved:
                    other = next(c for c in competitors if str(c['team']['id']) != tid)
                    own = next(c for c in competitors if str(c['team']['id']) == tid)
                    schedule.append((p['id'],event['id'], {'id':event['id'],'game_at':event['date'],'opponent':other['team']['displayName'], 'home':own['homeAway']=='home','source_url':url,'retrieved_at':timestamp}))
            elif done and history_days:
                summary_url = BASE+'/summary?event='+str(event['id'])
                summary = fetch(summary_url)
                for team_box in summary.get('boxscore',{}).get('players',[]):
                    for group in team_box.get('statistics',[]):
                        labels = [s.upper() for s in group.get('labels',[])]
                        for box in group.get('athletes',[]):
                            for p,aid,tid in involved:
                                if str(box.get('athlete',{}).get('id')) != aid:
                                    continue
                                stats = dict(zip(labels, box.get('stats',[])))
                                if box.get('didNotPlay') or not stats.get('MIN'):
                                    minutes,points,appeared = 0,0,False
                                else:
                                    parts = stats['MIN'].split(':')
                                    minutes = float(parts[0]) + (float(parts[1])/60 if len(parts)>1 else 0)
                                    points = int(stats['PTS'])
                                    appeared = minutes > 0
                                logs.append((p['id'],event['id'],{'id':event['id'],'game_at':event['date'],'available_at':timestamp,'retrieved_at':timestamp,'source_url':summary_url,'minutes':minutes,'points':points,'appeared':appeared,'opponent':next(c['team']['displayName'] for c in competitors if str(c['team']['id'])!=tid)}))
    for p,aid,tid in matched:
        # Preserve user-imported schedule records; replace only the ESPN cache.
        for r in db.execute("SELECT record_id,payload FROM records WHERE mode='live' AND kind='schedule' AND player_id=?", (p['id'],)).fetchall():
            if json.loads(r['payload']).get('source_url','').startswith(BASE):
                db.execute("DELETE FROM records WHERE mode='live' AND kind='schedule' AND player_id=? AND record_id=?", (p['id'],r['record_id']))
    for player_id, ident, payload in schedule:
        put(db,'live','schedule',player_id,ident,payload)
        count += 1
    for player_id, ident, payload in logs:
        # Preserve earliest observed snapshot rather than rewriting its publication time.
        if not db.execute("SELECT 1 FROM records WHERE mode='live' AND kind='logs' AND player_id=? AND record_id=?", (player_id,ident)).fetchone():
            put(db,'live','logs',player_id,ident,payload)
            count += 1
    db.execute("INSERT OR REPLACE INTO settings VALUES ('last_refresh',?)", (timestamp,))
    db.commit()
    return {'records':count, 'matched_players':len(matched), 'unmatched':[p['name'] for p in tracked if not identity.get(normalize(p['name']))], 'retrieved_at':timestamp}
