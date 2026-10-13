import time
import threading
import pytest
from app import create_app
from ingest import ImportControl, ImportCancelled, fetch_many
from store import connect, records, put

HEAD={'X-WNBA-Client':'1'}

def terminal(client,job_id,seconds=3):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        job=client.get('/api/history/jobs/'+job_id).get_json()
        if job['status'] in ('complete','failed','cancelled'):
            return job
        time.sleep(.01)
    pytest.fail('Import job did not terminate')

def test_background_import_progress_reuse_and_completion(tmp_path,monkeypatch):
    started=threading.Event();finish=threading.Event()
    def import_data(db,years,control):
        control.progress('Downloading player-season game logs',2,15)
        started.set()
        assert finish.wait(2)
        control.check()
        return {'records':20,'seasons':years,'unmatched':[]}
    monkeypatch.setattr('app.load_history',import_data)
    client=create_app(str(tmp_path/'jobs.sqlite3')).test_client()
    r=client.post('/api/history/load',json={},headers=HEAD)
    assert r.status_code==202 and started.wait(1)
    ident=r.get_json()['job_id']
    try:
        job=client.get('/api/history/jobs/'+ident).get_json()
        assert job['current']==2 and job['total']==15
        # Reads still work while ESPN is outstanding; no duplicate imports start.
        assert client.get('/api/dashboard').status_code==200
        repeated=client.post('/api/history/load',json={},headers=HEAD).get_json()
        assert repeated['job_id']==ident and repeated['reused']
    finally:
        finish.set()
    done=terminal(client,ident)
    assert done['result']['records']==20 and done['status']=='complete'

def test_cancel_and_failed_imports_preserve_game_records(tmp_path,monkeypatch):
    path=tmp_path/'cancel.sqlite3'
    client=create_app(str(path)).test_client()
    with connect(path) as db:
        put(db,'live','logs','aja-wilson','existing',{'id':'existing','points':20})
        db.commit()
    started=threading.Event()
    def paused(db,years,control):
        started.set()
        while True:
            control.check()
            time.sleep(.01)
    monkeypatch.setattr('app.load_history',paused)
    ident=client.post('/api/history/load',json={},headers=HEAD).get_json()['job_id']
    assert started.wait(1)
    assert client.post('/api/history/jobs/'+ident+'/cancel',json={},headers=HEAD).status_code==200
    assert terminal(client,ident)['status']=='cancelled'
    def fail(*args):raise TimeoutError('blocked ESPN connection')
    monkeypatch.setattr('app.load_history',fail)
    ident=client.post('/api/history/load',json={},headers=HEAD).get_json()['job_id']
    failed=terminal(client,ident)
    assert failed['status']=='failed' and 'time limit' in failed['error']
    with connect(path) as db:
        assert records(db,'live','logs','aja-wilson')==[{'id':'existing','points':20}]
    assert client.get('/api/history/jobs/missing').status_code==404

def test_import_cancel_rolls_back_uncommitted_changes(tmp_path,monkeypatch):
    path=tmp_path/'rollback.sqlite3'
    def fail(db,years,control):
        put(db,'live','logs','aja-wilson','uncommitted',{'id':'uncommitted'})
        raise ImportCancelled('Cancelled before commit')
    monkeypatch.setattr('app.load_history',fail)
    client=create_app(str(path)).test_client()
    ident=client.post('/api/history/load',json={},headers=HEAD).get_json()['job_id']
    assert terminal(client,ident)['status']=='cancelled'
    with connect(path) as db:
        assert records(db,'live','logs','aja-wilson')==[]

def test_parallel_downloads_bounded_and_ordered(monkeypatch):
    active=0;maximum=0;lock=threading.Lock()
    barrier=threading.Event()
    def source(url):
        nonlocal active,maximum
        with lock:
            active+=1;maximum=max(maximum,active)
            if active==3:barrier.set()
        assert barrier.wait(1)
        time.sleep(.01)
        with lock:active-=1
        return {'url':url}
    monkeypatch.setattr('ingest.fetch',source)
    updates=[]
    control=ImportControl(lambda message,current,total:updates.append((current,total)))
    result=fetch_many(list(map(str,range(8))),control)
    assert [r['url'] for r in result]==list(map(str,range(8)))
    assert maximum==3 and updates[-1]==(8,8)

def test_overall_deadline_does_not_wait_for_network_worker(monkeypatch):
    release=threading.Event()
    started=threading.Event()
    def stalled(url):started.set();release.wait(2);return {}
    monkeypatch.setattr('ingest.fetch',stalled)
    begin=time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            fetch_many(['stalled'],ImportControl(seconds=.05))
        assert started.is_set() and time.monotonic()-begin<1
    finally:
        release.set()
