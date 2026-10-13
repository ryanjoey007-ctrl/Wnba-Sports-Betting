from datetime import datetime, timedelta, timezone
import pytest
from calendar_stats import calendar_summary, local_day
from model import forecast

def log(ident, at, points, appeared=True, available=None):
    stamp=datetime.fromisoformat(at.replace('Z','+00:00'))
    return {'id':ident,'game_at':at,'available_at':available or (stamp+timedelta(hours=3)).isoformat(),
            'minutes':30 if appeared else 0,'points':points if appeared else 0,
            'appeared':appeared,'source_url':'https://example.com/test-game'}

def test_sydney_day_not_utc_and_month_edges():
    assert local_day('2025-01-31T23:00:00Z')==1
    assert local_day('2025-06-30T23:00:00Z')==1
    assert local_day('2025-06-12T01:00:00Z')==12

def test_calendar_means_counts_threshold_and_exclusions():
    games=[log('a','2025-01-12T01:00:00Z',20),log('b','2025-02-12T01:00:00Z',25),
           log('missed','2025-03-12T01:00:00Z',0,False),log('other','2025-04-13T01:00:00Z',12),
           log('future','2026-02-12T01:00:00Z',70),
           log('late','2025-04-12T01:00:00Z',90,available='2026-02-12T01:00:00Z')]
    out=calendar_summary(games,'2026-01-01T00:00:00Z',22.5)
    day=out['days'][11]
    assert len(out['days'])==31 and out['appearances']==3
    assert day['n']==2 and day['mean']==22.5 and day['minimum']==20 and day['maximum']==25
    assert day['counts']=={'below':1,'above':1,'exactly':0}
    assert day['frequencies']['below']==.5 and day['low_sample']
    assert out['days'][30]['n']==0 and out['days'][30]['mean'] is None
    assert out['days'][30]['frequencies'] is None
    assert all(g['source_url'] for g in day['games'])

def test_season_filter_and_calendar_does_not_change_forecast():
    games=[log(str(y),'%d-06-12T01:00:00Z'%y,20+y%3) for y in range(2018,2026)]
    before=forecast(games,'2026-01-01T00:00:00Z',22.5)
    out=calendar_summary(games,'2026-01-01T00:00:00Z',22.5,season=2025)
    assert out['appearances']==1 and out['seasons'][0]==2025
    assert forecast(games,'2026-01-01T00:00:00Z',22.5)==before

def test_calendar_walk_forward_uses_prior_snapshots_on_matched_targets():
    start=datetime(2020,1,12,1,tzinfo=timezone.utc)
    games=[]
    for year in range(2020,2023):
        for month in range(1,13):
            at=start.replace(year=year,month=month)
            games.append(log(str(len(games)),at.isoformat(),20+len(games)%4))
    baseline=calendar_summary(games,'2024-01-01T00:00:00Z')['validation']
    assert baseline['n']==31 and baseline['calendar_mae'] is not None
    # Make every result first available after all targets. No historical test may use them.
    for g in games:g['available_at']='2023-12-01T00:00:00Z'
    blocked=calendar_summary(games,'2024-01-01T00:00:00Z')['validation']
    assert blocked['n']==0 and blocked['finding']=='insufficient_data'

def test_integer_threshold_ties_and_next_day():
    games=[log('a','2025-01-12T01:00:00Z',22)]
    out=calendar_summary(games,'2026-01-01T00:00:00Z',22,next_game_at='2026-01-31T23:00:00Z')
    assert out['days'][11]['counts']['exactly']==1
    assert out['next_game_day']==1
