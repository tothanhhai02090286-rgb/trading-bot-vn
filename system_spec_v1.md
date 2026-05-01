# 🚀 TRADING BOT SYSTEM SPEC (VN STOCK)

## 📌 OVERVIEW
Hệ thống trading bot cổ phiếu Việt Nam chạy batch trên GitHub Actions.

Mục tiêu:
- Tự động lọc cổ phiếu theo tín hiệu kỹ thuật
- Phân loại hành động: MUA / CHỜ / THEO DÕI / BỎ QUA
- Xuất dashboard HTML + gửi Telegram
- Nâng cấp dần sang AI decision system

----

# ⚙️ SYSTEM ARCHITECTURE

## ENGINE
- Batch trading system
- Chạy qua GitHub Actions
- Dữ liệu từ:
  - Cache CSV (ưu tiên)
  - vnstock (fallback)

## DATA STORAGE
- cache_stock/*.csv
- all_signal_results.csv
- entry_plan_next_session.csv
- action_plan.csv
- ai_risk_dashboard.html

---

# 📊 INDICATORS

- MA5, MA20
- RSI (14)
- ATR (%)
- Volume Ratio (so với MA20 volume)
- Ret5 %, Ret10 %, Ret20 %
- Drawdown 20 phiên
- Rebound từ đáy 20 phiên
- MACD Histogram

---

# 🧠 CORE LOGIC

## 1. MOMENTUM FILTER
- MA5 > MA20
- RSI: 55–75
- Ret5 > 2%
- Ret10 > 3%
- Ret20 > 0
- Volume Ratio > 1.2
- ATR <= 8%
- MACD histogram tăng
- Dist MA20: 0–12%

## 2. BOTTOM FILTER
- RSI: 30–48
- Drawdown 20P <= -5%
- Rebound >= 1%
- Volume >= 0.8
- ATR <= 9%
- Ret20 > -8%
- Dist MA20 <= 3%
- MACD histogram tăng

---

# 🎯 SIGNAL CLASSIFICATION

| Điều kiện | Kết quả |
|----------|--------|
| Score >= 85 | MUA |
| Score >= 70 | CHỜ |
| Score >= 55 | THEO DÕI |
| else | BỎ QUA |

---

# ⚠️ RISK FILTER

Loại bỏ nếu:
- RSI >= 90
- ATR > 10%
- Volume Ratio < 0.6
- Momentum nhưng giá < MA20

---

# 🌍 MARKET REGIME

Dựa vào VNINDEX / VN30:

| Ret20 | Regime |
|------|--------|
| >= 5% | TĂNG MẠNH |
| >= 1% | TÍCH CỰC |
| -2 → 1 | SIDEWAY |
| -5 → -2 | YẾU |
| < -5 | GIẢM MẠNH |

---

# 📦 V12 CORE STABLE

## MỤC TIÊU
- Chạy ổn định 100%
- Không lỗi font
- Không crash
- Telegram OK
- Dashboard đọc được

## BAO GỒM
- Indicator
- Momentum / Bottom
- Score + Action
- Market regime
- CSV output
- Dashboard HTML
- Telegram alert

## KHÔNG BAO GỒM
- AI
- OOS
- Backtest
- Predict

---

# 🤖 V12 PRO FINAL (UPGRADE)

## 1. AI FILTER
- AI Score
- AI Grade
- AI Action

## 2. BACKTEST + OOS
- OOS Win%
- OOS Samples
- Status (STRONG / WEAK)

## 3. REGIME PERFORMANCE
- Win theo regime
- Regime probability

## 4. TRUST SCORE
- HIGH / MEDIUM / LOW

## 5. EXPLAIN SIGNAL
Ví dụ:
- RSI tốt
- Volume xác nhận
- Momentum mạnh

## 6. ENTRY PLAN
- Buy zone
- Stop loss

## 7. 📈 DỰ BÁO LỢI NHUẬN

Dựa trên pattern + OOS:

Ví dụ:
- +3 ngày: +2.1%
- +5 ngày: +3.8%
- +10 ngày: +5.2%

## 8. TELEGRAM + DASHBOARD

Telegram:
- Phân nhóm:
  - 🔥 Ưu tiên
  - ⚠️ Chờ
  - 👀 Theo dõi

Dashboard:
- Bảng rõ ràng
- Không lỗi font
- Đọc dễ (ưu tiên tiếng Việt)

---

# ⚠️ NGUYÊN TẮC PHÁT TRIỂN

- Không patch chồng
- Mỗi version build từ nền sạch
- Backend dùng ASCII (tránh lỗi font)
- UI hiển thị tiếng Việt
- Test từng bước trước khi nâng cấp

---

# 📌 NEXT STEP

Hiện tại:
👉 Đang ở V12 CORE STABLE

Tiếp theo:
👉 Build V12 PRO FINAL

---

# 🧩 NOTES

- Nếu hệ thống lỗi:
  → quay về CORE
- Nếu thiếu dữ liệu:
  → bỏ AI / OOS
- Nếu chạy chậm:
  → giảm batch size