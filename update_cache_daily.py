# -*- coding: utf-8 -*-
"""
UPDATE CACHE DAILY

Nhiem vu:
- Goi API vnstock de cap nhat cache_stock/*.csv moi ngay.
- Chi file nay duoc phep dung API.
- Workflow run bot se chi doc cache, khong goi API.

Cach chay:
python update_cache_daily.py
"""

import os
import time
import pandas as pd
from datetime import datetime, timedelta

from v10_config import *
from v10_utils import *


def load_quote_history_api(symbol, start, end):
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    try:
        from vnstock.api.quote import Quote

        last_error = None
        for source in ["KBS", "VCI"]:
            try:
                q = Quote(symbol=symbol, source=source)
                df = q.history(start=start_str, end=end_str, interval="1D")
                if df is not None and not df.empty:
                    print(f"API OK {symbol} source={source}")
                    return df
            except Exception as e:
                last_error = e
                continue

        if last_error:
            raise last_error

    except Exception as e:
        print(f"Quote API error {symbol}: {repr(e)}")

    return pd.DataFrame()


def normalize_price_df(df):
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]

    if "close" not in df.columns:
        return pd.DataFrame()

    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    date_col = None
    for c in ["time", "date"]:
        if c in df.columns:
            date_col = c
            break

    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col])
        df = df.drop_duplicates(subset=[date_col], keep="last")
        df = df.sort_values(date_col)

    df = df.dropna(subset=["close"]).reset_index(drop=True)
    return df


def get_last_cache_date(cache_path):
    if not os.path.exists(cache_path):
        return ""

    try:
        df = pd.read_csv(cache_path, encoding="utf-8-sig")
        df.columns = [str(c).lower() for c in df.columns]

        for c in ["time", "date"]:
            if c in df.columns and not df.empty:
                return str(df[c].iloc[-1])[:10]
    except Exception:
        return ""

    return ""


def update_one_symbol(symbol, lookback_days=900):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{symbol}.csv")

    now_vn = datetime.utcnow() + timedelta(hours=7)
    today = now_vn.strftime("%Y-%m-%d")
    last_date = get_last_cache_date(cache_path)

    if last_date == today:
        print(f"SKIP {symbol}: cache already today")
        return "SKIP"

    end = now_vn
    start = end - timedelta(days=lookback_days)

    df = load_quote_history_api(symbol, start, end)
    df = normalize_price_df(df)

    if df.empty:
        print(f"EMPTY {symbol}")
        return "EMPTY"

    df.to_csv(cache_path, index=False, encoding="utf-8-sig")
    print(f"UPDATED {symbol}: rows={len(df)} -> {cache_path}")
    return "UPDATED"


def main():
    print("UPDATE CACHE DAILY START")
    print("Time VN:", datetime.utcnow() + timedelta(hours=7))

    symbols = ["VNINDEX", "VN30"] + list(UNIVERSE)

    updated = 0
    skipped = 0
    empty = 0
    failed = 0

    for i, symbol in enumerate(symbols, 1):
        print(f"{i}/{len(symbols)} Update {symbol}")
        try:
            status = update_one_symbol(symbol)
            if status == "UPDATED":
                updated += 1
            elif status == "SKIP":
                skipped += 1
            elif status == "EMPTY":
                empty += 1
        except Exception as e:
            failed += 1
            print(f"FAIL {symbol}: {repr(e)}")

        time.sleep(API_SLEEP_SEC if "API_SLEEP_SEC" in globals() else 1.5)

    print("UPDATE CACHE DAILY DONE")
    print(f"updated={updated} skipped={skipped} empty={empty} failed={failed}")


if __name__ == "__main__":
    main()
