# 🚀 TRADING SYSTEM SPEC

## VERSION
- PRO_V1 (updated)
- Date: 2026-04-28

## STRATEGY VERSION
- Version: PRO_V1
- Core logic: MA + RSI
- Noise filter: RS + Volume + ATR + MACD + ADX
- Data source: KBS via vnstock
- No random data

## ENGINE
- Batch trading bot
- Batch size: 20 symbols/run
- Run via GitHub Actions
- Time: 17:00 → 20:30 Vietnam time
- Cron: 0,30 10-13 * * 1-5
- Estimated scan: ~160 symbols/night

## MOMENTUM FILTER
- MA5 > MA20
- RSI 55–75
- Ret5 > 2%
- Ret10 > 3%
- RS20 > 0
- Volume ratio > 1.2
- ADX > 20
- ATR% <= 8%
- MACD histogram tăng
- Distance from MA20: 0–12%

## BOTTOM FILTER
- RSI 30–48
- Drawdown 20P <= -5%
- Rebound from low >= 1%
- Volume ratio >= 0.8
- Không thủng đáy 20 phiên
- ATR% <= 9%
- RS20 > -8
- Distance from MA20 <= 3%

## ENTRY RULES
- BUY NOW: tín hiệu mạnh, không vi phạm risk filter
- WAIT: có tín hiệu nhưng chưa đủ xác nhận
- WATCHLIST: gần đạt điều kiện, cần theo dõi thêm
- SKIP: yếu, nhiễu, thiếu dữ liệu hoặc rủi ro cao

## RISK FILTER
- Nếu VNINDEX dưới MA20: giảm điểm tín hiệu
- Nếu VNINDEX giảm mạnh: không BUY NOW
- Nếu ATR% quá cao: loại
- Nếu volume yếu: không BUY NOW
- Nếu RS20 quá yếu: loại

## OUTPUT FILES
- all_signal_results.csv: toàn bộ kết quả quét
- ai_risk_filtered.csv: bảng chính cho dashboard
- bottom_common_priority.csv: danh sách bắt đáy
- momentum_common_priority.csv: danh sách mã mạnh
- entry_plan_next_session.csv: kế hoạch xử lý phiên sau
- progress_state.csv: nhớ batch đã chạy tới đâu

## NEXT UPGRADE
- Top 10 signals
- Portfolio holding status
- Action plan: MUA / GIỮ / GIẢM / BÁN
- Telegram alert
