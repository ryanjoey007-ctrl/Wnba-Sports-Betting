"""Interpretable conditional-on-appearance count forecasts. No news in backtests."""
import math
from datetime import datetime, timezone
from scipy.stats import nbinom, poisson

VERSION = 'minutes-rate-v1'

def instant(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Timestamps must include a timezone (e.g. Z or +10:00).')
    return dt.astimezone(timezone.utc)

def eligible(logs, cutoff):
    at = instant(cutoff)
    return sorted([g for g in logs if g['appeared'] and g['minutes'] > 0
                   and instant(g['game_at']) < at and instant(g['available_at']) < at],
                  key=lambda g: instant(g['game_at']))

def distribution(mean, variance):
    if mean <= 0:
        return poisson(0)
    if variance <= mean + 1e-8:
        return poisson(mean)
    r = mean * mean / (variance - mean)
    return nbinom(r, r / (r + mean))

def probabilities(mean, variance, threshold):
    if threshold is None:
        return None
    t = float(threshold)
    if not math.isfinite(t) or t < 0 or t > 200:
        raise ValueError('Threshold must be between 0 and 200.')
    d = distribution(mean, variance)
    below = float(d.cdf(math.ceil(t) - 1))
    equal = float(d.pmf(int(t))) if t.is_integer() else 0.0
    return {'below': below, 'exactly': equal, 'above': max(0.0, 1.0 - below - equal)}

def forecast(logs, cutoff, threshold=None, minutes_cap=None):
    games = eligible(logs, cutoff)
    if len(games) < 5:
        return None
    season = instant(games[-1]['game_at']).year
    season_games = [g for g in games if instant(g['game_at']).year == season]
    # At most 80 appearances, with a season component and a recent-five component.
    reference = season_games if len(season_games) >= 5 else games[-80:]
    recent = games[-5:]
    average = lambda xs, key: sum(g[key] for g in xs) / len(xs)
    minutes = .65 * average(recent, 'minutes') + .35 * average(reference, 'minutes')
    rate = lambda xs: sum(g['points'] for g in xs) / sum(g['minutes'] for g in xs)
    ppm = .65 * rate(recent) + .35 * rate(reference)
    if minutes_cap is not None:
        minutes = min(minutes, float(minutes_cap))
    mean = minutes * ppm
    residuals = []
    # Each dispersion residual uses an earlier prefix only, never its own outcome.
    for i in range(max(5, len(games) - 30), len(games)):
        prev = games[max(0, i - 5):i]
        estimate = average(prev, 'points')
        residuals.append((games[i]['points'] - estimate) ** 2)
    variance = max(mean, sum(residuals) / len(residuals) if len(residuals) >= 5 else 1.8 * mean, 1.0)
    d = distribution(mean, variance)
    return {'expected_points': round(mean, 2), 'projected_minutes': round(minutes, 2),
            'points_per_minute': round(ppm, 4), 'variance': variance,
            'interval': [int(d.ppf(.1)), int(d.ppf(.9))],
            'probabilities': probabilities(mean, variance, threshold),
            'baseline': round(average(recent, 'points'), 2), 'training_games': len(games),
            'latest_game': games[-1]['game_at'], 'data_cutoff': cutoff, 'model_version': VERSION,
            'explanation': 'Minutes and points per minute each blend recent five appearances (65%) with season performance (35%). Their product gives expected points. The count distribution uses past scoring residuals for uncertainty.'}

def evaluate(logs, threshold=None):
    ordered = sorted(logs, key=lambda g: instant(g['game_at']))
    rows = []
    for game in ordered:
        if not game['appeared'] or game['minutes'] <= 0:
            continue
        f = forecast(ordered, game['game_at'], threshold)
        if f is None:
            continue
        y = game['points']
        row = {'game_at': game['game_at'], 'actual': y, 'forecast': f['expected_points'],
               'baseline': f['baseline'], 'interval': f['interval']}
        if threshold is not None:
            # Multiclass Brier: below, equal, above. Binary above calibration also reported.
            p = f['probabilities']
            labels = {'below': y < threshold, 'exactly': y == threshold, 'above': y > threshold}
            row['brier'] = sum((p[k] - int(labels[k])) ** 2 for k in labels)
            row['above_probability'] = p['above']
            row['above_actual'] = int(y > threshold)
        rows.append(row)
    n = len(rows)
    metrics = {'n': n, 'missed_games': sum(not g['appeared'] for g in logs),
               'mae': None, 'baseline_mae': None, 'coverage': None, 'brier': None, 'calibration': []}
    if n:
        metrics.update(mae=round(sum(abs(r['actual'] - r['forecast']) for r in rows) / n, 3),
                       baseline_mae=round(sum(abs(r['actual'] - r['baseline']) for r in rows) / n, 3),
                       coverage=sum(r['interval'][0] <= r['actual'] <= r['interval'][1] for r in rows) / n)
    if threshold is not None and n >= 20:
        metrics['brier'] = sum(r['brier'] for r in rows) / n
        for bucket in range(5):
            members = [r for r in rows if min(4, int(r['above_probability'] * 5)) == bucket]
            if members:
                metrics['calibration'].append({'n': len(members), 'predicted': sum(r['above_probability'] for r in members) / len(members), 'observed': sum(r['above_actual'] for r in members) / len(members)})
    return {'metrics': metrics, 'rows': rows, 'limitations': 'Only timestamp-eligible statistics are used. News, opponent, home/away, rest, usage and teammate features are excluded: no validated improvement or historical news snapshots. Imported available_at times must reflect real publication times; revisions without snapshots cannot be reconstructed. Fewer than 20 predictions: threshold calibration and Brier are withheld.'}
