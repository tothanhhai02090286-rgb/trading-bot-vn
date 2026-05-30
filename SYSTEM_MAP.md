SYSTEM_MAP.md — Trading Bot VN (v1)

1. LIVE CORE (ĐANG CHẠY THẬT)

Realtime Engine

realtime/intraday_alert_bot.py

Chức năng:

* polling realtime
* đọc watchlist RAW GitHub
* lọc realtime
* gửi Telegram ENTRY
* V18.2 execution recommendation

Render Procfile

realtime/Procfile

Current live command:

python -u intraday_alert_bot.py
(cd /opt/render/project/src && V192_RUN_ONCE=0 python -u v19.danh_muc_mua/v192_realtime_position_telegram_desk_vi.py)
python -m http.server $PORT

V19 Position Realtime

v19.danh_muc_mua/v192_realtime_position_telegram_desk_vi.py

Chức năng:

* realtime position monitoring
* price guard
* Telegram position alert
* intraday risk guard

V19.3 Journal Sync

v19.3_alert_lichsu_canhbao/v1931_github_journal_sync.py

Chức năng:

* push tracker_output lên GitHub
* sync journal
* daily summary
* alert statistics

⸻

2. DAILY PIPELINE (NGUỒN TẠO DỮ LIỆU)

Workflow chính

.github/workflows/run-daily-cache-only.yml

Vai trò:

* generate intraday watchlist
* update cache
* publish CSV
* prepare realtime input

Workflow research / integrated

.github/workflows/run-v153-v1541-v155-v16-v171-integrated.yml

Vai trò:

* lớp lọc bổ sung
* integrated research
* experimental pipeline

STATUS:

NOT PRIMARY LIVE PIPELINE

⸻

3. DATA / STATE

Watchlist realtime

intraday_watchlist_v17.csv

Source of truth cho:

* Render realtime
* V18 realtime engine

Position tracking

positions_v19.csv

Tracker outputs

tracker_output/
├── alert_journal_v193.csv
├── v193_daily_summary.csv
├── v193_alert_stats.csv

⸻

4. OPS / INFRA

Render

Platform:

Render.com

Branch:

main

Realtime worker:

trading-bot-vn

Important ENV

Public RAW

GITHUB_RAW_WATCHLIST_URL
RAW_URL
RAW_URL_CACHE_BUST

Telegram

TELEGRAM_TOKEN
TELEGRAM_CHAT_ID

Realtime

CHECK_INTERVAL_SEC
MARKET_START
MARKET_END

GitHub Sync

GITHUB_SYNC_TOKEN

IMPORTANT:

DO NOT USE GITHUB_TOKEN FOR PUBLIC RAW FETCH

⸻

5. TOKEN ARCHITECTURE

V18 Realtime

NO AUTH REQUIRED

Uses:

* public RAW URL only

V19.3 Sync

Uses:

GITHUB_SYNC_TOKEN

Permissions:

Contents → Read and write
Metadata → Read

⸻

6. BACKUP STRATEGY

Stable backup branch

Example:

backup-stable-2026-05-30

Rule

Before major change:

git checkout -b backup-YYYY-MM-DD
git push origin backup-YYYY-MM-DD

⸻

7. CURRENT SYSTEM STATUS

VERIFIED OK

* Render realtime running
* RAW watchlist fetch OK
* Telegram OK
* V19 sync OK
* GitHub push OK
* Token permissions OK

Current architecture

GitHub Actions
    ↓
Generate watchlist CSV
    ↓
GitHub RAW
    ↓
Render realtime engine
    ↓
Telegram alerts

⸻

8. IMPORTANT RULES

DO NOT randomly move:

* realtime/
* v19 live files
* workflow live files

DO NOT:

* reuse expired tokens
* use one token for everything

ALWAYS:

* backup before major refactor
* test Render logs after deploy
* keep realtime layer independent
