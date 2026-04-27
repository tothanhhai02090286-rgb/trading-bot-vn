# 🚀 TRADING SYSTEM SPEC

## ENGINE
- Batch trading bot
- Source: KBS (vnstock)
- Batch size: 20
- GitHub Actions auto run 17h → 20h30

## MOMENTUM FILTER
- MA5 > MA20
- RSI 55–75
- Ret5 > 2%
- Ret10 > 3%
- RS20 > 0
- Volume ratio > 1.2
- ADX > 20
- ATR% <= 8
- MACD histogram tăng
- Dist MA20 0–12%

## BOTTOM FILTER
- RSI 30–48
- Drawdown 20P <= -5%
- Rebound from low >= 1%
- Volume >= 0.8
- Không thủng đáy 20 phiên
- ATR% <= 9
- RS20 > -8
- Dist MA20 <= 3
## NOTE
- Đây là bản mô tả chiến lược PRO_V1.
- Code chính nằm trong run_daily_system.py.
- Output chính gồm: all_signal_results.csv, ai_risk_filtered.csv, bottom_common_priority.csv, momentum_common_priority.csv, entry_plan_next_session.csv
- ## OUTPUT FILES
- all_signal_results.csv: toàn bộ kết quả đã quét
- ai_risk_filtered.csv: bảng chính cho dashboard
- bottom_common_priority.csv: danh sách bắt đáy
- momentum_common_priority.csv: danh sách mã mạnh
- entry_plan_next_session.csv: kế hoạch xử lý phiên sau
- progress_state.csv: nhớ batch đã chạy tới đâu

## SCHEDULE
- Chạy tự động qua GitHub Actions
- Cron: 0,30 10-13 * * 1-5
- Tương đương 17:00 → 20:30 giờ Việt Nam, thứ 2–6
- Mỗi lần chạy 20 mã
- Một tối quét được khoảng 160 mã

## DATA RULES
- Chỉ dùng source KBS
- Nếu API lỗi thì retry
- Nếu mã không đủ dữ liệu thì bỏ qua
- Không dùng dữ liệu random

## STRATEGY VERSION
- Version: PRO_V1
- Logic cũ MA + RSI được giữ làm lõi
- Logic mới RS + Volume + ATR + MACD + ADX dùng để lọc nhiễu

## NEXT UPGRADE
- Top 10 signals
- Portfolio holding status
- Action plan: MUA / GIỮ / GIẢM / BÁN
- Telegram alert
