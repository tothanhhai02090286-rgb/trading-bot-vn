# V20 — Context Replay & Trade Review Engine

## Vai trò

V20 không tìm thêm indicator. Nó replay bối cảnh trước tín hiệu để hiểu WIN khác FAIL ở đâu.

## Input ưu tiên

V20 tự tìm theo thứ tự:

```text
tracker_output/v195_weighted_signals.csv
tracker_output/v194_historical_signal_validation.csv
tracker_output/v1942_quality_filtered_signals.csv
```

## Output

```text
tracker_output/v20_context_replay.csv
tracker_output/v20_win_fail_context_summary.csv
tracker_output/v20_fail_patterns.csv
tracker_output/v20_win_patterns.csv
tracker_output/v20_context_report.txt
```

## Đọc file nào trước?

Đọc:

```text
v20_context_report.txt
```

Sau đó xem:

```text
v20_fail_patterns.csv
v20_win_patterns.csv
```

## Cách upload

1. Upload `v20_context_replay_trade_review_engine_vi.py` vào root repo.
2. Upload `run-v20-context-replay.yml` vào `.github/workflows/`.
3. Commit.
4. Actions → Run V20 Context Replay → Run workflow.
