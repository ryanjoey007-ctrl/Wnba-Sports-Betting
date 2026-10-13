import pytest
from datetime import datetime, timedelta, timezone
from app import availability, create_app
from ingest import news_records, parse_gamelog, refresh_news, BASE, GAMELOG_BASE
from store import connect, records

MATCHED=[({'id':'aja-wilson','name':'A’ja Wilson'},'3149391','17')]
NOW='2026-10-13T01:00:00Z'

def article(aid='3149391',ident='a1',headline='Basketball update'):
    return {'id':ident,'published':'2026-10-12T01:00:00Z','lastModified':'2026-10-12T01:00:00Z',
            'headline':headline,'description':'Public basketball news.',
            'categories':[{'type':'athlete','id':'not-the-athlete-id','athleteId':aid}],
            'links':{'web':{'href':'https://www.espn.com/wnba/story/_/id/123/test'}}}

def injury(status='Out',date='2026-10-12T01:00:00Z',body='Wilson is out; the injury is undisclosed.'):
    return {'id':'report1','date':date,'status':status,'longComment':body,
            'details':{'type':'Undisclosed'},'athlete':{'displayName':"A'ja Wilson",'links':[{'href':'https://www.espn.com/wnba/player/_/id/3149391/aja-wilson'}]}}

def test_explicit_player_filter_stable_id_and_name():
    items,skipped=news_records(MATCHED,[article(),article('999','unrelated'),article('999','named',"A'ja Wilson scores 25")],[],NOW)
    assert len(items)==2 and skipped==0
    assert all(x[2]['status']=='unknown' and not x[2]['confirmed'] for x in items)

def test_public_undisclosed_report_only_and_stale_missing_status():
    items,_=news_records(MATCHED,[],[{'injuries':[injury()]}],NOW)
    report=items[0][2]
    assert report['injury_type']=='Undisclosed' and report['status']=='out'
    assert report['source_url']==BASE+'/injuries?limit=100' and report['published_at']=='2026-10-12T01:00:00Z'
    assert availability([report],NOW)['status']=='out'
    assert availability([] ,NOW)['status']=='unknown'
    assert availability([report],'2026-10-15T01:00:00Z')['status']=='unknown'
    assert report['minutes_cap'] is None
    # Unfamiliar status is not guessed, and no private detail is filled in.
    unknown,_=news_records(MATCHED,[],[{'injuries':[injury(status='Pending',body='No detail provided.')]}],NOW)
    assert unknown[0][2]['status']=='unknown' and not unknown[0][2]['confirmed']

def test_general_article_never_clears_injury_or_revives_stale_report():
    items,_=news_records(MATCHED,[article()], [{'injuries':[injury(date='2026-10-01T01:00:00Z')]}],NOW)
    result=availability([x[2] for x in items],NOW)
    assert result['status']=='unknown' and result['stale']

def test_revision_snapshots_and_bad_source_dates():
    one,_=news_records(MATCHED,[],[{'injuries':[injury()]}],NOW)
    two,_=news_records(MATCHED,[],[{'injuries':[injury(status='Available')]}],NOW)
    assert one[0][1]!=two[0][1]
    assert availability([one[0][2],two[0][2]],NOW)['conflict']
    bad=article();bad.pop('published')
    future=article(ident='future');future['published']='2026-10-20T01:00:00Z'
    parsed,skipped=news_records(MATCHED,[bad,future],[],NOW)
    assert parsed==[] and skipped==2

def test_news_cache_repeatability_and_transactional_failure(tmp_path,monkeypatch):
    path=tmp_path/'news.sqlite3'
    def source(url):
        if '/news' in url:return {'articles':[article()]}
        if '/injuries' in url:return {'injuries':[{'injuries':[injury()]}]}
        raise AssertionError(url)
    monkeypatch.setattr('ingest.fetch',source)
    monkeypatch.setattr('ingest.now',lambda:NOW)
    with connect(path) as db:
        assert refresh_news(db,MATCHED)['reports']==2
        assert refresh_news(db,MATCHED)['reports']==0
        assert len(records(db,'live','news','aja-wilson'))==2
        def fail(url):raise OSError('blocked')
        monkeypatch.setattr('ingest.fetch',fail)
        with pytest.raises(OSError):refresh_news(db,MATCHED)
        assert len(records(db,'live','news','aja-wilson'))==2

def test_game_logs_multiple_periods_all_star_exclusion_and_retrieval_cutoff():
    data={'labels':['MIN','PTS'],'events':{'g1':{'gameDate':'2026-06-12T01:00:00Z','opponent':{'displayName':'Opponent'},'atVs':'vs'},
         'star':{'gameDate':'2026-07-12T01:00:00Z','isAllStar':True},'future':{'gameDate':'2027-01-01T01:00:00Z'}},
         'seasonTypes':[{'displayName':'2026 Regular Season','categories':[{'events':[
             {'eventId':'g1','stats':['32:30','25']},{'eventId':'star','stats':['20','40']},{'eventId':'future','stats':['30','20']}]}]},
             {'displayName':'2026 Preseason','categories':[{'events':[{'eventId':'g1','stats':['30','40']}]}]}]}
    rows,skipped=parse_gamelog(data,NOW,2026,GAMELOG_BASE+'/3149391/gamelog?season=2026')
    assert len(rows)==1 and skipped==0 and rows[0]['minutes']==32.5 and rows[0]['points']==25
    assert rows[0]['available_at']==NOW and rows[0]['season_type']=='regular'

def test_new_endpoints_validate_and_report_failures(tmp_path,monkeypatch):
    client=create_app(str(tmp_path/'app.sqlite3')).test_client()
    head={'X-WNBA-Client':'1'}
    assert client.get('/api/player/aja-wilson/calendar?threshold=22.5').get_json()['days']
    assert client.get('/api/player/aja-wilson/calendar?season=invalid').status_code==400
    assert client.post('/api/history/load',json={'seasons':[True]},headers=head).status_code==400
    def fail(*a,**k):raise OSError('blocked')
    monkeypatch.setattr('app.refresh_news',fail)
    assert client.post('/api/news/refresh',json={},headers=head).status_code==502
    assert client.get('/api/dashboard').get_json()['news_refresh_error']
