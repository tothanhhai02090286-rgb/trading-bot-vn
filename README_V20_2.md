# V20.2 — Context Drilldown + Rule Generator

## Vai trò

V20.2 khoan sâu nguyên nhân WIN/FAIL thay vì chỉ nói chung chung.

Nó phân tích:

```text
FOMO
market overheating
distance MA20
volume spike
base quality
sideway
volatility contraction
drawdown risk
combo 2-3 điều kiện
```

## File chính

```text
v202_context_drilldown_engine_vi.py
v202_realtime_rule_filter.py
run-v202-context-drilldown.yml
```

## Output

```text
tracker_output/v202_drilldown_patterns.csv
tracker_output/v202_fail_rules.csv
tracker_output/v202_win_rules.csv
tracker_output/v202_realtime_rules_for_v18.csv
tracker_output/v202_context_report.txt
```

## Cách upload

1. Upload 2 file `.py` vào root repo:
   - `v202_context_drilldown_engine_vi.py`
   - `v202_realtime_rule_filter.py`

2. Upload workflow vào `.github/workflows/`:
   - `run-v202-context-drilldown.yml`

3. Commit.

4. Actions → Run V20.2 Context Drilldown → Run workflow.

## Cách đọc

Đọc trước:

```text
tracker_output/v202_context_report.txt
```

Sau đó xem:

```text
tracker_output/v202_realtime_rules_for_v18.csv
```

## Gắn vào V18.2

Sau khi V18.2 có recommendation:

```python
from v202_realtime_rule_filter import evaluate_v202_realtime_context, apply_v202_rule_cap

v202 = evaluate_v202_realtime_context(
    price=price,
    vwap=vwap,
    ma20=ma20,
    ref=ref,
    volume_ratio=volume_ratio,
    stock_ret5=stock_ret5,
    stock_ret20=stock_ret20,
    market_ret5=market_ret5,
    market_dist_ma20_pct=market_dist_ma20_pct,
    market_context=market_context,
)

final_rec = apply_v202_rule_cap(final_rec, v202)
```

## Nguyên tắc

V20.2 chỉ dùng để hạ rủi ro:

```text
FOMO -> WATCH
market nóng + cổ phiếu xa MA20 -> WATCH
giá dưới MA20 + dưới VWAP -> WATCH/KHÔNG VÀO
```

Không dùng V20.2 để tự động nâng BUY lớn.
