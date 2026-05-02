from v10_config import *
from v10_utils import *
from v10_indicators import add_indicators

def load_quote_history(symbol, start, end):
    """
    V2: Æ°u tiÃªn API má»i Quote Äá» trÃ¡nh VNSTOCK DEPRECATION NOTICE.
    Fallback vá» Vnstock cÅ© náº¿u mÃ´i trÆ°á»ng chÆ°a há» trá»£ Quote.
    """
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    # API má»i
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
                    print(f"â Quote API source={source}: {symbol}")
                    return df
            except Exception as e:
                last_error = e
                continue

        if last_error:
            raise last_error

    except Exception as e:
        print(f"â ï¸ Quote API lá»i {symbol}: {repr(e)} â fallback Vnstock cÅ©")

    # Fallback API cÅ©
    from vnstock import Vnstock

    vn = Vnstock()
    if API_KEY:
        try:
            vn.set_token(API_KEY)
        except Exception as e:
            print(f"â ï¸ KhÃ´ng set ÄÆ°á»£c token báº±ng Vnstock cÅ©: {repr(e)}")

    stock = vn.stock(symbol=symbol, source="KBS")
    return stock.quote.history(
        start=start_str,
        end=end_str,
        interval="1D"
    )

def fetch_history(symbol):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"{symbol}.csv")

    # Giá» Viá»t Nam
    now_vn = datetime.utcnow() + timedelta(hours=7)
    today = now_vn.strftime("%Y-%m-%d")
    close_hour = 16  # sau 16h má»i tin dá»¯ liá»u ngÃ y hÃ´m nay

    if os.path.exists(cache_path):
        try:
            df = fix_vietnamese_columns(pd.read_csv(cache_path, encoding="utf-8-sig"))

            if df is not None and not df.empty and "close" in df.columns:
                last_date = None

                if "time" in df.columns:
                    last_date = str(df["time"].iloc[-1])[:10]
                elif "date" in df.columns:
                    last_date = str(df["date"].iloc[-1])[:10]

                # Láº¥y giá» file cache ÄÆ°á»£c lÆ°u
                cache_mtime_vn = datetime.utcfromtimestamp(os.path.getmtime(cache_path)) + timedelta(hours=7)
                cache_hour = cache_mtime_vn.hour

                # 1. Náº¿u Äang trÆ°á»c 16h â dÃ¹ng cache, khÃ´ng gá»i API
                if now_vn.hour < close_hour:
                    print(f"â³ TrÆ°á»c 16h VN â dÃ¹ng cache: {symbol}")
                    return df, "CACHE"

                # 2. Náº¿u cache lÃ  ngÃ y hÃ´m nay vÃ  ÄÆ°á»£c lÆ°u sau 16h â dÃ¹ng cache
                if last_date == today and cache_hour >= close_hour:
                    print(f"â¡ Cache OK sau phiÃªn: {symbol}")
                    return df, "CACHE"

                # 3. Náº¿u cache ngÃ y hÃ´m nay nhÆ°ng lÆ°u trÆ°á»c 16h â fetch láº¡i
                if last_date == today and cache_hour < close_hour:
                    print(f"ð Cache ngÃ y {today} nhÆ°ng lÆ°u trÆ°á»c 16h â update láº¡i: {symbol}")

                # 4. Náº¿u cache ngÃ y cÅ© â fetch láº¡i
                elif last_date != today:
                    print(f"ð Cache cÅ© {symbol}: {last_date} â update ngÃ y {today}")

                else:
                    print(f"ð Cache cáº§n update: {symbol}")

        except Exception as e:
            print(f"â ï¸ Cache lá»i {symbol}: {e}")

    print(f"ð API fetch/update: {symbol}")

    end = now_vietnam()
    start = end - timedelta(days=260)

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
    print(f"ð¾ Updated cache: {cache_path}")

    return df, "API"

def get_market_ret20():
    for benchmark in ["VNINDEX", "VN30"]:
        try:
            df, _ = fetch_history(benchmark)
            if df.empty or len(df) < 30:
                continue
            df = add_indicators(df)
            ret20 = safe_float(df["Ret20 %"].iloc[-1], 0)
            print(f"ð Market benchmark {benchmark} Ret20: {ret20:.2f}%")
            return ret20
        except Exception:
            continue

    print("â ï¸ KhÃ´ng láº¥y ÄÆ°á»£c benchmark, RS20 táº¡m tÃ­nh = Ret20")
    return 0
