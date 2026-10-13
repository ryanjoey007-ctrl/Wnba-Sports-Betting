from datetime import datetime, timedelta, timezone
from app import create_app
from game_scope import exclusion_reason
from ingest import parse_gamelog, GAMELOG_BASE
from model import eligible, forecast, evaluate
from store import connect, put, records

def test_nested_public_flags_and_event_note():
    assert exclusion_reason({'team':{'isAllStar':True}})=='All-Star game'
    assert exclusion_reason({'eventNote':'AT&T WNBA All-Star Game'})=='All-Star game'
    assert exclusion_reason({'isAllStar':False,'team':{'isAllStar':False}}) is None
    assert exclusion_reason({'competition_type':'preseason'})=='Preseason game'

def test_existing_verified_espn_event_excluded_without_name_guessing():
    assert exclusion_reason({'id':'401857320','source_url':GAMELOG_BASE+'/3149391/gamelog?season=2026'})=='All-Star game'
    assert exclusion_reason({'id':'401857320','source_url':'https://example.com/my-csv'}) is None
    assert exclusion_reason({'opponent':'TEAM SOMETHING'}) is None

def test_parser_excludes_nested_flags_missing_top_level_flag():
    data={'labels':['MIN','PTS'],'events':{
        'regular':{'gameDate':'2026-07-13T01:00:00Z','opponent':{'displayName':'Opponent'}},
        'allstar':{'gameDate':'2026-07-26T00:30:00Z','eventNote':'AT&T WNBA All-Star Game','team':{'isAllStar':True}}},
        'seasonTypes':[{'displayName':'2026 Regular Season','categories':[{'events':[
            {'eventId':'regular','stats':['31','20']},{'eventId':'allstar','stats':['14','12']}]}]}]}
    rows,skipped=parse_gamelog(data,'2026-10-13T00:00:00Z',2026,GAMELOG_BASE+'/3149391/gamelog?season=2026')
    assert [r['id'] for r in rows]==['regular'] and skipped==0

def test_forecast_and_validation_ignore_exhibition_train_and_target():
    start=datetime(2026,5,1,tzinfo=timezone.utc)
    games=[{'id':str(i),'game_at':(start+timedelta(days=i*3)).isoformat(),
            'available_at':(start+timedelta(days=i*3,hours=3)).isoformat(),
            'appeared':True,'minutes':30,'points':20+i%3} for i in range(40)]
    cutoff='2026-12-01T00:00:00Z'
    star={**games[20],'id':'401857320','points':100,'source_url':GAMELOG_BASE+'/3149391/gamelog?season=2026'}
    assert forecast(games+[star],cutoff)==forecast(games,cutoff)
    assert evaluate(games+[star])['rows']==evaluate(games)['rows']
    assert evaluate(games+[star])['metrics']['excluded_games']==1
    assert len(eligible(games+[star],cutoff))==40

def test_detail_labels_existing_raw_record_without_changing_it(tmp_path):
    path=tmp_path/'old-data.sqlite3'
    app=create_app(str(path));client=app.test_client()
    current=datetime.now(timezone.utc)
    at=(current-timedelta(days=5)).isoformat()
    raw={'id':'401857320','game_at':at,'available_at':at,'retrieved_at':at,
         'appeared':True,'minutes':14,'points':12,'opponent':'TEAM COOP',
         'source_url':GAMELOG_BASE+'/3149391/gamelog?season=2026'}
    with connect(path) as db:
        put(db,'live','logs','aja-wilson',raw['id'],raw);db.commit()
    client.post('/api/mode',json={'mode':'live'},headers={'X-WNBA-Client':'1'})
    d=client.get('/api/player/aja-wilson').get_json()
    assert d['log_count']==1 and d['appearance_count']==0
    assert d['logs'][0]['exclusion_reason']=='All-Star game'
    assert d['calendar']['appearances']==0 and d['evaluation']['metrics']['excluded_games']==1
    with connect(path) as db:
        assert records(db,'live','logs','aja-wilson')==[raw]
