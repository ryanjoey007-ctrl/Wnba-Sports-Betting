"""End-to-end checks against an isolated database. Requires Playwright + Chromium.

Run: python tests/browser_smoke.py
"""
import csv
import io
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime,timedelta,timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]

def contents(rows):
    stream=io.StringIO()
    writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
    writer.writeheader();writer.writerows(rows)
    return stream.getvalue().encode()

with tempfile.TemporaryDirectory() as temporary:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    environment={**os.environ,'WNBA_DB':str(Path(temporary)/'browser.sqlite3'),'PORT':str(port),'REFRESH_MINUTES':'0'}
    environment.pop('LLM_API_KEY',None)
    process=subprocess.Popen([sys.executable,'app.py'],cwd=ROOT,env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    base=f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base+'/api/dashboard',timeout=1).close();break
            except OSError:
                time.sleep(.1)
        else:
            raise RuntimeError('Server did not become ready')
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=os.getenv('CHROMIUM_PATH','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[]
            page.on('pageerror',lambda exc:errors.append(str(exc)))
            page.goto(base)
            page.wait_for_function("document.querySelectorAll('.player-name').length===5")
            assert 'Synthetic demo' in page.locator('#data-banner').inner_text()
            page.fill('#threshold','22.5');page.click('#apply-threshold')
            page.wait_for_function("document.querySelector('#probabilities').textContent.includes('22.5')")
            assert 'Exactly: 0.0%' in page.locator('#probabilities').inner_text()
            page.fill('#search','Sabrina')
            assert page.locator('.player-name').count()==1
            page.fill('#search','')
            page.click('#add-player')
            page.locator('#add-form input').fill('Browser Test Player')
            page.locator('#add-form button.primary').click()
            page.wait_for_function("document.querySelectorAll('.player-name').length===6")
            page.locator('button[aria-label="Remove Browser Test Player"]').click()
            page.wait_for_function("document.querySelectorAll('.player-name').length===5")
            page.click('#save-forecasts')
            page.wait_for_function("document.querySelector('#notice').textContent.includes('Saved 4')")
            page.locator('.player-name').first.click()
            page.wait_for_selector('#ask-form')
            assert page.locator('svg.chart').count()==1
            assert page.locator('svg.calendar-chart').count()==1
            assert page.locator('#calendar-day option').count()==31
            page.select_option('#calendar-day','13')
            assert 'CALENDAR DAY 13' in page.locator('#calendar-selected').inner_text()
            assert 'Observed frequencies, not forecast probabilities' in page.locator('#calendar-selected').inner_text() or 'No recorded appearances' in page.locator('#calendar-selected').inner_text()
            last_season=page.locator('#calendar-season option').nth(1).get_attribute('value')
            page.select_option('#calendar-season',last_season)
            page.wait_for_function("!document.querySelector('#calendar-season').disabled")
            assert page.locator('#calendar-season').input_value()==last_season
            assert 'Descriptive history' in page.locator('.calendar-panel').inner_text()
            assert 'SYNTHETIC RESULTS' in page.locator('#detail').inner_text()
            assert 'Threshold 22.5' in page.locator('#detail').inner_text()
            assert 'Above-threshold calibration' in page.locator('#detail').inner_text()
            assert 'minutes-rate-v1' in page.locator('#detail').inner_text()
            page.fill('#ask-form input','Why did her projection change?')
            page.locator('#ask-form button').click()
            page.wait_for_function("document.querySelector('#answer').textContent.includes('Stored-facts explanation')")
            assert 'Synthetic demo evidence only' in page.locator('#answer').inner_text()
            page.goto(base)
            page.wait_for_selector('.player-name')
            page.click('#open-data')
            page.wait_for_selector('#data-dialog[open]')
            page.route('**/api/history/load',lambda route:route.fulfill(status=202,content_type='application/json',body='{"job_id":"browser-import","status":"queued"}'))
            polls={'n':0}
            def history_status(route):
                polls['n']+=1
                body='{"status":"running","message":"Downloading player-season game logs","current":3,"total":15,"elapsed_seconds":1}' if polls['n']==1 else '{"status":"complete","message":"Import complete","current":15,"total":15,"elapsed_seconds":2,"result":{"records":0,"games_checked":0,"seasons":[2024,2025,2026],"unmatched":[]}}'
                route.fulfill(status=200,content_type='application/json',body=body)
            page.route('**/api/history/jobs/browser-import',history_status)
            page.click('#load-seasons')
            page.wait_for_function("document.querySelector('#history-message').textContent.includes('3/15')")
            assert page.locator('#load-seasons').is_disabled()
            page.wait_for_selector('#history-view:visible')
            assert 'Import complete' in page.locator('#history-message').inner_text()
            assert not page.locator('#load-seasons').is_disabled()
            page.click('#history-view')
            page.wait_for_function("document.querySelector('#mode-label').textContent.includes('sourced-data')")
            assert page.locator('.points').count()==0
            page.click('#open-data')
            page.wait_for_selector('#data-dialog[open]')
            at=datetime.now(timezone.utc)
            rows=[{'player_id':'aja-wilson','id':f'browser-{i}','game_at':(at-timedelta(days=40-i)).isoformat(),
                   'available_at':(at-timedelta(days=40-i,hours=-3)).isoformat(),'minutes':32,'points':21+i%5,
                   'appeared':'true','source_url':'https://example.com/browser-test-fixture'} for i in range(30)]
            page.set_input_files('#import-form input[type=file]',{'name':'logs.csv','mimeType':'text/csv','buffer':contents(rows)})
            page.locator('#import-form button').click()
            page.wait_for_function("document.querySelector('#import-result').textContent.includes('Imported 30')")
            page.select_option('#import-kind','schedule')
            scheduled=[{'player_id':'aja-wilson','id':'browser-next','game_at':(at+timedelta(days=1)).isoformat(),'opponent':'Browser fixture opponent','home':'true','source_url':'https://example.com/browser-test-fixture'}]
            page.set_input_files('#import-form input[type=file]',{'name':'schedule.csv','mimeType':'text/csv','buffer':contents(scheduled)})
            page.locator('#import-form button').click()
            page.wait_for_function("document.querySelector('#import-result').textContent.includes('Imported 1 ')")
            page.click('#close-data')
            page.wait_for_selector('.points')
            assert page.locator('.points').count()==1
            assert 'Availability unknown' in page.locator('#players').inner_text()
            page.locator('.player-name').first.click()
            page.wait_for_selector('#ask-form')
            assert 'TIMESTAMP-ELIGIBLE STATS' in page.locator('#detail').inner_text()
            assert 'Browser fixture opponent' in page.locator('#detail').inner_text()
            assert 'RECORDED APPEARANCES' in page.locator('.calendar-panel').inner_text()
            page.route('**/api/news/refresh',lambda route:route.fulfill(status=502,content_type='application/json',body='{"error":"Public ESPN feed unavailable in browser fixture; cache retained."}'))
            page.click('#player-news-refresh')
            page.wait_for_function("document.querySelector('#notice').textContent.includes('Public ESPN feed unavailable')")
            assert page.locator('svg.calendar-chart').count()==1
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert page.locator('.calendar-scroll').evaluate('(el)=>el.scrollWidth>el.clientWidth')
            page.set_viewport_size({'width':1440,'height':1000})
            page.goto(base)
            page.wait_for_selector('.player-name')
            page.click('#switch-mode')
            page.wait_for_function("document.querySelector('#mode-label').textContent.includes('Synthetic')")
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert page.locator('.table-wrap').evaluate('(el)=>el.scrollWidth>el.clientWidth')
            output=ROOT/'test-results'
            output.mkdir(exist_ok=True)
            page.screenshot(path=str(output/'mobile.png'),full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
            page.screenshot(path=str(output/'dashboard.png'),full_page=True)
            assert errors==[],errors
            browser.close()
            print('PASS: watchlist, thresholds, snapshots, charts, calendar filters, import progress/completion and view-data action, error states, Q&A, real/demo isolation, CSV imports and mobile layout; no browser JS errors.')
    finally:
        process.terminate();process.wait(timeout=10)
