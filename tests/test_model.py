from datetime import datetime, timedelta, timezone
import pytest
from model import eligible, forecast, probabilities, evaluate

def logs(n=40):
    at=datetime(2025,6,1,tzinfo=timezone.utc)
    return [{'id':str(i),'game_at':(at+timedelta(days=i*3)).isoformat(),
             'available_at':(at+timedelta(days=i*3,hours=3)).isoformat(),
             'minutes':30,'points':20+i%7,'appeared':True} for i in range(n)]

def test_no_future_or_late_published_scores():
    gs=logs(12)
    gs[0]['available_at']=gs[11]['game_at']
    used=eligible(gs,gs[10]['game_at'])
    assert len(used)==9
    assert gs[10] not in used and gs[11] not in used and gs[0] not in used

def test_walk_forward_prefix_and_target_mutations():
    gs=logs()
    expected=evaluate(gs)['rows'][10]['forecast']
    gs[15]['points']=140
    assert evaluate(gs)['rows'][10]['forecast']==expected
    gs[16]['points']=150
    assert evaluate(gs)['rows'][10]['forecast']==expected

def test_minutes_times_rate_and_missed_not_zero():
    gs=logs(10)
    at='2026-01-01T00:00:00Z'
    f=forecast(gs,at)
    assert f['expected_points']==round(f['projected_minutes'] * (.65*sum(g['points'] for g in gs[-5:])/150+.35*sum(g['points'] for g in gs)/300),2)
    missing={**gs[-1],'appeared':False,'minutes':0,'points':0}
    assert forecast(gs+[missing],at)==f
    capped=forecast(gs,at,minutes_cap=20)
    assert capped['projected_minutes']==20
    assert capped['expected_points']<f['expected_points']

@pytest.mark.parametrize('threshold',[0,1,22,22.5,100,200])
def test_probability_partition(threshold):
    p=probabilities(24,55,threshold)
    assert sum(p.values())==pytest.approx(1)
    assert all(0<=v<=1 for v in p.values())
    if threshold%1:
        assert p['exactly']==0
    else:
        assert p['exactly']>=0

def test_poisson_zero_and_integer_ties():
    assert probabilities(0,0,0)=={'below':0,'exactly':1,'above':0}
    assert probabilities(24,24,24)['exactly']>0
    with pytest.raises(ValueError): probabilities(24,40,float('nan'))

def test_validation_metrics_counts_and_calibration():
    result=evaluate(logs(),22.5)
    m=result['metrics']
    assert m['n']==35 and m['mae']>=0 and m['baseline_mae']>=0
    assert 0<=m['coverage']<=1 and 0<=m['brier']<=2
    assert sum(b['n'] for b in m['calibration'])==35
    assert evaluate(logs(10),22.5)['metrics']['brier'] is None

def test_naive_timestamp_rejected():
    with pytest.raises(ValueError): eligible(logs(),'2026-01-01')
