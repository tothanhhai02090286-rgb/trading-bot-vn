# V19.4.1 — Signal Family Comparison Engine

## Bản này nâng cấp gì?

So sánh theo từng nhóm tín hiệu:

```text
BREAKOUT: 5D / 10D / 20D
PULLBACK: MA5 / MA10 / MA20
RELATIVE_STRENGTH: RS5 / RS10 / RS20
VOLUME_FILTER: 1.2x / 1.5x / 2.0x
```

## File output quan trọng nhất

```text
tracker_output/v194_family_compare.csv
```

File này cho biết từng nhóm và từng biến thể cái nào hiệu quả hơn.

## Output đầy đủ

```text
tracker_output/v194_historical_signal_validation.csv
tracker_output/v194_signal_stats.csv
tracker_output/v194_family_compare.csv
tracker_output/v194_regime_stats.csv
tracker_output/v194_baseline_comparison.csv
tracker_output/v194_bad_signal_patterns.csv
tracker_output/v194_report.txt
```

## Cách upload

1. Upload `v194_signal_validation_engine_vi.py` vào root repo để thay bản V19.4 cũ.
2. Upload `run-v194-signal-validation.yml` vào `.github/workflows/` để thay workflow cũ.
3. Commit.
4. Vào GitHub Actions → Run V19.4 Signal Validation → Run workflow.

## Lưu ý

Đây là validation engine, không phải máy tối ưu tham số. Kết quả xấu cũng có giá trị vì giúp loại tín hiệu yếu.
