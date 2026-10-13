"""Public competition metadata, never player health or calendar-date inference."""
import re
from urllib.parse import urlsplit

# Verified in ESPN's public player game logs on 13 October 2026. Earlier
# imports omitted nested team.isAllStar/eventNote; identify those stored
# snapshots by their exact ESPN event IDs without editing or deleting them.
VERIFIED_ALL_STAR_EVENTS = {'401620458','401781604','401857320'}

def exclusion_reason(game):
    if game.get('isAllStar') is True:
        return 'All-Star game'
    if any(isinstance(game.get(key),dict) and game[key].get('isAllStar') is True for key in ('team','opponent')):
        return 'All-Star game'
    note=str(game.get('eventNote') or '')
    if re.search(r'\ball[ -]?star\b',note,re.IGNORECASE):
        return 'All-Star game'
    if game.get('competition_type')=='all_star':
        return 'All-Star game'
    if game.get('competition_type')=='preseason' or re.search(r'\bpreseason\b',note,re.IGNORECASE):
        return 'Preseason game'
    if str(game.get('id','')) in VERIFIED_ALL_STAR_EVENTS:
        host=urlsplit(game.get('source_url') or '').hostname
        if host in ('site.api.espn.com','site.web.api.espn.com','www.espn.com'):
            return 'All-Star game'
    return None

def scoring_appearance(game):
    return game['appeared'] and game['minutes']>0 and exclusion_reason(game) is None
