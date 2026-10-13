"""Public ESPN adapter plus strict, transactional CSV import."""
import csv
import io
import json
import math
import re
import urllib.request
import urllib.parse
import unicodedata
import hashlib
import time
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timedelta, timezone
from model import instant
from game_scope import exclusion_reason
from store import now, put

BASE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/wnba'
GAMELOG_BASE = 'https://site.web.api.espn.com/apis/common/v3/sports/basketball/wnba/athletes'
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

class ImportCancelled(Exception):
    pass

class ImportControl:
    def __init__(self, progress=None, seconds=120):
        self.deadline=time.monotonic()+seconds
        self.cancelled=threading.Event()
        self.progress=progress or (lambda message,current,total: None)

    def check(self):
        if self.cancelled.is_set():
            raise ImportCancelled('Import cancelled. Existing game records were preserved.')
        if time.monotonic()>=self.deadline:
            raise TimeoutError('ESPN import exceeded two minutes. Existing game records were preserved.')

def fetch(url):
    started=time.monotonic()
    req = urllib.request.Request(url, headers={'User-Agent':'WNBA-Personal-Forecast/1.0','Accept':'application/json'})
    with urllib.request.urlopen(req, timeout=10) as response:
        chunks=[]
        size=0
        while True:
            if time.monotonic()-started>20:
                raise TimeoutError('ESPN response took too long.')
            chunk=response.read1(65536)
            if not chunk:
                break
            chunks.append(chunk)
            size+=len(chunk)
            if size>8*1024*1024:
                raise ValueError('ESPN response was larger than expected.')
        return json.loads(b''.join(chunks))

def fetch_many(urls, control=None, label='Downloading ESPN records'):
    """Bounded parallel requests; cancellation/deadline never waits on executor exit."""
    control=control or ImportControl()
    control.check()
    control.progress(label,0,len(urls))
    results=[None]*len(urls)
    pool=ThreadPoolExecutor(max_workers=3,thread_name_prefix='espn')
    pending={}
    try:
        pending={pool.submit(fetch,url):i for i,url in enumerate(urls)}
        done_count=0
        while pending:
            control.check()
            finished,_=wait(pending,timeout=.25,return_when=FIRST_COMPLETED)
            for future in finished:
                control.check()
                index=pending.pop(future)
                results[index]=future.result()
                done_count+=1
                control.progress(label,done_count,len(urls))
        return results
    finally:
        for future in pending:
            future.cancel()
        pool.shutdown(wait=False,cancel_futures=True)

def normalize(name):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', name).lower())

def resolve_players(db, control=None, reuse_ids=False):
    """Resolve identities from public roster IDs without collecting personal data."""
    tracked = list(db.execute('SELECT * FROM players WHERE tracked=1'))
    if not tracked:
        raise ValueError('Track at least one player before importing.')
    if reuse_ids and all(p['espn_id'] for p in tracked):
        return [(dict(p),p['espn_id'],p['team_id']) for p in tracked],[]
    control=control or ImportControl()
    teams = fetch_many([BASE+'/teams'],control,'Connecting to ESPN')[0]['sports'][0]['leagues'][0]['teams']
    identity = {}
    rosters=fetch_many([BASE+f"/teams/{entry['team']['id']}/roster" for entry in teams],control,'Finding player IDs in team rosters')
    for entry,roster in zip(teams,rosters):
        team = entry['team']
        for athlete in roster.get('athletes', []):
            # Some ESPN sports group athletes by position.
            athletes = athlete.get('items', [athlete])
            for a in athletes:
                identity[normalize(a.get('fullName', a.get('displayName','')))] = (str(a['id']), str(team['id']))
    matched = []
    for player in tracked:
        match = identity.get(normalize(player['name']))
        if match:
            matched.append((dict(player), *match))
    if not matched:
        raise ValueError('No tracked players matched current ESPN rosters. Import stable IDs via CSV instead.')
    return matched, [p['name'] for p in tracked if not identity.get(normalize(p['name']))]

def persist_identities(db, matched):
    # Acquire the SQLite write lock after network requests, keeping reads responsive.
    for player,aid,tid in matched:
        db.execute('UPDATE players SET espn_id=?,team_id=? WHERE id=?',(aid,tid,player['id']))

def linked_athlete_id(athlete):
    if athlete.get('id'):
        return str(athlete['id'])
    # The verified public injury feed omits athlete.id but includes player links.
    for link in athlete.get('links',[]):
        parsed=urllib.parse.urlsplit(link.get('href',''))
        if parsed.hostname in ('www.espn.com','espn.com'):
            match=re.search(r'/player/(?:[a-z]+/)?_/id/(\d+)(?:/|$)',parsed.path)
            if match:
                return match[1]
    return None

def news_matches(article, player, espn_id):
    # The upstream athlete query parameter was verified to be ignored.
    tagged = any(str(c.get('athleteId',c.get('athlete',{}).get('id','')))==espn_id
                 for c in article.get('categories',[]) if c.get('type')=='athlete')
    named = normalize(player['name']) in normalize(article.get('headline','')+' '+article.get('description',''))
    return tagged or named

def news_records(matched, articles, injury_groups, timestamp):
    output=[]
    skipped=0
    for player,aid,tid in matched:
        for article in articles:
            if not news_matches(article,player,aid):
                continue
            try:
                published=article['published']
                modified=article.get('lastModified',published)
                if instant(published)>instant(timestamp) or instant(modified)>instant(timestamp):
                    raise ValueError('Future report')
                url=source_url(article['links']['web']['href'])
                if urllib.parse.urlsplit(url).hostname not in ('www.espn.com','espn.com'):
                    raise ValueError('Unexpected article source')
                ident=f"espn-article-{article['id']}-{modified}"
                payload={'id':ident,'published_at':published,'source_modified_at':modified,'retrieved_at':timestamp,
                         'source_url':url,'feed_url':BASE+'/news?limit=100','provider':'ESPN','report_kind':'article',
                         'title':article['headline'],'text':article.get('description',''),
                         'status':'unknown','confirmed':False,'minutes_cap':None}
                output.append((player['id'],ident,payload))
            except (ValueError,KeyError,TypeError):
                skipped+=1
        for group in injury_groups:
            for injury in group.get('injuries',[]):
                if linked_athlete_id(injury.get('athlete',{}))!=aid:
                    continue
                try:
                    published=injury['date']
                    if instant(published)>instant(timestamp):
                        raise ValueError('Future report')
                    raw_status=injury.get('status','')
                    status={'out':'out','doubtful':'questionable','questionable':'questionable',
                            'day-to-day':'questionable','probable':'questionable','available':'available',
                            'active':'available'}.get(raw_status.casefold(),'unknown')
                    # Public basketball injury descriptions only. No extrapolation.
                    text=injury.get('longComment') or injury.get('shortComment') or 'No public detail supplied.'
                    injury_type=injury.get('details',{}).get('type')
                    # Preserve revisions even if ESPN reuses its report ID/date.
                    digest=hashlib.sha256(json.dumps({'text':text,'status':raw_status,'type':injury_type},sort_keys=True).encode()).hexdigest()[:12]
                    ident=f"espn-injury-{injury['id']}-{published}-{digest}"
                    payload={'id':ident,'published_at':published,'retrieved_at':timestamp,
                             'source_url':BASE+'/injuries?limit=100','provider':'ESPN','report_kind':'injury',
                             'title':f"ESPN report: {player['name']} — {raw_status or 'status unknown'}",
                             'text':text,'status':status,'reported_status':raw_status,
                             'injury_type':injury_type,'confirmed':status!='unknown','minutes_cap':None}
                    output.append((player['id'],ident,payload))
                except (ValueError,KeyError,TypeError):
                    skipped+=1
    return output,skipped

def refresh_news(db, matched=None):
    if matched is None:
        matched,unmatched=resolve_players(db)
    else:
        unmatched=[]
    timestamp=now()
    article_feed=fetch(BASE+'/news?limit=100')
    injury_feed=fetch(BASE+'/injuries?limit=100')
    if not isinstance(article_feed.get('articles'),list) or not isinstance(injury_feed.get('injuries'),list):
        raise ValueError('Unexpected public news response')
    items,skipped=news_records(matched,article_feed['articles'],injury_feed['injuries'],timestamp)
    persist_identities(db,matched)
    added=0
    for pid,ident,payload in items:
        if not db.execute("SELECT 1 FROM records WHERE mode='live' AND kind='news' AND player_id=? AND record_id=?",(pid,ident)).fetchone():
            put(db,'live','news',pid,ident,payload)
            added+=1
    db.execute("INSERT OR REPLACE INTO settings VALUES ('last_news_refresh',?)",(timestamp,))
    db.execute("DELETE FROM settings WHERE key='news_refresh_error'")
    db.commit()
    return {'reports':added,'matched_players':len(matched),'unmatched':unmatched,'skipped_reports':skipped,'retrieved_at':timestamp}

def parse_gamelog(data, timestamp, season, url):
    if not isinstance(data.get('seasonTypes'),list) or not isinstance(data.get('events'),dict):
        raise ValueError('Unexpected game-log response')
    labels=[s.upper() for s in data.get('labels',[])]
    if 'MIN' not in labels or 'PTS' not in labels:
        raise ValueError('Game logs missing scoring columns')
    rows={}
    skipped=0
    for period in data['seasonTypes']:
        period_name=period.get('displayName','').lower()
        if 'regular season' not in period_name and 'postseason' not in period_name:
            continue
        for category in period.get('categories',[]):
            for entry in category.get('events',[]):
                try:
                    ident=str(entry['eventId'])
                    event=data['events'][ident]
                    if exclusion_reason(event):
                        continue
                    start=event['gameDate']
                    if instant(start)>=instant(timestamp):
                        continue
                    stats=dict(zip(labels,entry['stats']))
                    parts=stats['MIN'].split(':')
                    minutes=number(parts[0],0,70)+(number(parts[1],0,59)/60 if len(parts)==2 else 0)
                    points=number(stats['PTS'],0,150,True)
                    if minutes==0 and points:
                        raise ValueError('Scoring with no minutes')
                    rows[ident]={'id':ident,'game_at':start,'available_at':timestamp,'retrieved_at':timestamp,
                                 'source_url':url,'minutes':minutes,'points':points,'appeared':minutes>0,
                                 'opponent':event.get('opponent',{}).get('displayName','Unknown'),
                                 'home':event.get('atVs')=='vs','season':season,
                                 'season_type':'postseason' if 'postseason' in period_name else 'regular'}
                except (ValueError,KeyError,TypeError):
                    skipped+=1
    return list(rows.values()),skipped

def load_history(db, seasons, control=None):
    control=control or ImportControl()
    matched,unmatched=resolve_players(db,control,reuse_ids=True)
    timestamp=now()
    rows=[]
    skipped=0
    tasks=[(player,season,f'{GAMELOG_BASE}/{aid}/gamelog?season={season}') for player,aid,tid in matched for season in seasons]
    downloaded=fetch_many([t[2] for t in tasks],control,'Downloading player-season game logs')
    timestamp=now()
    for (player,season,url),payload in zip(tasks,downloaded):
        control.check()
        parsed,missing=parse_gamelog(payload,timestamp,season,url)
        skipped+=missing
        rows.extend((player['id'],r) for r in parsed)
    control.check()
    control.progress('Saving verified game snapshots',0,len(rows))
    added=0
    persist_identities(db,matched)
    for pid,r in rows:
        if not db.execute("SELECT 1 FROM records WHERE mode='live' AND kind='logs' AND player_id=? AND record_id=?",(pid,r['id'])).fetchone():
            put(db,'live','logs',pid,r['id'],r)
            added+=1
    db.execute("INSERT OR REPLACE INTO settings VALUES ('last_history_refresh',?)",(timestamp,))
    control.check()
    db.commit()
    control.progress('Import complete',len(rows),len(rows))
    return {'records':added,'games_checked':len(rows),'matched_players':len(matched),'unmatched':unmatched,'seasons':seasons,'skipped_rows':skipped,'retrieved_at':timestamp}

def refresh(db, history_days=0):
    """Game snapshots use retrieval times; public injury records retain report times."""
    matched,unmatched=resolve_players(db)
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
    persist_identities(db,matched)
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
    result={'records':count, 'matched_players':len(matched), 'unmatched':unmatched, 'retrieved_at':timestamp}
    try:
        result['news']=refresh_news(db,matched)
    except Exception:
        warning='Public ESPN news/injury refresh failed. Earlier reports are retained and still checked for staleness. No missing report implies an injury or clearance.'
        db.execute("INSERT OR REPLACE INTO settings VALUES ('news_refresh_error',?)",(warning,))
        db.commit()
        result['news_warning']=warning
    return result
