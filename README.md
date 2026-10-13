# Courtwise — personal WNBA forecasting

A working Flask + SQLite web app with a responsive vanilla-JavaScript interface. Starts with A’ja Wilson, Breanna Stewart, Sabrina Ionescu, Kelsey Plum and Kelsey Mitchell. Times use Australia/Sydney, including daylight-saving changes. Read [QUICKSTART.md](QUICKSTART.md) for beginner instructions.

## Run and test

Python 3.12+ is recommended (tested: 3.12.14). No Node build or external database is required.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python app.py
```

The server prints its local address; port defaults to 5050. Application records are retained in `data/wnba.sqlite3`, which is ignored by Git. Back up this database before updating the app. Database contents and keys are not included in the downloadable source archive. This personal app binds to the local machine and has same-origin write protection, but no user login. Public deployment needs authentication, HTTPS, a persistent writable volume and a production WSGI server. No deployment or publicly accessible URL is included.

```sh
.venv/bin/python -m pytest -q
# Optional actual-browser smoke test (Linux, Chromium already installed):
.venv/bin/python -m pip install playwright==1.58.0
CHROMIUM_PATH=/usr/bin/chromium .venv/bin/python tests/browser_smoke.py
```

The browser test starts a temporary server with an isolated database. It exercises watchlists, thresholds, player details, charts, snapshots, Q&A, CSV imports and mobile layout. `test-results/` contains generated screenshots. Browser binaries can alternatively be installed through Playwright's supported installer; set `CHROMIUM_PATH` to the executable.

## Data modes and source status

| Capability | Current status |
| --- | --- |
| Synthetic demo | Working; reproducible fake game logs across two years, fake future fixtures and fake public reports. All clearly labelled. Nothing is a real basketball fact. |
| CSV logs / schedules / public reports / team statistics | Working, validated and tested; user-supplied source URLs and publication times. Source authenticity and the truth of a report are the importer's responsibility. |
| ESPN roster and schedule adapter | Implemented; fixture-tested. Direct requests were rejected with HTTP proxy 403 in the build environment. Not verified with live responses. A successful refresh populates only real-data tables. |
| ESPN historical box scores | Implemented through scoreboard + event summary; fixture coverage is partial and live responses are unverified. Supports bounded historical fetches; CSV supports multiple seasons. |
| Live injury or minutes-restriction feed | Not implemented or independently verified. Import public team announcements / reporting with source links. No invented or inferred injuries. |
| AI | Optional OpenAI evidence selection; requires a server-side key and network access. No live AI call was verified. Without credentials, stored-facts answers work. |

Candidate public ESPN API URLs used by the adapter:

- `https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/teams`
- `https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/teams/{team_id}/roster`
- `https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates=YYYYMMDD`
- `https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary?event={event_id}`

These public endpoints are unofficial and may change or disallow access. No credential requirement has been established; no access-control bypass is attempted. Retries use normal verified HTTPS. Current roster matches resolve the stable internal player ID to an ESPN athlete/team ID; unmatched or traded historical identities need manual CSV records. Imported IDs stay stable when watchlists change. No numerical IDs are fabricated. Missing schedule means **no scheduled game in the loaded data**, not proof the league has no game.

For actual CSV source research, use the league's official game-center / player statistics and published team announcements, or licensed data exports you can access. If an export requires your credentials, obtain it from that provider's own UI and import the CSV locally; do not send credentials in chat. This project has not verified a licensed provider or claimed access to its feed. Team/opponent statistics can be imported with citations, but are not used for model adjustments without validation.

In cloud environment settings, the saved custom domains are `site.api.espn.com`, `site.web.api.espn.com` (candidate game-log API), and `api.openai.com` (optional AI), preserving package-manager presets. Saving the draft does not apply networking to the running machine. Review/save/publish through environment settings, then retry. A successful future request is needed before claiming live support. No new publication has been verified.

## CSV imports

Open **Data & sources**, download the selected CSV header template, and copy the player ID displayed in the dialog. Imports are UTF-8 and atomic: an invalid row rejects the whole upload. Maximum 5 MB / 20,000 rows per upload; split larger exports. Use `true`/`false` or `1`/`0` for boolean fields. Timestamps must include `Z` or an explicit offset. Blank times, missing source links, NaN and invalid ranges are rejected. Imports go into the real-data workspace even while demo is selected.

**Historical game logs**

```csv
player_id,id,game_at,available_at,minutes,points,appeared,source_url
```

- `id`: stable game/event ID. The same ID must be used in a future schedule and its final result to settle saved forecasts.
- `game_at`: scheduled start in ISO-8601. Only past games may be imported as results.
- `available_at`: when this exact statistical snapshot became public, at or after game start and no later than now. Do not use game start as a substitute for publication time. An accurate available_at timestamp is necessary for leakage-free tests. If unknown, use retrieval time: this is conservative and may leave too little history for backtests.
- `minutes`: 0–70; `points`: integer 0–150; `appeared`: false for missed games (then both numbers must be zero). Missing games never count as scoring zeros.
- `source_url`: public HTTP(S) URL without embedded credentials. Publication time is `available_at`; retrieval time is recorded automatically.
- Optional columns: `opponent`, `home`. They are displayed but do not change forecasts.
- Existing log snapshots cannot be revised in place. Keep the original database for audit and use a separate database for corrected historical datasets. The adapter also retains its earliest observed box-score snapshot.

**Upcoming schedules**

```csv
player_id,id,game_at,opponent,home,source_url
```

The app displays the earliest future game. Past scheduled events remain stored but are not shown as upcoming. Importing an existing schedule ID updates that schedule; already saved forecast snapshots retain their original fixture and source.

**Public news / availability**

```csv
player_id,id,published_at,title,text,status,confirmed,source_url,minutes_cap
```

`status` is `available`, `questionable`, `out`, or `unknown`. `confirmed` means the imported source explicitly states the status, not a model inference. Optional `minutes_cap` must be a publicly confirmed 0–70 minute restriction. Claims always show the imported source and publication/retrieval times. Speculation is displayed as unconfirmed and does not set status or a cap. Reports older than 48 hours cannot establish current availability. Fresh conflicting confirmed statuses yield unknown; all reports remain visible. Use distinct report IDs for updates. A fresh confirmed out status suppresses scoring outputs, while its status snapshot can still be saved.

**Team / opponent statistics**

```csv
player_id,id,published_at,team,metric,value,source_url
```

Context only. Shows publication and retrieval provenance on the detail page; not used by the baseline.

## Statistical method

Forecasts are **conditional on an appearance**. The app does not estimate whether a questionable/unknown player will appear. At least five timestamp-eligible, positive-minute appearances are needed. For minutes and points per minute, 65% weight comes from the recent five appearances and 35% from the latest season (falling back to up to 80 previous appearances when the season has fewer than five). Expected points is their product. Fresh confirmed minutes restrictions cap minutes for current forecasts only.

The predictive distribution is negative binomial, or Poisson when overdispersion is absent. Dispersion is estimated from squared errors of earlier recent-five means; each residual uses only that game's preceding records. Integer-support CDF/PMF calculations give below, above and exactly-on probabilities. A half-point threshold has zero tie probability. The 80% interval uses the 10th and 90th percentiles; discrete coverage can exceed the nominal rate. This is a baseline, not a validated guarantee of accuracy.

Recent/season blending captures broad changes in observed role. No explicit usage, shot volume, rest, back-to-back, home/away, opponent or teammate-absence coefficients are used. These more complex features have not demonstrated chronological out-of-sample improvement on verified real data. Private reproductive information and monthly/day-of-month patterns are not collected or used.

Walk-forward evaluation predicts every eligible appearance using only games and exact statistical snapshots with `game_at < target start` and `available_at < target start`. Each row is recomputed from an earlier prefix. It reports points MAE, recent-five scoring baseline MAE, 80% interval coverage, and missed-game counts separately. If the model's MAE is worse than the baseline, the dashboard still exposes both. It does not claim improvement. At least 20 evaluated appearances plus a user threshold are required for multiclass Brier score (below/tie/above) and binned above-threshold calibration.

Historical news is excluded because reliable contemporaneous snapshots were not available. Retrospectively fetched ESPN box scores are assigned the actual retrieval time as `available_at`, so they cannot masquerade as earlier publications. This may yield no historical predictions until trustworthy historical publication times are imported. Revisions and unavailable snapshots remain a limitation; user-provided false timestamps cannot be independently detected. Reconstructed walk-forward tests are labelled separately from genuinely saved pregame forecasts.

**Save forecast snapshot** appends timestamped forecasts for future scheduled events with model version, cutoff, threshold, fixture, current availability and reports. Updating never deletes older forecasts. Actual outcomes join by game ID and mode. Missed appearances are marked separately; pending games have no actual score. There is no sportsbook integration, betting automation, profit or ROI calculation.

## Optional AI and configuration

`.env.example` lists supported variables. The app reads process environment variables; it does not auto-load `.env`. Set `WNBA_DB`, `PORT`, `REFRESH_MINUTES`, `LLM_API_KEY` or `LLM_MODEL` in your terminal or hosting secret settings. Never commit actual credentials. `LLM_API_KEY` is sent only server-to-server to `https://api.openai.com/v1/chat/completions`; it never reaches the browser.

The language model receives the question and stored evidence and returns only evidence indices. The server renders existing fact text and citations, keeping all availability reports visible even if the AI omits them. This deliberately limits fluent generation: the LLM cannot invent numbers, probabilities, health claims or citations, or change model outputs. Without a key or when the request fails, the player question box returns grounded stored facts and a visible fallback message. No current live AI integration has been tested with credentials.

## Refresh, caching and scheduling

Manual refresh replaces the fetched ESPN schedule cache only after successful requests and retains imported schedules. Failed refreshes preserve existing records and show an error. Fetching 30 days can require many requests; daily refresh uses 15 schedule days plus roster calls. Multi-season bulk imports are preferred to repeatedly fetching a whole season.

```sh
.venv/bin/python manage.py refresh --history-days 30
# Refresh and append genuine pregame snapshots in the real-data workspace:
.venv/bin/python manage.py refresh --history-days 7 --save
# Refresh ONLY fictional demo dates/examples; leaves real records intact:
.venv/bin/python manage.py reset-demo
```

Optional built-in scheduler: export `REFRESH_MINUTES=60` before starting `app.py`; minimum enabled interval is 15 minutes. It runs only while this single server process runs, and does not save snapshots automatically. For a host without background jobs, invoke `manage.py refresh --save` using a host scheduler or your computer's cron/Task Scheduler. Example hourly Linux cron entry, adjusted to your extracted project location:

```cron
0 * * * * cd /absolute/path/Courtwise && .venv/bin/python manage.py refresh --history-days 7 --save >> data/refresh.log 2>&1
```

The computer/host must be running. Use a persistent volume for SQLite. An offline app does not fetch news, schedules or statistics. A paused free web host needs an external scheduler or manual refresh; no deployment-specific background capability is assumed.

## Architecture

`model.py`: pure statistical model and chronological evaluation. `store.py`: SQLite persistence and labelled demo generation. `ingest.py`: strict CSV ingestion and public API adapter. `app.py`: Flask routes, grounded Q&A and optional in-process scheduler. `manage.py`: runnable scheduling CLI. `static/` and `templates/`: responsive UI, SVG chart, loading/error/empty states. Tests exercise leakage, distribution partitioning, imports, statuses, stable identities, history preservation and browser workflows.
