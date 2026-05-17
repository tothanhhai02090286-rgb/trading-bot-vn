# V19.4.2 — Quality Filter Test

## Vai trò

Bản này không test tràn lan nữa. Nó chỉ test `PULLBACK_MA20` sau khi qua bộ lọc chất lượng.

## Quality filter

```text
- Regime không quá xấu
- Không mua khi giá quá xa MA20
- Volume đủ nhưng không quá FOMO
- RS20 mạnh nhưng không tăng nóng
- Drawdown trước đó không quá sâu
- Chỉ test PULLBACK_MA20
```

## Output

```text
tracker_output/v1942_quality_filtered_signals.csv
tracker_output/v1942_quality_stats.csv
tracker_output/v1942_quality_regime_stats.csv
tracker_output/v1942_quality_baseline_comparison.csv
tracker_output/v1942_quality_bad_patterns.csv
tracker_output/v1942_quality_report.txt
```

## Cách upload

1. Upload `v1942_quality_filter_pullback_ma20_vi.py` vào root repo.
2. Upload `run-v1942-quality-filter.yml` vào `.github/workflows/`.
3. Commit.
4. Vào Actions → Run V19.4.2 Quality Filter Test → Run workflow.

## Lưu ý

Nếu kết quả vẫn yếu, không phải lỗi. Nghĩa là logic PULLBACK_MA20 cần lọc chặt hơn hoặc không phù hợp giai đoạn dữ liệu hiện tại.
