# Portfolio Intelligence Engine (PIE)

Patch gộp Phase 10 → 14 cho V19.2 Position Telegram Desk.

## Mục tiêu
PIE bổ sung một lớp quản trị danh mục/vốn, **không ghi đè logic mua/bán hiện tại**.

## Module mới

```text
v19.danh_muc_mua/vn_portfolio_intelligence.py
```

## File tích hợp

```text
v19.danh_muc_mua/v192_realtime_position_telegram_desk_vi.py
```

## Feature flag

```text
VN_PORTFOLIO_INTELLIGENCE_ON=1
```

## Các lớp trong PIE

1. Portfolio Exposure Manager: đề xuất Cash/Stock/Margin theo Mini Market + Adjusted Rotation.
2. Portfolio Health Engine: tổng hợp Position Health của toàn danh mục.
3. Risk Budget Engine: ước tính risk đã dùng và còn lại.
4. Position Sizing Guardrail: đưa trần size vị thế mới theo NAV.
5. Drawdown Protection: giới hạn exposure khi tài khoản drawdown.

## Env tùy chỉnh

```text
VN_PORTFOLIO_MAX_RISK_BUDGET_PCT=10
VN_PORTFOLIO_DEFAULT_RISK_PER_POSITION_PCT=1
VN_PORTFOLIO_DRAWDOWN_PCT=0
VN_PORTFOLIO_MAX_POSITION_PCT=15
VN_PORTFOLIO_MAX_NEW_POSITION_PCT=8
```

## Telegram START cần có

```text
Portfolio Intelligence: ON
```

## Telegram detail sẽ có block

```text
📊 Portfolio Intelligence

Trạng thái: 🔴 RISK OFF
Portfolio Health: 10/100 🔴 CRITICAL

Exposure đề xuất:
Cash 90% | Stock 10% | Margin 0%

Risk Budget:
Used ... / Max ... | Còn lại ...

Position Sizing:
Max vị thế mới ...% NAV

Drawdown Protection:
...
```

## Nguyên tắc an toàn

- PIE chỉ là lớp context/guardrail.
- Không thay đổi kết luận `Hành động V19.2`.
- Không ghi đè Position State, VN Trade Safety, Mini Market hoặc Leader Rotation.
