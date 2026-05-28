# -*- coding: utf-8 -*-
"""
Phân tích chuỗi tăng (streaks) và thời gian đạt lợi nhuận (time-to-profit)
từ dữ liệu cache_stock (các file CSV của từng mã).
Kết quả xuất ra 3 file: streaks_report.csv, time_to_profit_report.csv, returns_summary.txt
"""

import os
import pandas as pd
import numpy as np
from glob import glob

# ==================== CẤU HÌNH ====================
CACHE_DIR = "cache_stock"            # Thư mục chứa dữ liệu lịch sử giá
OUT_STREAKS = "streaks_report.csv"   # Báo cáo chuỗi tăng dài nhất
OUT_TIMING = "time_to_profit_report.csv"  # Báo cáo thời gian đạt mục tiêu
OUT_SUMMARY = "returns_summary.txt"       # Tóm tắt ngắn


# ==================== HÀM ĐỌC DỮ LIỆU ====================
def load_history(symbol):
    """
    Đọc file CSV của một mã, chuẩn hóa cột ngày và giá đóng cửa.
    Trả về DataFrame với 2 cột: 'date' (datetime) và 'close' (float).
    Trả về None nếu không đọc được.
    """
    path = os.path.join(CACHE_DIR, f"{symbol}.csv")
    if not os.path.exists(path):
        return None

    df = pd.read_csv(path)

    # Tìm cột ngày (ưu tiên 'time', sau đó 'date')
    date_col = 'time' if 'time' in df.columns else 'date' if 'date' in df.columns else None
    if date_col is None:
        return None

    # Chuyển cột ngày về datetime và sắp xếp
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col).reset_index(drop=True)

    # Tìm cột giá đóng cửa (ưu tiên 'close', sau đó 'Close')
    close_col = 'close' if 'close' in df.columns else 'Close' if 'Close' in df.columns else None
    if close_col is None:
        return None

    # Chỉ giữ lại 2 cột cần thiết
    df = df[[date_col, close_col]].copy()
    df.columns = ['date', 'close']
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df = df.dropna()
    return df


# ==================== CHUỖI TĂNG DÀI NHẤT ====================
def longest_up_streak(series):
    """
    Tính chuỗi tăng liên tiếp dài nhất của một chuỗi giá (close).
    Trả về: (số_phiên_tăng_dài_nhất, danh_sách_%_tăng_từng_phiên)
    """
    returns = series.pct_change() * 100   # % thay đổi mỗi phiên
    is_up = returns > 0                   # True nếu phiên đó tăng

    streak = 0
    max_streak = 0
    best_returns = []
    cur_returns = []

    for r, up in zip(returns, is_up):
        if up:
            streak += 1
            cur_returns.append(round(r, 2))
        else:
            if streak > max_streak:
                max_streak = streak
                best_returns = cur_returns.copy()
            streak = 0
            cur_returns = []

    # Kiểm tra nếu chuỗi kéo dài đến cuối
    if streak > max_streak:
        max_streak = streak
        best_returns = cur_returns

    return max_streak, best_returns


# ==================== THỜI GIAN ĐẠT LỢI NHUẬN MỤC TIÊU ====================
def time_to_target(df, target_pct=3, max_days=20):
    """
    Với mỗi ngày trong lịch sử, giả sử mua ở giá đóng cửa.
    Tìm số phiên sớm nhất (tối đa max_days) để lợi nhuận đạt >= target_pct %.
    Trả về danh sách các số phiên cần (chỉ tính những lần đạt được mục tiêu).
    """
    results = []
    close = df['close'].values
    n = len(close)

    for i in range(n - max_days):
        buy_price = close[i]
        for j in range(i + 1, min(i + max_days + 1, n)):
            ret = (close[j] / buy_price - 1) * 100
            if ret >= target_pct:
                results.append(j - i)   # số phiên đã trôi qua
                break
    return results


# ==================== HÀM CHÍNH ====================
def main():
    # Lấy danh sách tất cả các file CSV trong thư mục cache_stock
    all_files = glob(f"{CACHE_DIR}/*.csv")
    symbols = [os.path.basename(f).replace('.csv', '') for f in all_files]

    # Loại bỏ các chỉ số thị trường (không phải cổ phiếu)
    symbols = [s for s in symbols if s not in ['VNINDEX', 'VN30', '^VNINDEX']]

    streaks_rows = []   # lưu kết quả phân tích chuỗi tăng
    timing_rows = []    # lưu kết quả thời gian đạt mục tiêu

    for sym in symbols:
        df = load_history(sym)
        if df is None or len(df) < 50:
            continue    # bỏ qua mã có ít dữ liệu

        # ---- 1. Chuỗi tăng dài nhất ----
        max_streak, rets = longest_up_streak(df['close'])
        streaks_rows.append({
            'Ma': sym,
            'So phien tang dai nhat': max_streak,
            'Muc tang tung phien trong chuoi (%)': str(rets),
            'Tong % tang cua chuoi': round(sum(rets), 2) if rets else 0,
            'Trung binh % tang moi phien': round(np.mean(rets), 2) if rets else 0
        })

        # ---- 2. Thời gian đạt mục tiêu 3% và 5% ----
        for target in [3, 5]:
            days = time_to_target(df, target_pct=target, max_days=20)
            if days:
                timing_rows.append({
                    'Ma': sym,
                    'Muc tieu %': target,
                    'So mau': len(days),
                    'Trung binh ngay': round(np.mean(days), 2),
                    'Trung vi (ngay)': int(np.median(days)),
                    'Percentile 75': int(np.percentile(days, 75)),
                    'Ti le dat muc tieu trong 20 phien': round(len(days) / (len(df) - 20) * 100, 1)
                })

    # Lưu báo cáo CSV
    pd.DataFrame(streaks_rows).to_csv(OUT_STREAKS, index=False, encoding='utf-8-sig')
    pd.DataFrame(timing_rows).to_csv(OUT_TIMING, index=False, encoding='utf-8-sig')

    # Tạo file tóm tắt
    with open(OUT_SUMMARY, 'w', encoding='utf-8') as f:
        f.write("===== TONG HOP CHUOI TANG & THOI GIAN DAT LOI NHUAN =====\n\n")
        f.write(f"Tong so ma phan tich: {len(streaks_rows)}\n")
        if streaks_rows:
            best = max(streaks_rows, key=lambda x: x['So phien tang dai nhat'])
            f.write(f"Ma co chuoi tang dai nhat: {best['Ma']} ({best['So phien tang dai nhat']} phien)\n")
        f.write("\n--- Time to profit 3% (top 10 trung vi thap nhat) ---\n")
        df_time = pd.DataFrame(timing_rows)
        if not df_time.empty:
            top = df_time[df_time['Muc tieu %'] == 3].nsmallest(10, 'Trung vi (ngay)')
            for _, r in top.iterrows():
                f.write(f"{r['Ma']}: {r['Trung vi (ngay)']} ngay (ti le dat {r['Ti le dat muc tieu trong 20 phien']}%)\n")

    print("✅ Phan tich hoan tat. Cac file da duoc ghi:", OUT_STREAKS, OUT_TIMING, OUT_SUMMARY)


if __name__ == "__main__":
    main()
