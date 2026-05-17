# V19.5 — Weighted Signal Scoring Engine

## Vai trò

V19.5 không dùng một tín hiệu đơn lẻ để quyết định. Nó chấm điểm tổng hợp nhiều yếu tố:

```text
Regime
Trend
RS
Pullback / distance MA20
Volume
Momentum
Drawdown
Breakout context
```

Sau đó kiểm chứng các ngưỡng:

```text
score >= 60
score >= 70
score >= 80
```

## Output

```text
tracker_output/v195_weighted_signals.csv
tracker_output/v195_score_threshold_stats.csv
tracker_output/v195_factor_bucket_stats.csv
tracker_output/v195_regime_score_stats.csv
tracker_output/v195_bad_score_patterns.csv
tracker_output/v195_baseline_comparison.csv
tracker_output/v195_report.txt
```

## Cách upload

1. Upload `v195_weighted_signal_scoring_engine_vi.py` vào root repo.
2. Upload `run-v195-weighted-signal-scoring.yml` vào `.github/workflows/`.
3. Commit.
4. Actions → Run V19.5 Weighted Signal Scoring → Run workflow.

## Mục tiêu đọc kết quả

Đọc trước:

```text
v195_report.txt
v195_score_threshold_stats.csv
```

Nếu `score >= 70` hoặc `score >= 80` có winrate và avg return tốt hơn rõ rệt, weighted score có giá trị.
