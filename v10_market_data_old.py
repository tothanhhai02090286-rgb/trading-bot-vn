# -*- coding: utf-8 -*-
from v10_config import *
from v10_utils import *
from v10_indicators import add_indicators


def load_quote_history(symbol, start, end):
    """
    Load daily quote history.
    Prefer the new vnstock Quote API, then fallback to old Vnstock API.
    """
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    try:
        from vnstock.api.quote import Quote

        last_error = None
        for source in ["KBS", "VCI"]:
            try:
                q = Quote(symbol=symbol, source=source)
                df = q.history(
                    start=start_str,
                    end=end_str,
                    interval="1D"
                )
                if df is not None and not df.empty:
                    print(f"Quote API source={source}: {symbol}")
                    return df
            except Exception as e:
                last_error = e
                continue

        if last_error:
            raise last_error

    except Exception as e:
        print(f"Quote API error {symbol}: {repr(e)} -> fallback old Vnstock API")

    from vnstock import Vnstock

    vn = Vnstock()
    if API_KEY:
        try:
            vn.set_token(API_KEY)
        except Exception as e:
            print(f"Cannot set Vnstock token: {repr(e)}")

    stock = vn.stock(symbol=symbol, source="KBS")
    return stock.quote.history(
        start=start_str,
        end=end_str,
        interval="1D"
    )


def fetch_history(symbol):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{symbol}.csv")

    now_vn = datetime.utcnow() + timedelta(hours=7)
    today = now_vn.strftime("%Y-%m-%d")
    close_hour = 16

    if os.path.exists(cache_path):
        try:
            df = fix_vietnamese_columns(pd.read_csv(cache_path, encoding="utf-8-sig"))

            if df is not None and not df.empty and "close" in df.columns:
                last_date = None

                if "time" in df.columns:
                    last_date = str(df["time"].iloc[-1])[:10]
                elif "date" in df.columns:
                    last_date = str(df["date"].iloc[-1])[:10]

                cache_mtime_vn = datetime.utcfromtimestamp(os.path.getmtime(cache_path)) + timedelta(hours=7)
                cache_hour = cache_mtime_vn.hour

                if now_vn.hour < close_hour:
                    print(f"Before 16h VN -> use cache: {symbol}")
                    return df, "CACHE"

                if last_date == today and cache_hour >= close_hour:
                    print(f"Cache OK after session: {symbol}")
                    return df, "CACHE"

                if last_date == today and cache_hour < close_hour:
                    print(f"Cache today but before close -> update: {symbol}")
                elif last_date != today:
                    print(f"Old cache {symbol}: {last_date} -> update {today}")
                else:
                    print(f"Cache needs update: {symbol}")

        except Exception as e:
            print(f"Cache error {symbol}: {e}")

    print(f"API fetch/update: {symbol}")

    end = now_vietnam()
    start = end - timedelta(days=800)

    df = load_quote_history(symbol, start, end)

    if df is None or df.empty:
        return pd.DataFrame(), "EMPTY"

    df.columns = [str(c).lower() for c in df.columns]

    if "close" not in df.columns:
        return pd.DataFrame(), "EMPTY"

    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["close"]).reset_index(drop=True)

    df.to_csv(cache_path, index=False, encoding="utf-8-sig")
    print(f"Updated cache: {cache_path}")

    return df, "API"


def get_market_ret20():
    for benchmark in ["VNINDEX", "VN30"]:
        try:
            df, _ = fetch_history(benchmark)
            if df.empty or len(df) < 30:
                continue
            df = add_indicators(df)
            ret20 = safe_float(df["Ret20 %"].iloc[-1], 0)
            print(f"Market benchmark {benchmark} Ret20: {ret20:.2f}%")
            return ret20
        except Exception as e:
            print(f"Market benchmark error {benchmark}: {repr(e)}")
            continue

    print("Cannot get benchmark, RS20 fallback = Ret20")
    return 0


def classify_market_regime(market_ret20):
    """
    Market regime helper.
    Kept here as a safe fallback so other files can import it without circular import issues.
    """
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
