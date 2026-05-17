# V20.1 FULL — Entry + Market Context

## Gồm 2 phần

### 1. Replay lịch sử

File:

```text
v201_entry_market_context_replay_engine_vi.py
```

Chạy cuối tuần để phân tích:

```text
entry_context
market_context
fail_patterns
win_patterns
rules_for_v18
```

### 2. Module realtime cho V18.2

File:

```text
v201_entry_context_filter.py
```

Dùng để import vào V18.2:

```python
from v201_entry_context_filter import classify_entry_context_realtime, apply_entry_context_cap
```

## Output replay

```text
tracker_output/v201_context_replay.csv
tracker_output/v201_entry_context_summary.csv
tracker_output/v201_market_context_summary.csv
tracker_output/v201_fail_patterns.csv
tracker_output/v201_win_patterns.csv
tracker_output/v201_context_rules_for_v18.csv
tracker_output/v201_context_report.txt
```

## Cách upload

1. Upload 2 file `.py` vào root repo:
   - `v201_entry_market_context_replay_engine_vi.py`
   - `v201_entry_context_filter.py`

2. Upload workflow vào `.github/workflows/`:
   - `run-v201-entry-market-context.yml`

3. Commit.

4. Actions → Run V20.1 Entry Market Context Replay → Run workflow.

## Gắn vào V18.2

Sau khi V18.2 build xong recommendation, gọi:

```python
ctx = classify_entry_context_realtime(
    price=price,
    vwap=vwap,
    ref=ref,
    buy_low=low,
    buy_high=high,
    session_high_prev=session_high_prev,
    volume_ratio=volume_ratio,
    market_context=market_context,
)

final_rec = apply_entry_context_cap(final_rec, ctx)
```

## Nguyên tắc

V20.1 chỉ dùng để hạ rủi ro:

```text
ENTRY LƯNG CHỪNG -> WATCH
ENTRY FOMO -> WATCH / KHÔNG VÀO
MARKET RISK-OFF -> WATCH / KHÔNG VÀO
```

Không dùng V20.1 để tự động nâng BUY lớn.
