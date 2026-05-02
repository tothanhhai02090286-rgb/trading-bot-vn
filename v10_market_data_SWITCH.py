# -*- coding: utf-8 -*-
"""
V10 MARKET DATA - AUTO SWITCH API / CACHE

Che do:
- CACHE_ONLY: chi doc cache, khong goi API.
- AUTO: doc cache truoc; neu cache cu/missing thi goi API.
- API_ONLY: luon goi API.

Khuyen nghi:
- Workflow update-cache: dung API_ONLY hoac file update_cache_daily.py rieng.
- Workflow run-daily: dung CACHE_ONLY.
"""

from v10_config import *
from v10_utils import *
from v10_indicators import add_indicators


DATA_MODE = os.getenv("DATA_MODE", "CACHE_ONLY").upper()
CACHE_STALE_DAYS = int(os.getenv("CACHE_STALE_DAYS", "1"))


def load_quote_history(symbol, start, end):
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
                    print(f"Quote API source={source}: {symbol}")
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

    for dcol in ["time", "date"]:
        if dcol in df.columns:
            df[dcol] = pd.to_datetime(df[dcol], errors="coerce")
            df = df.dropna(subset=[dcol])
            df = df.drop_duplicates(subset=[dcol], keep="last")
            df = df.sort_values(dcol).reset_index(drop=True)
            break

    df = df.dropna(subset=["close"]).reset_index(drop=True)
    return df


def read_cache(symbol):
    cache_path = os.path.join(CACHE_DIR, f"{symbol}.csv")
    if not os.path.exists(cache_path):
        return pd.DataFrame(), ""

    try:
        df = fix_vietnamese_columns(pd.read_csv(cache_path, encoding="utf-8-sig"))
        df = normalize_price_df(df)

        last_date = ""
        if not df.empty:
            if "time" in df.columns:
                last_date = str(df["time"].iloc[-1])[:10]
            elif "date" in df.columns:
                last_date = str(df["date"].iloc[-1])[:10]

        return df, last_date
    except Exception as e:
        print(f"Cache read error {symbol}: {repr(e)}")
        return pd.DataFrame(), ""


def is_cache_fresh(last_date):
    if not last_date:
        return False
    try:
        d = pd.to_datetime(last_date)
        today = pd.Timestamp((datetime.utcnow() + timedelta(hours=7)).date())
        age_days = (today - d).days
        return age_days <= CACHE_STALE_DAYS
    except Exception:
        return False


def fetch_history(symbol):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{symbol}.csv")

    df, last_date = read_cache(symbol)

    if DATA_MODE == "CACHE_ONLY":
        if df.empty:
            print(f"CACHE_ONLY: missing/empty cache {symbol}")
            return pd.DataFrame(), "EMPTY"
        print(f"CACHE_ONLY: {symbol} last_date={last_date} rows={len(df)}")
        return df, "CACHE"

    if DATA_MODE == "AUTO":
        if not df.empty and is_cache_fresh(last_date):
            print(f"AUTO: use fresh cache {symbol} last_date={last_date}")
            return df, "CACHE"

        print(f"AUTO: cache stale/missing -> API update {symbol}")

    if DATA_MODE in ["AUTO", "API_ONLY"]:
        end = now_vietnam()
        start = end - timedelta(days=900)

        api_df = load_quote_history(symbol, start, end)
        api_df = normalize_price_df(api_df)

        if api_df.empty:
            if not df.empty:
                print(f"API empty, fallback cache {symbol} last_date={last_date}")
                return df, "CACHE_FALLBACK"
            return pd.DataFrame(), "EMPTY"

        api_df.to_csv(cache_path, index=False, encoding="utf-8-sig")
        print(f"API updated cache {symbol}: rows={len(api_df)}")
        return api_df, "API"

    if df.empty:
        return pd.DataFrame(), "EMPTY"
    return df, "CACHE"


def get_market_ret20():
    for benchmark in ["VNINDEX", "VN30"]:
        try:
            df, mode = fetch_history(benchmark)
            if df.empty or len(df) < 30:
                continue
            df = add_indicators(df)
            ret20 = safe_float(df["Ret20 %"].iloc[-1], 0)
            print(f"Market benchmark {benchmark} Ret20: {ret20:.2f}% | mode={mode}")
            return ret20
        except Exception as e:
            print(f"Market benchmark error {benchmark}: {repr(e)}")
            continue

    print("Cannot get benchmark. RS20 fallback = Ret20")
    return 0


def classify_market_regime(market_ret20):
    market_ret20 = safe_float(market_ret20, 0)

    if market_ret20 >= 5:
        return "UPTREND"
    if market_ret20 >= 1:
        return "POSITIVE"
    if market_ret20 <= -5:
        return "DOWNTREND"
    if market_ret20 <= -1:
        return "WEAK"

    return "SIDEWAY"
