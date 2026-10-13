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
| ESPN roster and schedule adapter | Verified against live responses on 13 October 2026. All five player IDs resolved; no next-14-day game was returned for those players during that check. Only real-data tables are populated. |
| ESPN historical game logs | Verified live: 662 regular/postseason game logs for the five players across 2024–2026. The new three-season loader uses the common game-log API and excludes All-Star games. The separate scoreboard/event-summary fallback remains fixture-tested. |
| Public ESPN news / injury feed | Verified live: 28 relevant article/report snapshots. Article matching uses athlete IDs or full names because the upstream player query is ignored. Structured public injury status is used conservatively; source publication dates and links are retained. General news never implies clearance. Minutes caps still require a confirmed CSV report. |
| AI | Optional OpenAI evidence selection; requires a server-side key and network access. No live AI call was verified. Without credentials, stored-facts answers work. |

Public ESPN API URLs used by the adapters:

- `https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/teams`
- `https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/teams/{team_id}/roster`
- `https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates=YYYYMMDD`
- `https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary?event={event_id}`
- `https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/news?limit=100`
- `https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/injuries?limit=100`
- `https://site.web.api.espn.com/apis/common/v3/sports/basketball/wnba/athletes/{athlete_id}/gamelog?season={year}`

These public endpoints are unofficial and may change or disallow access. No credential requirement has been established; no access-control bypass is attempted. Retries use normal verified HTTPS. Current roster matches resolve the stable internal player ID to an ESPN athlete/team ID; unmatched or traded historical identities need manual CSV records. Imported IDs stay stable when watchlists change. No numerical IDs are fabricated. Missing schedule means **no scheduled game in the loaded data**, not proof the league has no game.

For actual CSV source research, use the league's official game-center / player statistics and published team announcements, or licensed data exports you can access. If an export requires your credentials, obtain it from that provider's own UI and import the CSV locally; do not send credentials in chat. This project has not verified a licensed provider or claimed access to its feed. Team/opponent statistics can be imported with citations, but are not used for model adjustments without validation.

In cloud environment settings, the saved custom domains are `site.api.espn.com`, `site.web.api.espn.com` (game logs), and `api.openai.com` (optional AI), preserving package-manager presets. Live ESPN requests succeeded on 13 October 2026; they were blocked during the initial build. Availability can differ on your machine or after policy changes. Saving a draft does not apply or publish it; review/save/publish through environment settings separately. No new cloud publication has been verified.

## Real-data buttons and calendar-day chart

Open **Data & sources → Load last 3 seasons of real logs**, then choose **Use my data**. The loader defaults to the current year and preceding two years, gets regular/postseason appearance records, skips All-Star/preseason and future events, and never overwrites an earlier game snapshot. **Refresh ESPN news & reports** loads relevant public articles and structured injury reports. **Refresh sources** also fetches upcoming schedules and attempts a news refresh; if news alone fails, it retains the successful schedule refresh and displays the warning. An absent upcoming game is not filled in with a fake fixture.

History imports return a job immediately, then display phase/count/elapsed progress beside the button. Use **Cancel import** to cancel before saving, and **View imported data** after completion to switch from demo to the real-data workspace. Requests run with at most three parallel ESPN downloads, ten-second socket timeouts, bounded response reads and a two-minute import deadline. A failed or cancelled import rolls back pending game writes; earlier snapshots remain. Repeated clicks reuse an active job instead of starting another. Completion and errors are visible beside the button, not only below the CSV form. Job status is kept in the single server process; restarting it interrupts a pending job and requires starting a new import. Browser requests also time out explicitly. This personal runner is single-process; multi-worker hosting needs shared job storage before deployment.

Each player's **Scoring by day of the month** chart has 31 calendar-day buckets using Australia/Sydney, with an all-season/year filter, average points, observed range, sample sizes and source-linked underlying appearances. Missing days have no average; missed appearances are excluded. Fewer than five appearances is visibly flagged. The highlighted day defaults to the next loaded game's Sydney date, or today's date if no fixture is loaded. With a user threshold, it shows **historical observed frequencies**, not future probabilities or a recommended bet.

Calendar dates never enter the numerical forecasting model or imply private health conditions. Calendar differences can reflect opponent, minutes, season, role, schedule or chance. The diagnostic compares earlier same-date averages with recent-five and the current model on identical chronological targets, requiring five earlier same-date appearances per target and at least 20 targets for even an exploratory result. All inputs must have been published before the target. The live retrospective import gave zero eligible historical calendar tests because those snapshots were first retrieved now; it cannot establish predictive improvement. A lower descriptive average does not establish a profitable under bet. No odds or ROI are calculated.

The public injury feed lacks athlete.id but includes verified player-card links; stable IDs are resolved from those links rather than guessed from names. Each article revision and changed injury report is retained as a separate snapshot. The feed's original injury report date is used, not the new fetch date, so refreshing does not resurrect an old report as current. Reports older than 48 hours do not set present status. Fresh contradictory status reports yield unknown. Unfamiliar status is not inferred. Public article headlines/excerpts do not set availability, and roster Active status is not treated as clearance. An undisclosed injury is displayed only when a source explicitly reports one; no undisclosed detail is invented. Source injury descriptions are attributed to ESPN, not independently medically verified. Read the dated source before relying on a status; this feed can be incomplete or stale. Public confirmed minutes restrictions can still be imported with citations.

A Windows update guide is in [UPDATE-WINDOWS.md](UPDATE-WINDOWS.md). The new backend uses pinned `tzdata` so Sydney time works on Windows as well as Linux.

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

`calendar_stats.py`: descriptive Sydney calendar-day averages and matched chronological comparisons, never scoring-model features. `model.py`: pure statistical model and chronological evaluation. `store.py`: SQLite persistence and labelled demo generation. `ingest.py`: strict CSV ingestion and public API adapter. `app.py`: Flask routes, grounded Q&A and optional in-process scheduler. `manage.py`: runnable scheduling CLI. `static/` and `templates/`: responsive UI, SVG chart, loading/error/empty states. Tests exercise leakage, distribution partitioning, imports, statuses, stable identities, history preservation and browser workflows.
