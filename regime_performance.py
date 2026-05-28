# -*- coding: utf-8 -*-
"""
Phân tích hiệu suất T+2, T+5 theo 3 pha thị trường: UPTREND, SIDEWAY, DOWNTREND.
Sử dụng chỉ báo ADX, MA20 slope, và lợi nhuận 20 phiên của VNINDEX.
"""

import os
import pandas as pd
import numpy as np
from glob import glob

CACHE_DIR = "cache_stock"
VNINDEX_FILE = os.path.join(CACHE_DIR, "VNINDEX.csv")
OUTPUT_FILE = "regime_performance_stats.csv"

# ==================== TÍNH TOÁN REGIME CHO TỪNG NGÀY ====================
def calculate_adx(high, low, close, period=14):
    """Tính ADX (Average Directional Index)"""
    high, low, close = high.values, low.values, close.values
    plus_dm = np.zeros(len(close))
    minus_dm = np.zeros(len(close))
    tr = np.zeros(len(close))
    
    for i in range(1, len(close)):
        up_move = high[i] - high[i-1]
        down_move = low[i-1] - low[i]
        plus_dm[i] = up_move if up_move > down_move and up_move > 0 else 0
        minus_dm[i] = down_move if down_move > up_move and down_move > 0 else 0
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
    
    atr = pd.Series(tr).rolling(period).mean().values
    plus_di = 100 * pd.Series(plus_dm).rolling(period).mean() / (atr + 1e-9)
    minus_di = 100 * pd.Series(minus_dm).rolling(period).mean() / (atr + 1e-9)
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)
    adx = pd.Series(dx).rolling(period).mean()
    return adx

def classify_regime(vnindex_df, date):
    """Xác định regime của một ngày dựa trên dữ liệu VNINDEX"""
    # Lấy dữ liệu đến ngày đó
    df = vnindex_df[vnindex_df['date'] <= date].copy()
    if len(df) < 30:
        return "SIDEWAY"
    
    # Tính ADX
    df['adx'] = calculate_adx(df['high'], df['low'], df['close'], 14)
    current_adx = df['adx'].iloc[-1]
    
    # Tính Ret20 của VNINDEX
    if len(df) >= 20:
        ret20 = (df['close'].iloc[-1] / df['close'].iloc[-20] - 1) * 100
    else:
        ret20 = 0
    
    # Tính MA20 và vị trí giá
    df['ma20'] = df['close'].rolling(20).mean()
    above_ma20 = df['close'].iloc[-1] > df['ma20'].iloc[-1]
    
    # Phân loại
    if current_adx > 25 and ret20 > 3 and above_ma20:
        return "UPTREND"
    elif current_adx > 25 and ret20 < -3 and not above_ma20:
        return "DOWNTREND"
    else:
        return "SIDEWAY"

# ==================== TÍNH HIỆU SUẤT THEO REGIME ====================
def load_stock_history(symbol):
    path = os.path.join(CACHE_DIR, f"{symbol}.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    date_col = 'time' if 'time' in df.columns else 'date'
    if date_col not in df.columns:
        return None
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col).reset_index(drop=True)
    close_col = 'close' if 'close' in df.columns else 'Close'
    if close_col not in df.columns:
        return None
    df = df[[date_col, close_col]].copy()
    df.columns = ['date', 'close']
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df = df.dropna()
    return df

def calc_future_returns(df, horizon=5):
    """Tính lợi nhuận T+horizon cho mỗi ngày"""
    df['future_ret'] = df['close'].shift(-horizon) / df['close'] - 1
    return df

def main():
    # Đọc dữ liệu VNINDEX
    if not os.path.exists(VNINDEX_FILE):
        print("Không tìm thấy VNINDEX.csv, bỏ qua.")
        return
    
    vnindex = pd.read_csv(VNINDEX_FILE)
    date_col = 'time' if 'time' in vnindex.columns else 'date'
    vnindex['date'] = pd.to_datetime(vnindex[date_col])
    vnindex['close'] = pd.to_numeric(vnindex['close'] if 'close' in vnindex.columns else vnindex['Close'], errors='coerce')
    vnindex['high'] = pd.to_numeric(vnindex['high'] if 'high' in vnindex.columns else vnindex['High'], errors='coerce')
    vnindex['low'] = pd.to_numeric(vnindex['low'] if 'low' in vnindex.columns else vnindex['Low'], errors='coerce')
    vnindex = vnindex.dropna().sort_values('date').reset_index(drop=True)
    
    # Xác định regime cho từng ngày (để dùng cho các mã)
    vnindex['regime'] = vnindex['date'].apply(lambda d: classify_regime(vnindex, d))
    
    # Thống kê tổng hợp cho tất cả mã
    stock_files = glob(f"{CACHE_DIR}/*.csv")
    symbols = [os.path.basename(f).replace('.csv','') for f in stock_files if 'VNINDEX' not in f.upper()]
    
    all_stats = []
    
    for sym in symbols[:20]:  # giới hạn để test nhanh, bỏ limit khi chạy thật
        df = load_stock_history(sym)
        if df is None or len(df) < 50:
            continue
        
        # Tính lợi nhuận T+2 và T+5
        df = calc_future_returns(df, horizon=2)
        df = df.rename(columns={'future_ret': 'ret_t2'})
        df = calc_future_returns(df, horizon=5)
        df = df.rename(columns={'future_ret': 'ret_t5'})
        
        # Ghép regime (lấy regime theo ngày)
        df['date_only'] = df['date'].dt.date
        vnindex['date_only'] = vnindex['date'].dt.date
        merged = df.merge(vnindex[['date_only', 'regime']], on='date_only', how='left')
        
        # Thống kê theo regime
        for regime in ['UPTREND', 'SIDEWAY', 'DOWNTREND']:
            sub = merged[merged['regime'] == regime]
            if sub.empty:
                continue
            win_t2 = (sub['ret_t2'] > 0).mean() * 100
            win_t5 = (sub['ret_t5'] > 0).mean() * 100
            avg_t2 = sub['ret_t2'].mean() * 100
            avg_t5 = sub['ret_t5'].mean() * 100
            all_stats.append({
                'Mã': sym,
                'Regime': regime,
                'Số mẫu T+2': sub['ret_t2'].notna().sum(),
                'Winrate T+2 %': round(win_t2, 2),
                'Lợi nhuận TB T+2 %': round(avg_t2, 2),
                'Winrate T+5 %': round(win_t5, 2),
                'Lợi nhuận TB T+5 %': round(avg_t5, 2),
            })
    
    # Lưu kết quả
    stats_df = pd.DataFrame(all_stats)
    stats_df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
    print(f"✅ Đã lưu thống kê theo regime vào {OUTPUT_FILE}")
    
    # In tóm tắt
    print("\n=== TÓM TẮT THEO REGIME (trung bình toàn bộ mã) ===")
    for regime in ['UPTREND', 'SIDEWAY', 'DOWNTREND']:
        sub = stats_df[stats_df['Regime'] == regime]
        if not sub.empty:
            avg_win_t5 = sub['Winrate T+5 %'].mean()
            print(f"{regime}: Winrate T+5 trung bình = {avg_win_t5:.1f}%")

if __name__ == "__main__":
    main()
