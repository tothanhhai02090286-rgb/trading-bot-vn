# V19.3.1 — GitHub Persistent Journal

## Mục tiêu

Đồng bộ `alert_journal_v193.csv` từ Render local về GitHub để không mất dữ liệu sau restart/redeploy.

## File thêm mới

```text
v19.3_alert_lichsu_canhbao/v1931_github_journal_sync.py
```

## Output trên GitHub

```text
tracker_output/
 ├── alert_journal_v193.csv
 ├── v193_daily_summary.csv
 └── v193_alert_stats.csv
```

## ENV cần thêm trên Render

```text
V193_GITHUB_SYNC_ENABLE=1
GITHUB_TOKEN=...
GITHUB_REPO=owner/repo
GITHUB_BRANCH=main
V193_JOURNAL_LOCAL_PATH=alert_journal_v193.csv
V193_JOURNAL_REMOTE_PATH=tracker_output/alert_journal_v193.csv
V193_GITHUB_SYNC_MIN_INTERVAL_SEC=60
```

## GITHUB_TOKEN cần quyền gì?

Token cần quyền ghi repo:

```text
Contents: Read and Write
```

## Patch vào V18.2

Trong `intraday_alert_bot.py`, thêm import:

```python
from v1931_github_journal_sync import sync_journal_to_github
```

Sau `log_entry_alert(...)`, thêm:

```python
sync_journal_to_github()
```

## Patch vào V19.2

Trong `v19.danh_muc_mua/v192_realtime_position_telegram_desk_vi.py`, thêm import:

```python
from v1931_github_journal_sync import sync_journal_to_github
```

Sau `log_position_alert(...)`, thêm:

```python
sync_journal_to_github()
```

## Lưu ý

- Không đổi start command.
- Không gọi thêm API giá.
- Nếu sync GitHub lỗi, bot vẫn tiếp tục chạy.
