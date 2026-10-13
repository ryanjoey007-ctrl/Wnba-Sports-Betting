"""Run refresh from cron while the web server is stopped or running."""
import argparse
import json
import os
from store import connect, seed_demo
from ingest import refresh

parser = argparse.ArgumentParser()
parser.add_argument('command', choices=['refresh','reset-demo'])
parser.add_argument('--history-days',type=int,default=7)
parser.add_argument('--save',action='store_true',help='Append pregame forecast snapshots after a successful refresh.')
args = parser.parse_args()
if not 0 <= args.history_days <= 366:
    parser.error('--history-days must be 0–366. Use CSV for larger multi-season imports.')
with connect(os.getenv('WNBA_DB','data/wnba.sqlite3')) as db:
    if args.command == 'reset-demo':
        db.execute("DELETE FROM records WHERE mode='demo'")
        db.execute("DELETE FROM forecasts WHERE mode='demo'")
        db.execute("DELETE FROM settings WHERE key='demo_seeded'")
        seed_demo(db)
        print('Reset synthetic demo only; real data and forecasts preserved.')
    else:
        print(json.dumps(refresh(db,args.history_days),indent=2))
if args.command=='refresh' and args.save:
    from app import app
    with app.test_client() as client:
        # No mutation of the UI's selected mode: cron always saves live records.
        response=client.post('/api/forecasts',json={'mode':'live'},headers={'X-WNBA-Client':'1'})
        if response.status_code!=200:
            raise RuntimeError('Snapshot save failed')
        print(response.get_json())
