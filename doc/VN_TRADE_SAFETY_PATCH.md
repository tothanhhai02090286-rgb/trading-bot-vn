# VN Trade Safety Patch

Patch này thêm lớp an toàn giao dịch cho TTCK Việt Nam.

## File mới

- `vn_trade_safety.py`
- `realtime/vn_trade_safety.py`

Mình đặt một bản ở root và một bản trong `realtime/` để tránh lỗi import khi Render chạy từ thư mục khác nhau.

## File đã sửa

- `realtime/intraday_alert_bot.py`
- `v19.danh_muc_mua/v192_realtime_position_telegram_desk_vi.py`

## Logic mới

### 1. Liquidity Filter

Dựa trên dữ liệu `cache_stock/<MÃ>.csv`, hệ thống tính:

- Giá trị giao dịch trung bình 20 phiên
- Khối lượng trung bình 20 phiên
- Band thanh khoản: `MỎNG`, `YẾU`, `TRUNG BÌNH`, `ỔN`

Ngưỡng mặc định:

- `< 10 tỷ/ngày`: không mua mới
- `10 đến 30 tỷ/ngày`: chỉ test nhỏ
- `30 đến 50 tỷ/ngày`: chỉ mua nhỏ
- `> 50 tỷ/ngày`: cho phép xét bình thường

Có thể chỉnh bằng biến môi trường:

```txt
VN_MIN_AVG_VALUE_BN_BLOCK=10
VN_MIN_AVG_VALUE_BN_TEST=30
VN_MIN_AVG_VALUE_BN_NORMAL=50
VN_TRADE_SAFETY_ON=1
```

### 2. Ceiling/Floor Risk

Mặc định giả định HOSE biên độ 7%, HNX 10%, UPCoM 15%.

Có thể chỉnh bằng biến môi trường:

```txt
VN_HOSE_LIMIT_PCT=7
VN_HNX_LIMIT_PCT=10
VN_UPCOM_LIMIT_PCT=15
VN_NEAR_CEIL_FLOOR_BUFFER=0.01
```

Nếu giá gần trần, bot không đuổi mua.
Nếu giá gần sàn, bot chặn mua mới và cảnh báo rủi ro kẹt hàng.

### 3. V18 Realtime

`intraday_alert_bot.py` bây giờ có thêm phần:

```txt
VN Trade Safety:
Thanh khoản
GTGD 20 phiên
Exit risk
Safety score
```

Khuyến nghị có thể bị hạ từ `BUY NHỎ` xuống `TEST NHỎ`, `WATCH`, hoặc `KHÔNG VÀO`.

### 4. V19.2 Position Desk

`v192_realtime_position_telegram_desk_vi.py` bây giờ có thêm phần Safety vào snapshot và Telegram.

Nếu có tín hiệu bán nhưng mã thanh khoản yếu hoặc gần sàn, hành động có thể chuyển thành:

```txt
THOÁT KHI CÓ THANH KHOẢN
```

Ý nghĩa: tín hiệu bán có rủi ro không khớp ngay, nên ưu tiên thoát khi có lực cầu thay vì tin rằng stoploss luôn thực hiện được.

## Cách dùng

Copy các file trong patch này đè vào repo hiện tại, commit lên GitHub rồi deploy lại Render/GitHub Actions.

Nên bật mặc định:

```txt
VN_TRADE_SAFETY_ON=1
```

Nếu cần rollback nhanh:

```txt
VN_TRADE_SAFETY_ON=0
```
