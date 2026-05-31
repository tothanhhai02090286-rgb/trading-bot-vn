# VN Sector Money Flow Patch

## Mục tiêu

Patch này thêm lớp **Sector Money Flow** cho bot chứng khoán Việt Nam. Lớp này giúp bot đánh giá cổ phiếu theo bối cảnh dòng tiền ngành, thay vì chỉ nhìn riêng từng mã.

## File thêm/sửa

- `sector_money_flow.py`
- `realtime/sector_money_flow.py`
- `v19.danh_muc_mua/sector_money_flow.py`
- `configs/stock_sector_map.csv`
- `realtime/intraday_alert_bot.py`
- `v19.danh_muc_mua/v192_realtime_position_telegram_desk_vi.py`
- `docs/VN_SECTOR_MONEY_FLOW_PATCH.md`

## Biến môi trường

Bật lớp mới:

```txt
VN_SECTOR_FLOW_ON=1
```

Tắt nhanh nếu cần rollback mềm:

```txt
VN_SECTOR_FLOW_ON=0
```

## Logic chính

Module `sector_money_flow.py` đọc bảng phân ngành `configs/stock_sector_map.csv` và dữ liệu cache lịch sử trong `cache_stock/` để tính:

- Ngành của mã
- Điểm dòng tiền ngành từ 0 đến 100
- Trạng thái ngành: `MẠNH`, `KHÁ`, `TRUNG TÍNH`, `YẾU`, `UNKNOWN`
- Hiệu suất trung bình 5 phiên và 20 phiên của ngành
- Tỷ lệ mã trong ngành nằm trên MA20
- Volume ratio trung bình 20 phiên
- Leader và laggard trong ngành
- Rank của mã trong ngành

## Tác động lên V18.2 realtime

V18.2 sẽ thêm block `Sector Money Flow` vào Telegram entry alert.

Nếu ngành yếu:

- `BUY CÓ KIỂM SOÁT` hoặc `BUY NHỎ` bị hạ xuống `TEST NHỎ`
- `TEST NHỎ` bị hạ xuống `WATCH`

Patch này **không tự động nâng khuyến nghị mua**, chỉ dùng sector để hạ rủi ro khi ngành yếu.

## Tác động lên V19.2 position desk

V19.2 sẽ thêm các cột vào snapshot/alerts:

- `Sector`
- `Sector Flow`
- `Sector Score`
- `Sector Rank`
- `Sector Leaders`
- `Sector Note`

Telegram V19.2 sẽ có thêm block `Sector Money Flow`.

Nếu V19.2 đang xét mua thêm nhưng ngành yếu hoặc không đủ dữ liệu, patch sẽ chặn mua thêm để tránh bình quân/mua thêm ngược dòng tiền ngành.

## Bảng phân ngành

File `configs/stock_sector_map.csv` là bản mẫu ban đầu. Có thể bổ sung thêm mã bất kỳ theo format:

```csv
Mã,Ngành
VCB,Ngân hàng
SSI,Chứng khoán
HPG,Thép
```

## Test đã chạy khi tạo patch

- `python -m py_compile` cho các file Python chính: pass
- Chạy thử `v19.danh_muc_mua/v192_realtime_position_telegram_desk_vi.py` với `V192_RUN_ONCE=1`: pass
- Snapshot V19.2 sinh thêm các cột Sector Money Flow thành công

## Quy trình deploy đề xuất

1. Tạo branch test: `test-vn-sector-flow`
2. Upload patch vào branch test
3. Chạy GitHub Actions workflow `Run V19.2 Position Telegram Desk` trên branch test
4. Đổi Render sang branch `test-vn-sector-flow`
5. Thêm `VN_SECTOR_FLOW_ON=1`
6. Deploy test và xem log
7. Nếu pass, merge vào `main`
8. Đổi Render về `main` và deploy lại
9. Backup mốc mới nếu ổn
