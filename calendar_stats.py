"""Descriptive calendar-date scoring. These features never enter the forecast."""
from zoneinfo import ZoneInfo
from model import eligible, instant, forecast

ZONE = ZoneInfo('Australia/Sydney')

def local_day(timestamp):
    return instant(timestamp).astimezone(ZONE).day

def calendar_summary(logs, cutoff, threshold=None, season=None, next_game_at=None):
    appearances = eligible(logs, cutoff)
    seasons = sorted({instant(g['game_at']).astimezone(ZONE).year for g in appearances}, reverse=True)
    if season is not None:
        appearances = [g for g in appearances if instant(g['game_at']).astimezone(ZONE).year == season]
    overall = sum(g['points'] for g in appearances) / len(appearances) if appearances else None
    days = []
    for day in range(1, 32):
        members = [g for g in appearances if local_day(g['game_at']) == day]
        scores = [g['points'] for g in members]
        n = len(scores)
        counts = {key: sum(compare(y, threshold) for y in scores) for key, compare in (
            ('below', lambda y,t: y<t), ('exactly', lambda y,t: y==t), ('above', lambda y,t: y>t))} if threshold is not None else None
        days.append({'day':day, 'n':n, 'mean':round(sum(scores)/n,2) if n else None,
                     'minimum':min(scores) if n else None, 'maximum':max(scores) if n else None,
                     'low_sample':n<5, 'counts':counts,
                     'frequencies':{k:v/n for k,v in counts.items()} if counts and n else None,
                     'games':[{'id':g['id'],'game_at':g['game_at'],'points':g['points'],
                               'source_url':g.get('source_url')} for g in members]})
    # Test the hypothesis only on strictly earlier publication-eligible snapshots.
    # At least five earlier same-date appearances are required; matched targets
    # allow comparison with recent-five mean and the unchanged minutes-rate model.
    errors=[]
    for game in appearances:
        earlier=eligible(appearances,game['game_at'])
        same=[g for g in earlier if local_day(g['game_at'])==local_day(game['game_at'])]
        if len(same)<5:
            continue
        f=forecast(earlier,game['game_at'])
        if not f:
            continue
        mean=sum(g['points'] for g in same)/len(same)
        errors.append((abs(game['points']-mean),abs(game['points']-f['baseline']),abs(game['points']-f['expected_points'])))
    count=len(errors)
    mae=lambda index: round(sum(e[index] for e in errors)/count,3) if count else None
    calendar_mae, baseline_mae, model_mae=mae(0),mae(1),mae(2)
    finding='insufficient_data' if count<20 else 'no_improvement' if calendar_mae>=baseline_mae else 'experimental_improvement'
    return {'timezone':'Australia/Sydney', 'seasons':seasons, 'season':season, 'appearances':len(appearances),
            'overall_mean':round(overall,2) if overall is not None else None, 'days':days,
            'today_day':local_day(cutoff), 'next_game_day':local_day(next_game_at) if next_game_at else None,
            'threshold':threshold, 'validation':{'n':count,'minimum_prior_same_day':5,
            'calendar_mae':calendar_mae,'baseline_mae':baseline_mae,'model_mae':model_mae,'finding':finding},
            'limitation':'Historical averages, not future probabilities or a proven under strategy. Empty days have no average; fewer than five appearances is a small sample. Opponent, minutes, season and role differences can explain calendar differences. Calendar dates never affect the scoring model or imply private health information. Chronological comparisons require trustworthy historical publication times, which retrospectively fetched ESPN logs do not provide.'}
