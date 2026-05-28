# -*- coding: utf-8 -*-
"""
Phân tích hiệu suất T+2, T+5 theo 3 pha thị trường: UPTREND, SIDEWAY, DOWNTREND.
CHỈ PHÂN TÍCH CÁC MÃ CÓ TRONG WATCHLIST (intraday_watchlist_v17.csv)
"""

import os
import pandas as pd
import numpy as np
from glob import glob

CACHE_DIR = "cache_stock"
VNINDEX_FILE = os.path.join(CACHE_DIR, "VNINDEX.csv")
WATCHLIST_FILE = "intraday_watchlist_v17.csv"
OUTPUT_FILE = "regime_performance_stats.csv"


# ==================== TÍNH TOÁN REGIME CHO TỪNG NGÀY ====================
def calculate_adx(high, low, close, period=14):
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
    df = vnindex_df[vnindex_df['date'] <= date].copy()
    if len(df) < 30:
        return "SIDEWAY"
    df['adx'] = calculate_adx(df['high'], df['low'], df['close'], 14)
    current_adx = df['adx'].iloc[-1]
    if len(df) >= 20:
        ret20 = (df['close'].iloc[-1] / df['close'].iloc[-20] - 1) * 100
    else:
        ret20 = 0
    df['ma20'] = df['close'].rolling(20).mean()
    above_ma20 = df['close'].iloc[-1] > df['ma20'].iloc[-1]
    if current_adx > 25 and ret20 > 3 and above_ma20:
        return "UPTREND"
    elif current_adx > 25 and ret20 < -3 and not above_ma20:
        return "DOWNTREND"
    else:
        return "SIDEWAY"

def load_stock_history(symbol):
    path = os.path.join(CACHE_DIR, f"{symbol}.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    date_col = None
    for col in ['time', 'date', 'Date', 'TradingDate']:
        if col in df.columns:
            date_col = col
            break
    if date_col is None:
        return None
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col).reset_index(drop=True)
    close_col = None
    for col in ['close', 'Close', 'adj_close']:
        if col in df.columns:
            close_col = col
            break
    if close_col is None:
        return None
    df = df[[date_col, close_col]].copy()
    df.columns = ['date', 'close']
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df = df.dropna()
    return df

def calc_future_returns(df, horizon=5):
    df['future_ret'] = df['close'].shift(-horizon) / df['close'] - 1
    return df

def load_watchlist_symbols():
    if not os.path.exists(WATCHLIST_FILE):
        print(f"Không tìm thấy {WATCHLIST_FILE}, sẽ phân tích tất cả mã trong cache.")
        return None
    df = pd.read_csv(WATCHLIST_FILE)
    ma_col = None
    for col in ['Mã', 'Ma', 'Symbol', 'Ticker']:
        if col in df.columns:
            ma_col = col
            break
    if ma_col is None:
        print("Watchlist không có cột mã, bỏ qua lọc.")
        return None
    symbols = set(df[ma_col].astype(str).str.upper().str.strip())
    print(f"Số mã trong watchlist: {len(symbols)}")
    return symbols

def main():
    print("===== PHÂN TÍCH HIỆU SUẤT THEO REGIME (CHỈ WATCHLIST) =====")

    # 1. Lấy danh sách mã từ watchlist
    watch_symbols = load_watchlist_symbols()
    
    # 2. Đọc VNINDEX
    if not os.path.exists(VNINDEX_FILE):
        print("Không tìm thấy VNINDEX.csv, bỏ qua.")
        return
    vnindex = pd.read_csv(VNINDEX_FILE)
    # xác định cột ngày, giá, high, low
    date_col = None
    for col in ['time', 'date', 'Date', 'TradingDate']:
        if col in vnindex.columns:
            date_col = col
            break
    if date_col is None:
        print("Không tìm thấy cột ngày trong VNINDEX.csv")
        return
    vnindex['date'] = pd.to_datetime(vnindex[date_col])
    close_col = None
    for col in ['close', 'Close', 'adj_close']:
        if col in vnindex.columns:
            close_col = col
            break
    if close_col is None:
        print("Không tìm thấy cột giá trong VNINDEX.csv")
        return
    vnindex['close'] = pd.to_numeric(vnindex[close_col], errors='coerce')
    high_col = 'high' if 'high' in vnindex.columns else 'High' if 'High' in vnindex.columns else None
    low_col = 'low' if 'low' in vnindex.columns else 'Low' if 'Low' in vnindex.columns else None
    if high_col is None or low_col is None:
        print("Thiếu cột high/low trong VNINDEX.csv")
        return
    vnindex['high'] = pd.to_numeric(vnindex[high_col], errors='coerce')
    vnindex['low'] = pd.to_numeric(vnindex[low_col], errors='coerce')
    vnindex = vnindex.dropna().sort_values('date').reset_index(drop=True)
    
    print("Đang tính regime cho VNINDEX...")
    vnindex['regime'] = vnindex['date'].apply(lambda d: classify_regime(vnindex, d))
    print(f"Đã tính regime cho {len(vnindex)} ngày.")

    # 3. Lấy danh sách tất cả mã có cache, nếu có watchlist thì lọc
    all_stocks = [os.path.basename(f).replace('.csv','') for f in glob(f"{CACHE_DIR}/*.csv")]
    all_stocks = [s for s in all_stocks if s not in ['VNINDEX','VN30','^VNINDEX']]
    if watch_symbols is not None:
        symbols = [s for s in all_stocks if s in watch_symbols]
        print(f"Lọc theo watchlist: {len(symbols)} mã thỏa mãn.")
    else:
        symbols = all_stocks
        print(f"Phân tích tất cả {len(symbols)} mã.")

    # 4. Phân tích từng mã
    all_stats = []
    for sym in symbols:
        df = load_stock_history(sym)
        if df is None or len(df) < 50:
            continue
        df = calc_future_returns(df, horizon=2)
        df = df.rename(columns={'future_ret': 'ret_t2'})
        df = calc_future_returns(df, horizon=5)
        df = df.rename(columns={'future_ret': 'ret_t5'})
        df['date_only'] = df['date'].dt.date
        vnindex['date_only'] = vnindex['date'].dt.date
        merged = df.merge(vnindex[['date_only', 'regime']], on='date_only', how='left')
        for regime in ['UPTREND', 'SIDEWAY', 'DOWNTREND']:
            sub = merged[merged['regime'] == regime]
            if sub.empty:
                continue
            n_t2 = sub['ret_t2'].notna().sum()
            if n_t2 < 5:
                continue
            win_t2 = (sub['ret_t2'] > 0).mean() * 100
            win_t5 = (sub['ret_t5'] > 0).mean() * 100
            avg_t2 = sub['ret_t2'].mean() * 100
            avg_t5 = sub['ret_t5'].mean() * 100
            all_stats.append({
                'Mã': sym,
                'Regime': regime,
                'Số mẫu T+2': n_t2,
                'Winrate T+2 %': round(win_t2, 2),
                'Lợi nhuận TB T+2 %': round(avg_t2, 2),
                'Winrate T+5 %': round(win_t5, 2),
                'Lợi nhuận TB T+5 %': round(avg_t5, 2),
            })
    
    stats_df = pd.DataFrame(all_stats)
    stats_df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')
    print(f"✅ Đã lưu {len(stats_df)} dòng thống kê vào {OUTPUT_FILE}")
    if stats_df.empty:
        print("⚠️ Không có dữ liệu thống kê nào.")
    else:
        print(f"Số mã có thống kê: {len(stats_df['Mã'].unique())}")

if __name__ == "__main__":
    main()
