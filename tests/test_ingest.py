from datetime import datetime,timedelta,timezone
from store import connect,records
from ingest import refresh,BASE

def test_public_adapter_fixture_stable_identity_and_cache(tmp_path,monkeypatch):
    future=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    def fixture(url):
        if url.endswith('/teams'):
            return {'sports':[{'leagues':[{'teams':[{'team':{'id':'1'}}]}]}]}
        if url.endswith('/roster'):
            return {'athletes':[{'id':'123','fullName':"A'ja Wilson"}]}
        if '/scoreboard' in url:
            return {'events':[{'id':'event123','date':future,'competitions':[{'competitors':[{'team':{'id':'1','displayName':'Home'},'homeAway':'home'},{'team':{'id':'2','displayName':'Away'},'homeAway':'away'}],'status':{'type':{'completed':False}}}]}]}
        raise AssertionError(url)
    monkeypatch.setattr('ingest.fetch',fixture)
    with connect(tmp_path/'test.sqlite3') as db:
        result=refresh(db)
        assert result['matched_players']==1
        p=db.execute("SELECT * FROM players WHERE id='aja-wilson'").fetchone()
        assert p['espn_id']=='123' and p['team_id']=='1'
        schedule=records(db,'live','schedule','aja-wilson')
        assert len(schedule)==1 and schedule[0]['opponent']=='Away'
        assert schedule[0]['source_url'].startswith(BASE)
        refresh(db)
        assert len(records(db,'live','schedule','aja-wilson'))==1

def test_boxscore_retrieval_time_and_no_snapshot_overwrite(tmp_path,monkeypatch):
    past=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
    calls={'points':'25'}
    def fixture(url):
        if url.endswith('/teams'):
            return {'sports':[{'leagues':[{'teams':[{'team':{'id':'1'}}]}]}]}
        if url.endswith('/roster'):
            return {'athletes':[{'id':'123','fullName':"A'ja Wilson"}]}
        if '/scoreboard' in url:
            return {'events':[{'id':'completed','date':past,'competitions':[{'competitors':[{'team':{'id':'1','displayName':'Home'},'homeAway':'home'},{'team':{'id':'2','displayName':'Away'},'homeAway':'away'}],'status':{'type':{'completed':True}}}]}]}
        if '/summary' in url:
            return {'boxscore':{'players':[{'statistics':[{'labels':['MIN','PTS'],'athletes':[{'athlete':{'id':'123'},'stats':['32:30',calls['points']]}]}]}]}}
        raise AssertionError(url)
    monkeypatch.setattr('ingest.fetch',fixture)
    with connect(tmp_path/'boxscore.sqlite3') as db:
        first=refresh(db,3)
        logs=records(db,'live','logs','aja-wilson')
        assert len(logs)==1 and logs[0]['minutes']==32.5 and logs[0]['points']==25
        assert logs[0]['available_at']==first['retrieved_at']
        assert logs[0]['game_at']==past
        calls['points']='26'
        refresh(db,3)
        assert records(db,'live','logs','aja-wilson')[0]['points']==25
