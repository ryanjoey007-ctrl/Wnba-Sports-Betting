import csv
import io
from datetime import datetime,timedelta,timezone
import pytest
from app import create_app, availability
from store import connect, records, put

HEAD={'X-WNBA-Client':'1'}

@pytest.fixture
def client(tmp_path):
    app=create_app(str(tmp_path/'test.sqlite3'))
    app.config['TESTING']=True
    return app.test_client()

def csvfile(rows):
    out=io.StringIO()
    writer=csv.DictWriter(out,fieldnames=list(rows[0]))
    writer.writeheader();writer.writerows(rows)
    return {'file':(io.BytesIO(out.getvalue().encode()),'import.csv')}

def test_starting_players_demo_and_real_isolation(client):
    d=client.get('/api/dashboard').get_json()
    assert len(d['players'])==5 and d['mode']=='demo'
    out=next(p for p in d['players'] if p['id']=='kelsey-plum')
    assert out['availability']['status']=='out' and out['forecast'] is None
    assert next(p for p in d['players'] if p['id']=='kelsey-mitchell')['reason']=='No scheduled game'
    client.post('/api/mode',json={'mode':'live'},headers=HEAD)
    for p in client.get('/api/dashboard').get_json()['players']:
        assert p['forecast'] is None and p['availability']['status']=='unknown'

def test_add_remove_and_restore(client):
    p=client.post('/api/players',json={'name':'Alyssa Thomas'},headers=HEAD).get_json()
    assert p['id'].startswith('player-')
    client.delete('/api/players/'+p['id'],headers=HEAD)
    assert len(client.get('/api/dashboard').get_json()['players'])==5
    restored=client.post('/api/players',json={'name':'Alyssa Thomas'},headers=HEAD).get_json()
    assert restored['id']==p['id']

def test_csv_forecast_and_append_only_history(client):
    at=datetime.now(timezone.utc)
    rows=[{'player_id':'aja-wilson','id':str(i),'game_at':(at-timedelta(days=40-i)).isoformat(),
           'available_at':(at-timedelta(days=40-i,hours=-3)).isoformat(), 'minutes':30,'points':20+i%3,
           'appeared':'true','source_url':'https://www.wnba.com/test'} for i in range(30)]
    r=client.post('/api/import/logs',data=csvfile(rows),headers=HEAD)
    assert r.status_code==200
    schedule=[{'player_id':'aja-wilson','id':'future','game_at':(at+timedelta(days=1)).isoformat(), 'opponent':'Imported opponent','home':'true','source_url':'https://www.wnba.com/schedule'}]
    assert client.post('/api/import/schedule',data=csvfile(schedule),headers=HEAD).status_code==200
    client.post('/api/mode',json={'mode':'live'},headers=HEAD)
    detail=client.get('/api/player/aja-wilson?threshold=22.5').get_json()
    assert detail['forecast']['probabilities']['exactly']==0
    assert detail['evaluation']['metrics']['n']==25
    for _ in range(2):
        assert client.post('/api/forecasts',json={'threshold':22.5},headers=HEAD).get_json()['saved']==1
    history=client.get('/api/player/aja-wilson').get_json()['history']
    assert len(history)==2 and history[0]['id']!=history[1]['id']
    assert all(h['outcome']=='pending' and h['actual'] is None for h in history)
    assert all(h['forecast']['model_version']=='minutes-rate-v1' for h in history)
    rows[0]['points']=80
    assert client.post('/api/import/logs',data=csvfile(rows),headers=HEAD).status_code==400

def test_invalid_import_atomic_and_threshold(client):
    at=datetime.now(timezone.utc)-timedelta(days=2)
    row={'player_id':'aja-wilson','id':'valid','game_at':at.isoformat(),'available_at':(at+timedelta(hours=3)).isoformat(),'minutes':30,'points':20,'appeared':'true','source_url':'https://www.wnba.com/stats'}
    bad={**row,'id':'bad','points':-1}
    assert client.post('/api/import/logs',data=csvfile([row,bad]),headers=HEAD).status_code==400
    client.post('/api/mode',json={'mode':'live'},headers=HEAD)
    assert client.get('/api/player/aja-wilson').get_json()['logs']==[]
    assert client.get('/api/dashboard?threshold=nan').status_code==400

def test_sourced_out_conflicts_and_staleness(client):
    at=datetime.now(timezone.utc)
    base={'id':'n1','player_id':'aja-wilson','published_at':(at-timedelta(hours=2)).isoformat(),'status':'out','confirmed':True,'title':'Team statement','text':'Public report','source_url':'https://www.wnba.com/report','retrieved_at':at.isoformat(),'minutes_cap':None}
    assert availability([base],at.isoformat())['status']=='out'
    second={**base,'id':'n2','status':'available'}
    assert availability([base,second],at.isoformat())['conflict']
    assert availability([base,second],at.isoformat())['status']=='unknown'
    old={**base,'published_at':(at-timedelta(days=3)).isoformat()}
    assert availability([old],at.isoformat())['stale']
    assert availability([{**base,'confirmed':False}],at.isoformat())['status']=='unknown'

def test_answer_grounded_and_refresh_failure(client,monkeypatch):
    monkeypatch.delenv('LLM_API_KEY',raising=False)
    answer=client.post('/api/player/aja-wilson/ask',json={'question':'Why did it change?'},headers=HEAD).get_json()
    assert answer['demo'] and answer['facts'] and 'Stored' in answer['mode']
    def fail(*a,**k): raise OSError('network blocked')
    monkeypatch.setattr('app.refresh',fail)
    assert client.post('/api/refresh',json={},headers=HEAD).status_code==502
    assert client.get('/api/dashboard').get_json()['refresh_error']
    assert client.get('/api/player/aja-wilson').get_json()['logs']

def test_csrf_and_unknown_player(client):
    assert client.post('/api/mode',json={'mode':'live'}).status_code==403
    assert client.post('/api/mode',json={'mode':'live'},headers={**HEAD,'Origin':'https://evil.example'}).status_code==403
    assert client.get('/api/player/absent').status_code==404

def test_pregame_snapshot_settlement_and_separate_missed_outcomes(client,monkeypatch):
    current=datetime.now(timezone.utc)
    before=(current-timedelta(days=2)).isoformat()
    game_at=(current-timedelta(days=1)).isoformat()
    path=client.application.config['DB_PATH']
    with connect(path) as db:
        for pid in ('aja-wilson','breanna-stewart'):
            put(db,'demo','schedule',pid,'settlement-test',{'id':'settlement-test','game_at':game_at,'retrieved_at':before,'source_url':None,'opponent':'Synthetic settlement opponent','home':True})
        db.commit()
    monkeypatch.setattr('app.now',lambda:before)
    assert client.post('/api/forecasts',json={},headers=HEAD).status_code==200
    with connect(path) as db:
        for pid,appeared in [('aja-wilson',True),('breanna-stewart',False)]:
            put(db,'demo','logs',pid,'settlement-test',{'id':'settlement-test','game_at':game_at,'available_at':(current-timedelta(hours=20)).isoformat(),'retrieved_at':current.isoformat(),'source_url':None,'appeared':appeared,'minutes':30 if appeared else 0,'points':27 if appeared else 0})
        db.commit()
    monkeypatch.setattr('app.now',lambda:current.isoformat())
    one=client.get('/api/player/aja-wilson').get_json()['history'][0]
    missed=client.get('/api/player/breanna-stewart').get_json()['history'][0]
    assert one['outcome']=='appeared' and one['actual']==27
    assert missed['outcome']=='missed' and missed['actual'] is None
    assert one['created_at']==before and one['game']['game_at']==game_at

def test_scheduler_mode_does_not_mutate_dashboard_and_ai_unavailable_falls_back(client,monkeypatch):
    r=client.post('/api/forecasts',json={'mode':'live'},headers=HEAD)
    assert r.get_json()['saved']==0
    assert client.get('/api/dashboard').get_json()['mode']=='demo'
    monkeypatch.setenv('LLM_API_KEY','test-not-a-real-key')
    def fail(*a,**k): raise OSError('unavailable')
    monkeypatch.setattr('urllib.request.urlopen',fail)
    result=client.post('/api/player/aja-wilson/ask',json={'question':'Threshold probability?','threshold':22.5},headers=HEAD).get_json()
    assert result['warning'] and result['facts']
    assert any('22.5 points threshold' in f['text'] for f in result['facts'])
