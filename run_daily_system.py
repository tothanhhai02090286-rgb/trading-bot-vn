import os
import time
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from pandas.errors import EmptyDataError

from universe import UNIVERSE

API_KEY = os.getenv("VNSTOCK_API_KEY")

SYSTEM_VERSION = "PRO_V9_STABLE_FINAL_VI_2026_05_01"

BATCH_SIZE = 50
CACHE_SLEEP_SEC = 0.3
API_SLEEP_SEC = 5
CACHE_DIR = "cache_stock"

STATE_PATH = "progress_state.csv"
ALL_RESULT_PATH = "all_signal_results.csv"

RAW_SIGNAL_PATH = "raw_signal_candidates.csv"
AI_RISK_PATH = "ai_risk_filtered.csv"
BOTTOM_PATH = "bottom_common_priority.csv"
MOMENTUM_PATH = "momentum_common_priority.csv"
ENTRY_PATH = "entry_plan_next_session.csv"
DASHBOARD_PATH = "ai_risk_dashboard.html"

PORTFOLIO_PATH = "portfolio_current.csv"
PORTFOLIO_TRACKER_PATH = "portfolio_tracker.csv"
ACTION_PLAN_PATH = "action_plan.csv"

SIGNAL_HISTORY_PATH = "signal_history.csv"
PATTERN_STATS_PATH = "pattern_stats.csv"

WALK_FORWARD_STATS_PATH = "walk_forward_stats.csv"

BACKFILL_SIGNAL_HISTORY_PATH = "backfill_signal_history.csv"
BACKFILL_WALK_FORWARD_PATH = "backfill_walk_forward_stats.csv"

BACKFILL_ENABLED = True
BACKFILL_MIN_ROWS_PER_SYMBOL = 120
BACKFILL_LOOKBACK_DAYS = 360
BACKFILL_BLOCK_MONTHS = 3
BACKFILL_TRAIN_RATIO = 0.80
BACKFILL_MAX_SYMBOLS_PER_RUN = 40
BACKFILL_STATE_PATH = "backfill_state.csv"

REGIME_STATS_PATH = "regime_stats.csv"

REGIME_SHORT_MA = 20
REGIME_LONG_MA = 50
REGIME_STRONG_RET20 = 5.0
REGIME_WEAK_RET20 = -5.0
REGIME_SIDEWAY_ABS_RET20 = 2.0
REGIME_HIGH_VOL_ATR = 8.0

RECENT_WEIGHT_MIN = 0.20
REGIME_BONUS_STRONG = 6
REGIME_PENALTY_BAD = 10

WF_TRAIN_DAYS = 45
WF_TEST_DAYS = 10
WF_STEP_DAYS = 10
WF_MIN_TEST_SAMPLES = 5
WF_MIN_WINDOWS = 2
WF_MIN_OOS_WIN_PROB = 52.0

HISTORY_LOOKBACK_DAYS = 90
DECAY_HALFLIFE_DAYS = 30
MIN_PATTERN_SAMPLES = 8
BASE_WIN_PROB = 55.0
TP_LEARN_PCT = 4.0
SL_LEARN_PCT = -3.0
HOLD_DAYS_LIST = [3, 5, 10]

TELEGRAM_ENABLED = True
TELEGRAM_MAX_ITEMS = 7


def fix_vietnamese_columns(df):
    """
    Chuáº©n hÃ³a tÃªn cá»t bá» lá»i encoding phá» biáº¿n khi Äá»c CSV trÃªn Colab/GitHub.
    VÃ­ dá»¥: MÃÂ£ -> MÃ£, NgÃ y -> NgÃ y.
    """
    if df is None or df.empty:
        return df

    rename_map = {
        "MÃÂ£": "MÃ£",
        "Ma": "MÃ£",
        "NgÃ y": "NgÃ y",
        "Ngay": "NgÃ y",
        "ChiÃ¡ÂºÂ¿n lÃÂ°Ã¡Â»Â£c": "Chiáº¿n lÆ°á»£c",
        "HÃ nh ÃâÃ¡Â»â¢ng": "HÃ nh Äá»ng",
        "CÃ¡ÂºÂ£nh bÃÂ¡o": "Cáº£nh bÃ¡o",
        "LÃÂ½ do": "LÃ½ do",
        "GiÃÂ¡ vÃ¡Â»ân": "GiÃ¡ vá»n",
        "SÃ¡Â»â lÃÂ°Ã¡Â»Â£ng": "Sá» lÆ°á»£ng",
        "GiÃÂ¡ trÃ¡Â»â¹ vÃ¡Â»ân": "GiÃ¡ trá» vá»n",
        "GiÃÂ¡ trÃ¡Â»â¹ hiÃ¡Â»â¡n tÃ¡ÂºÂ¡i": "GiÃ¡ trá» hiá»n táº¡i",
        "LÃÂ£i/LÃ¡Â»â %": "LÃ£i/Lá» %",
        "LÃÂ£i/LÃ¡Â»â tiÃ¡Â»Ân": "LÃ£i/Lá» tiá»n",
    }

    df = df.copy()
    df.columns = [rename_map.get(str(c), str(c).replace("\ufeff", "").strip()) for c in df.columns]
    return df


def safe_read_csv(path):
    if not os.path.exists(path):
        return pd.DataFrame()

    for enc in ["utf-8-sig", "utf-8", "cp1258", "latin1"]:
        try:
            df = pd.read_csv(path, encoding=enc)
            return fix_vietnamese_columns(df)
        except EmptyDataError:
            return pd.DataFrame()
        except Exception:
            continue

    return pd.DataFrame()


def safe_float(x, default=np.nan):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def load_state():
    df = safe_read_csv(STATE_PATH)
    if df.empty or "next_start" not in df.columns:
        return 0
    try:
        return int(df["next_start"].iloc[-1])
    except Exception:
        return 0


def save_state(next_start):
    pd.DataFrame([{
        "updated_at": now_vietnam().strftime("%Y-%m-%d %H:%M:%S"),
        "next_start": next_start,
        "version": SYSTEM_VERSION
    }]).to_csv(STATE_PATH, index=False, encoding="utf-8-sig")



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


def calc_rsi(close, period=14):
    close = pd.Series(close).astype(float)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


def add_indicators(df):
    df = df.copy()

    close = df["close"]
    high = df["high"] if "high" in df.columns else close
    low = df["low"] if "low" in df.columns else close
    volume = df["volume"] if "volume" in df.columns else pd.Series([np.nan] * len(df))

    df["MA5"] = close.rolling(5).mean()
    df["MA20"] = close.rolling(20).mean()
    df["RSI"] = calc_rsi(close, 14)

    df["Ret5 %"] = close.pct_change(5) * 100
    df["Ret10 %"] = close.pct_change(10) * 100
    df["Ret20 %"] = close.pct_change(20) * 100

    df["VolMA20"] = volume.rolling(20).mean()
    df["Volume Ratio"] = volume / (df["VolMA20"] + 1e-9)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    df["ATR"] = tr.rolling(14).mean()
    df["ATR %"] = df["ATR"] / close * 100

    df["High20"] = high.rolling(20).max()
    df["Low20"] = low.rolling(20).min()

    df["Drawdown20 %"] = (close / df["High20"] - 1) * 100
    df["Rebound Low20 %"] = (close / df["Low20"] - 1) * 100
    df["Dist MA20 %"] = (close / df["MA20"] - 1) * 100

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()

    df["MACD Hist"] = macd - signal
    df["MACD Hist Up"] = df["MACD Hist"] > df["MACD Hist"].shift(1)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    plus_di = 100 * pd.Series(plus_dm).rolling(14).mean() / (df["ATR"] + 1e-9)
    minus_di = 100 * pd.Series(minus_dm).rolling(14).mean() / (df["ATR"] + 1e-9)

    dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
    df["ADX"] = dx.rolling(14).mean()

    return df


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


def score_momentum(row):
    score = 0
    if row["MA5"] > row["MA20"]:
        score += 15
    if 55 <= row["RSI"] <= 75:
        score += 15
    if row["Ret5 %"] > 2:
        score += 10
    if row["Ret10 %"] > 3:
        score += 10
    if row["RS20"] > 0:
        score += 10
    if row["Volume Ratio"] > 1.2:
        score += 10
    if row["ADX"] > 20:
        score += 10
    if row["ATR %"] <= 8:
        score += 10
    if row["MACD Hist Up"]:
        score += 5
    if 0 <= row["Dist MA20 %"] <= 12:
        score += 5
    return score


def score_bottom(row):
    score = 0
    if 30 <= row["RSI"] <= 48:
        score += 15
    if row["Drawdown20 %"] <= -5:
        score += 15
    if row["Rebound Low20 %"] >= 1:
        score += 10
    if row["Volume Ratio"] >= 0.8:
        score += 10
    if row["Close"] >= row["Low20"]:
        score += 10
    if row["ATR %"] <= 9:
        score += 10
    if row["RS20"] > -8:
        score += 10
    if row["Dist MA20 %"] <= 3:
        score += 10
    if row["MACD Hist Up"]:
        score += 10
    return score


def classify_strategy(row):
    if row["Momentum Score"] >= 75 and row["Momentum Score"] >= row["Bottom Score"]:
        return "MOMENTUM"
    if row["Bottom Score"] >= 70 and row["Bottom Score"] > row["Momentum Score"]:
        return "BOTTOM"
    if row["Momentum Score"] >= 60:
        return "MOMENTUM_WATCH"
    if row["Bottom Score"] >= 55:
        return "BOTTOM_WATCH"
    return "WATCH"


def risk_filter(row):
    reasons = []

    if row["RSI"] >= 90:
        reasons.append("RSI quÃ¡ nÃ³ng")
    if row["ATR %"] > 10:
        reasons.append("ATR quÃ¡ cao")
    if row["Volume Ratio"] < 0.7:
        reasons.append("Volume yáº¿u")
    if row["RS20"] < -10:
        reasons.append("RS20 yáº¿u")
    if row["Chiáº¿n lÆ°á»£c"] == "MOMENTUM" and row["Close"] < row["MA20"]:
        reasons.append("Momentum nhÆ°ng giÃ¡ dÆ°á»i MA20")

    if len(reasons) == 0:
        return "PASS", ""
    return "FAIL", "; ".join(reasons)


def classify_action(row):
    if row["Risk Status"] == "FAIL":
        return "SKIP"
    if row["RSI"] >= 90:
        return "SKIP"
    if 85 <= row["RSI"] < 90:
        return "WATCHLIST"
    if 75 <= row["RSI"] < 85:
        return "WAIT"
    if row["Chiáº¿n lÆ°á»£c"] == "MOMENTUM" and row["Momentum Score"] >= 80:
        return "BUY NOW"
    if row["Chiáº¿n lÆ°á»£c"] == "BOTTOM" and row["Bottom Score"] >= 75:
        return "BUY NOW"
    if row["Chiáº¿n lÆ°á»£c"] in ["MOMENTUM", "BOTTOM"]:
        return "WAIT"
    if row["Chiáº¿n lÆ°á»£c"] in ["MOMENTUM_WATCH", "BOTTOM_WATCH"]:
        return "WATCHLIST"
    return "SKIP"


def make_signal(row):
    if row["Chiáº¿n lÆ°á»£c"] == "MOMENTUM":
        return "ð MOMENTUM"
    if row["Chiáº¿n lÆ°á»£c"] == "BOTTOM":
        return "ð§² BOTTOM"
    if row["Chiáº¿n lÆ°á»£c"] == "MOMENTUM_WATCH":
        return "ð MOMENTUM WATCH"
    if row["Chiáº¿n lÆ°á»£c"] == "BOTTOM_WATCH":
        return "ð BOTTOM WATCH"
    return "ð WATCH"


def analyze_symbol(symbol, market_ret20):
    df, fetch_mode = fetch_history(symbol)

    if df.empty or len(df) < 60:
        return None

    df = add_indicators(df)
    last = df.iloc[-1]

    close = safe_float(last.get("close"))
    ma5 = safe_float(last.get("MA5"))
    ma20 = safe_float(last.get("MA20"))
    rsi = safe_float(last.get("RSI"))

    if pd.isna(close) or pd.isna(ma5) or pd.isna(ma20) or pd.isna(rsi):
        return None

    ret5 = safe_float(last.get("Ret5 %"), 0)
    ret10 = safe_float(last.get("Ret10 %"), 0)
    ret20 = safe_float(last.get("Ret20 %"), 0)
    rs20 = ret20 - market_ret20

    row = {
        "NgÃ y": get_price_data_date(df),
        "MÃ£": symbol,
        "Close": round(close, 2),
        "MA5": round(ma5, 2),
        "MA20": round(ma20, 2),
        "RSI": round(rsi, 2),
        "Ret5 %": round(ret5, 2),
        "Ret10 %": round(ret10, 2),
        "Ret20 %": round(ret20, 2),
        "RS20": round(rs20, 2),
        "Volume Ratio": round(safe_float(last.get("Volume Ratio"), 0), 2),
        "ADX": round(safe_float(last.get("ADX"), 0), 2),
        "ATR %": round(safe_float(last.get("ATR %"), 999), 2),
        "MACD Hist": round(safe_float(last.get("MACD Hist"), 0), 4),
        "MACD Hist Up": bool(last.get("MACD Hist Up")),
        "Dist MA20 %": round(safe_float(last.get("Dist MA20 %"), 0), 2),
        "Drawdown20 %": round(safe_float(last.get("Drawdown20 %"), 0), 2),
        "Rebound Low20 %": round(safe_float(last.get("Rebound Low20 %"), 0), 2),
        "Low20": round(safe_float(last.get("Low20"), 0), 2),
        "High20": round(safe_float(last.get("High20"), 0), 2),
        "Fetch Mode": fetch_mode,
        "Updated": now_vietnam().strftime("%Y-%m-%d %H:%M:%S"),
        "Version": SYSTEM_VERSION
    }

    row["Momentum Score"] = score_momentum(row)
    row["Bottom Score"] = score_bottom(row)
    row["Score"] = max(row["Momentum Score"], row["Bottom Score"])
    row["Chiáº¿n lÆ°á»£c"] = classify_strategy(row)

    risk_status, risk_reason = risk_filter(row)
    row["Risk Status"] = risk_status
    row["Risk Reason"] = risk_reason

    row["Action"] = classify_action(row)
    row["Signal"] = make_signal(row)

    return row




def normalize_date_col(df, col="NgÃ y"):
    if df is None or df.empty or col not in df.columns:
        return df

    df = df.copy()
    df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


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


def make_pattern_key(row, market_regime="SIDEWAY"):
    strategy = str(row.get("Chiáº¿n lÆ°á»£c", "WATCH"))
    action = str(row.get("Action", "SKIP"))

    rsi = safe_float(row.get("RSI"), 0)
    rs20 = safe_float(row.get("RS20"), 0)
    vol = safe_float(row.get("Volume Ratio"), 0)
    atr = safe_float(row.get("ATR %"), 999)
    dist = safe_float(row.get("Dist MA20 %"), 0)

    if rsi >= 75:
        rsi_bucket = "RSI_HIGH"
    elif rsi >= 55:
        rsi_bucket = "RSI_MID_HIGH"
    elif rsi >= 45:
        rsi_bucket = "RSI_MID"
    elif rsi >= 30:
        rsi_bucket = "RSI_LOW"
    else:
        rsi_bucket = "RSI_WEAK"

    if rs20 >= 8:
        rs_bucket = "RS_STRONG"
    elif rs20 >= 0:
        rs_bucket = "RS_OK"
    elif rs20 >= -8:
        rs_bucket = "RS_WEAK"
    else:
        rs_bucket = "RS_BAD"

    if vol >= 1.5:
        vol_bucket = "VOL_STRONG"
    elif vol >= 1.0:
        vol_bucket = "VOL_OK"
    else:
        vol_bucket = "VOL_LOW"

    if atr <= 6:
        atr_bucket = "ATR_LOW"
    elif atr <= 9:
        atr_bucket = "ATR_OK"
    else:
        atr_bucket = "ATR_HIGH"

    if dist >= 12:
        dist_bucket = "FAR_MA20"
    elif dist >= 0:
        dist_bucket = "ABOVE_MA20"
    else:
        dist_bucket = "BELOW_MA20"

    return "|".join([
        market_regime,
        strategy,
        action,
        rsi_bucket,
        rs_bucket,
        vol_bucket,
        atr_bucket,
        dist_bucket
    ])


def append_signal_history(combined, market_ret20):
    """
    LÆ°u lá»ch sá»­ tÃ­n hiá»u má»i láº§n cháº¡y.
    KhÃ´ng há»c váº¹t: chá» lÆ°u pattern + bá»i cáº£nh thá» trÆ°á»ng + features cáº§n thiáº¿t.
    """
    if combined is None or combined.empty or "MÃ£" not in combined.columns:
        return pd.DataFrame()

    market_regime = current_market_regime if 'current_market_regime' in globals() else classify_market_regime(market_ret20)

    keep_cols = [
        "NgÃ y", "MÃ£", "Close", "Signal", "Chiáº¿n lÆ°á»£c", "Action", "Score",
        "AI Confidence", "AI Grade", "AI Action",
        "RSI", "Ret5 %", "Ret10 %", "Ret20 %", "RS20",
        "Volume Ratio", "ADX", "ATR %", "Dist MA20 %",
        "Risk Status", "Fetch Mode"
    ]

    hist_new = combined[[c for c in keep_cols if c in combined.columns]].copy()
    hist_new["Run At"] = now_vietnam().strftime("%Y-%m-%d %H:%M:%S")
    hist_new["Market Ret20"] = round(safe_float(market_ret20, 0), 2)
    hist_new["Market Regime"] = market_regime
    hist_new["Pattern Key"] = hist_new.apply(lambda r: make_pattern_key(r, market_regime), axis=1)

    if "NgÃ y" not in hist_new.columns:
        hist_new["NgÃ y"] = now_vietnam().strftime("%Y-%m-%d")

    old = safe_read_csv(SIGNAL_HISTORY_PATH)

    if not old.empty:
        hist = pd.concat([old, hist_new], ignore_index=True)
    else:
        hist = hist_new

    # chá»ng trÃ¹ng: cÃ¹ng ngÃ y + mÃ£ giá»¯ dÃ²ng má»i nháº¥t
    if "NgÃ y" in hist.columns and "MÃ£" in hist.columns:
        hist["NgÃ y"] = pd.to_datetime(hist["NgÃ y"], errors="coerce").dt.strftime("%Y-%m-%d")
        hist = hist.drop_duplicates(subset=["NgÃ y", "MÃ£"], keep="last")

    # chá» giá»¯ 180 ngÃ y gáº§n nháº¥t cho nháº¹
    hist_dt = pd.to_datetime(hist.get("NgÃ y"), errors="coerce")
    cutoff = pd.Timestamp(now_vietnam().date()) - pd.Timedelta(days=180)
    hist = hist[(hist_dt.isna()) | (hist_dt >= cutoff)].copy()

    hist = normalize_outcome_dtype(hist)
    hist.to_csv(SIGNAL_HISTORY_PATH, index=False, encoding="utf-8-sig")
    print(f"â Updated signal history: {len(hist)} rows")

    return hist


def compute_forward_outcome_for_signal(row):
    """
    TÃ­nh outcome sau 3/5/10 phiÃªn tá»« cache_stock.
    Chá» dÃ¹ng dá»¯ liá»u ÄÃ£ cÃ³, khÃ´ng gá»i API thÃªm.
    """
    symbol = str(row.get("MÃ£", ""))
    signal_date = pd.to_datetime(row.get("NgÃ y"), errors="coerce")
    entry_price = safe_float(row.get("Close"), np.nan)

    if not symbol or pd.isna(signal_date) or pd.isna(entry_price):
        return {}

    cache_path = os.path.join(CACHE_DIR, f"{symbol}.csv")

    if not os.path.exists(cache_path):
        return {}

    dfp = safe_read_csv(cache_path)

    if dfp.empty or "close" not in dfp.columns:
        return {}

    date_col = "time" if "time" in dfp.columns else "date" if "date" in dfp.columns else None
    if date_col is None:
        return {}

    dfp = dfp.copy()
    dfp[date_col] = pd.to_datetime(dfp[date_col], errors="coerce")
    dfp = dfp.dropna(subset=[date_col, "close"]).sort_values(date_col).reset_index(drop=True)

    idxs = dfp.index[dfp[date_col] >= signal_date]
    if len(idxs) == 0:
        return {}

    entry_idx = int(idxs[0])
    out = {}

    for hold in HOLD_DAYS_LIST:
        target_idx = entry_idx + hold
        if target_idx < len(dfp):
            future_close = safe_float(dfp.loc[target_idx, "close"], np.nan)
            ret = (future_close / entry_price - 1) * 100 if entry_price and not pd.isna(future_close) else np.nan
            out[f"Ret+{hold}D %"] = round(ret, 2) if not pd.isna(ret) else np.nan
        else:
            out[f"Ret+{hold}D %"] = np.nan

    # max favorable / adverse trong 10 phiÃªn náº¿u cÃ³ high/low
    end_idx = min(entry_idx + 10, len(dfp) - 1)
    window = dfp.iloc[entry_idx:end_idx + 1]

    if not window.empty:
        if "high" in window.columns:
            max_high = pd.to_numeric(window["high"], errors="coerce").max()
            out["Max+10D %"] = round((max_high / entry_price - 1) * 100, 2) if entry_price and not pd.isna(max_high) else np.nan
        if "low" in window.columns:
            min_low = pd.to_numeric(window["low"], errors="coerce").min()
            out["Min+10D %"] = round((min_low / entry_price - 1) * 100, 2) if entry_price and not pd.isna(min_low) else np.nan

    max_ret = safe_float(out.get("Max+10D %"), np.nan)
    min_ret = safe_float(out.get("Min+10D %"), np.nan)
    ret5 = safe_float(out.get("Ret+5D %"), np.nan)
    ret10 = safe_float(out.get("Ret+10D %"), np.nan)

    if not pd.isna(max_ret) and max_ret >= TP_LEARN_PCT:
        out["Outcome"] = "WIN_TP"
    elif not pd.isna(min_ret) and min_ret <= SL_LEARN_PCT:
        out["Outcome"] = "LOSS_SL"
    elif not pd.isna(ret10):
        out["Outcome"] = "WIN" if ret10 > 0 else "LOSS"
    elif not pd.isna(ret5):
        out["Outcome"] = "WIN" if ret5 > 0 else "LOSS"
    else:
        out["Outcome"] = "PENDING"

    return out


def update_history_outcomes(hist):
    if hist is None or hist.empty:
        return pd.DataFrame()

    hist = hist.copy()
    hist = normalize_outcome_dtype(hist)

    outcome_cols = ["Ret+3D %", "Ret+5D %", "Ret+10D %", "Max+10D %", "Min+10D %", "Outcome"]
    for col in outcome_cols:
        if col not in hist.columns:
            hist[col] = np.nan if col != "Outcome" else "PENDING"

    # chá» cáº­p nháº­t nhá»¯ng dÃ²ng chÆ°a cÃ³ outcome hoáº·c cÃ²n pending
    mask = hist["Outcome"].isna() | (hist["Outcome"].astype(str).isin(["", "nan", "PENDING"]))
    idxs = list(hist[mask].index)

    updated = 0
    for idx in idxs:
        out = compute_forward_outcome_for_signal(hist.loc[idx])
        if not out:
            continue

        for k, v in out.items():
            hist.at[idx, k] = v
        updated += 1

    if updated:
        print(f"â Updated outcomes: {updated} signals")

    hist.to_csv(SIGNAL_HISTORY_PATH, index=False, encoding="utf-8-sig")
    return hist


def build_pattern_stats(hist):
    """
    Pattern stats cÃ³ decay + lookback, trÃ¡nh há»c váº¹t lá»ch sá»­ quÃ¡ xa.
    """
    if hist is None or hist.empty or "Pattern Key" not in hist.columns:
        return pd.DataFrame()

    h = hist.copy()
    h = normalize_outcome_dtype(h)
    h["NgÃ y"] = pd.to_datetime(h["NgÃ y"], errors="coerce")
    h = h.dropna(subset=["NgÃ y", "Pattern Key"])

    cutoff = pd.Timestamp(now_vietnam().date()) - pd.Timedelta(days=HISTORY_LOOKBACK_DAYS)
    h = h[h["NgÃ y"] >= cutoff].copy()

    if h.empty:
        return pd.DataFrame()

    h["Outcome"] = h.get("Outcome", "PENDING").astype(str)
    h = h[~h["Outcome"].isin(["PENDING", "", "nan"])].copy()

    if h.empty:
        return pd.DataFrame()

    today = pd.Timestamp(now_vietnam().date())
    age_days = (today - h["NgÃ y"]).dt.days.clip(lower=0)

    # exponential decay: dá»¯ liá»u cÃ ng cÅ© cÃ ng nháº¹
    h["Decay Weight"] = np.exp(-np.log(2) * age_days / DECAY_HALFLIFE_DAYS)

    h["Win Flag"] = h["Outcome"].isin(["WIN", "WIN_TP"]).astype(int)
    h["Loss Flag"] = h["Outcome"].isin(["LOSS", "LOSS_SL"]).astype(int)

    rows = []
    for key, g in h.groupby("Pattern Key"):
        sample = len(g)
        weighted_n = g["Decay Weight"].sum()
        weighted_win = (g["Win Flag"] * g["Decay Weight"]).sum()

        # Bayesian smoothing: trÃ¡nh Ã­t máº«u mÃ  tá»± tin quÃ¡
        prior_n = 10
        prior_p = BASE_WIN_PROB / 100
        win_prob = ((weighted_win + prior_p * prior_n) / (weighted_n + prior_n)) * 100

        avg_ret5 = pd.to_numeric(g.get("Ret+5D %"), errors="coerce").mean()
        avg_ret10 = pd.to_numeric(g.get("Ret+10D %"), errors="coerce").mean()

        rows.append({
            "Pattern Key": key,
            "Samples": sample,
            "Weighted Samples": round(weighted_n, 2),
            "Win Probability": round(win_prob, 2),
            "Win Count": int(g["Win Flag"].sum()),
            "Loss Count": int(g["Loss Flag"].sum()),
            "Avg Ret+5D %": round(avg_ret5, 2) if not pd.isna(avg_ret5) else np.nan,
            "Avg Ret+10D %": round(avg_ret10, 2) if not pd.isna(avg_ret10) else np.nan,
            "Updated": now_vietnam().strftime("%Y-%m-%d %H:%M:%S")
        })

    stats = pd.DataFrame(rows)

    if not stats.empty:
        stats = stats.sort_values(["Win Probability", "Weighted Samples"], ascending=False)
        stats.to_csv(PATTERN_STATS_PATH, index=False, encoding="utf-8-sig")
        print(f"â Pattern stats updated: {len(stats)} patterns")

    return stats



def build_walk_forward_stats(hist):
    """
    Walk-forward validation:
    há»c Äoáº¡n trÆ°á»c -> test Äoáº¡n sau, dÃ¹ng káº¿t quáº£ ngoÃ i máº«u Äá» trÃ¡nh há»c váº¹t.
    """
    if hist is None or hist.empty or "Pattern Key" not in hist.columns:
        return pd.DataFrame()

    h = hist.copy()
    h = normalize_outcome_dtype(h)
    h["NgÃ y"] = pd.to_datetime(h["NgÃ y"], errors="coerce")
    h = h.dropna(subset=["NgÃ y", "Pattern Key"])
    h["Outcome"] = h.get("Outcome", "PENDING").astype(str)
    h = h[~h["Outcome"].isin(["PENDING", "", "nan"])].copy()

    if h.empty:
        return pd.DataFrame()

    h["Win Flag"] = h["Outcome"].isin(["WIN", "WIN_TP"]).astype(int)

    min_date = h["NgÃ y"].min()
    max_date = h["NgÃ y"].max()

    if pd.isna(min_date) or pd.isna(max_date):
        return pd.DataFrame()

    rows = []
    cur_train_start = min_date

    while True:
        train_start = cur_train_start
        train_end = train_start + pd.Timedelta(days=WF_TRAIN_DAYS)
        test_start = train_end
        test_end = test_start + pd.Timedelta(days=WF_TEST_DAYS)

        if test_start > max_date:
            break

        train = h[(h["NgÃ y"] >= train_start) & (h["NgÃ y"] < train_end)].copy()
        test = h[(h["NgÃ y"] >= test_start) & (h["NgÃ y"] < test_end)].copy()

        if not train.empty and not test.empty:
            train_patterns = set(train["Pattern Key"].dropna().astype(str))
            test = test[test["Pattern Key"].astype(str).isin(train_patterns)].copy()

            for key, g in test.groupby("Pattern Key"):
                sample = len(g)
                if sample <= 0:
                    continue

                win_rate = g["Win Flag"].mean() * 100
                avg_ret5 = pd.to_numeric(g.get("Ret+5D %"), errors="coerce").mean()
                avg_ret10 = pd.to_numeric(g.get("Ret+10D %"), errors="coerce").mean()

                rows.append({
                    "Pattern Key": key,
                    "Train Start": train_start.strftime("%Y-%m-%d"),
                    "Train End": train_end.strftime("%Y-%m-%d"),
                    "Test Start": test_start.strftime("%Y-%m-%d"),
                    "Test End": test_end.strftime("%Y-%m-%d"),
                    "OOS Samples": sample,
                    "OOS Win Rate": round(win_rate, 2),
                    "OOS Avg Ret+5D %": round(avg_ret5, 2) if not pd.isna(avg_ret5) else np.nan,
                    "OOS Avg Ret+10D %": round(avg_ret10, 2) if not pd.isna(avg_ret10) else np.nan,
                })

        cur_train_start = cur_train_start + pd.Timedelta(days=WF_STEP_DAYS)

        if cur_train_start + pd.Timedelta(days=WF_TRAIN_DAYS) > max_date:
            break

    wf_raw = pd.DataFrame(rows)

    if wf_raw.empty:
        return pd.DataFrame()

    agg_rows = []
    for key, g in wf_raw.groupby("Pattern Key"):
        total_samples = int(g["OOS Samples"].sum())
        windows = len(g)

        if total_samples <= 0:
            continue

        weighted_win = (g["OOS Win Rate"] * g["OOS Samples"]).sum() / total_samples
        avg_ret5 = pd.to_numeric(g["OOS Avg Ret+5D %"], errors="coerce").mean()
        avg_ret10 = pd.to_numeric(g["OOS Avg Ret+10D %"], errors="coerce").mean()

        reliability = min(
            1.0,
            (windows / max(WF_MIN_WINDOWS, 1)) * 0.5 +
            (total_samples / max(WF_MIN_TEST_SAMPLES * 3, 1)) * 0.5
        )

        if windows < WF_MIN_WINDOWS or total_samples < WF_MIN_TEST_SAMPLES:
            status = "LOW_SAMPLE"
        elif weighted_win >= 60:
            status = "OOS_STRONG"
        elif weighted_win >= WF_MIN_OOS_WIN_PROB:
            status = "OOS_OK"
        elif weighted_win < 45:
            status = "OOS_BAD"
        else:
            status = "OOS_WEAK"

        agg_rows.append({
            "Pattern Key": key,
            "OOS Windows": windows,
            "OOS Samples": total_samples,
            "OOS Win Probability": round(weighted_win, 2),
            "OOS Avg Ret+5D %": round(avg_ret5, 2) if not pd.isna(avg_ret5) else np.nan,
            "OOS Avg Ret+10D %": round(avg_ret10, 2) if not pd.isna(avg_ret10) else np.nan,
            "OOS Reliability": round(reliability, 2),
            "OOS Status": status,
            "Updated": now_vietnam().strftime("%Y-%m-%d %H:%M:%S")
        })

    wf_stats = pd.DataFrame(agg_rows)

    if not wf_stats.empty:
        wf_stats = wf_stats.sort_values(["OOS Win Probability", "OOS Samples"], ascending=False)
        wf_stats.to_csv(WALK_FORWARD_STATS_PATH, index=False, encoding="utf-8-sig")
        print(f"â Walk-forward stats updated: {len(wf_stats)} patterns")

    return wf_stats


def apply_walk_forward_filter(combined, wf_stats):
    """
    Káº¿t há»£p walk-forward vÃ o Final Action.
    """
    if combined is None or combined.empty:
        return combined

    df = combined.copy()

    if "Final Action" not in df.columns:
        df["Final Action"] = df.get("AI Action", df.get("Action", "THEO DÃI"))

    if wf_stats is None or wf_stats.empty or "Pattern Key" not in df.columns:
        df["OOS Win Probability"] = np.nan
        df["OOS Samples"] = 0
        df["OOS Status"] = "NO_WF_DATA"
        df["Walk Forward Note"] = "ChÆ°a Äá»§ dá»¯ liá»u walk-forward"
        return df

    wf_map = wf_stats.set_index("Pattern Key").to_dict(orient="index")

    oos_probs = []
    oos_samples = []
    oos_statuses = []
    wf_notes = []
    final_actions = []

    for _, r in df.iterrows():
        key = r.get("Pattern Key")
        stat = wf_map.get(key)

        final_action = str(r.get("Final Action", r.get("AI Action", r.get("Action", "THEO DÃI"))))
        ai_conf = safe_float(r.get("AI Confidence"), safe_float(r.get("Score"), 50))
        win_prob = safe_float(r.get("Win Probability"), BASE_WIN_PROB)

        if not stat:
            oos_prob = np.nan
            sample = 0
            status = "NO_WF_DATA"
            note = "Pattern chÆ°a cÃ³ walk-forward"

            if final_action == "MUA Æ¯U TIÃN" and win_prob < 60:
                final_action = "MUA THÄM DÃ"
                note += " | chÆ°a Äá»§ OOS nÃªn giáº£m 1 báº­c"
        else:
            oos_prob = safe_float(stat.get("OOS Win Probability"), np.nan)
            sample = int(safe_float(stat.get("OOS Samples"), 0))
            status = str(stat.get("OOS Status", "NO_WF_DATA"))
            reliability = safe_float(stat.get("OOS Reliability"), 0)
            note = f"OOS {sample} máº«u, win ~{oos_prob:.1f}%, reliability {reliability:.2f}"

            if status in ["OOS_BAD", "OOS_WEAK"] and final_action in ["MUA Æ¯U TIÃN", "MUA THÄM DÃ"]:
                final_action = "CHá» XÃC NHáº¬N"
                note += " | walk-forward yáº¿u, háº¡ tÃ­n hiá»u"
            elif status == "OOS_BAD":
                final_action = "Bá» QUA"
                note += " | OOS xáº¥u"
            elif status in ["OOS_STRONG", "OOS_OK"] and ai_conf >= 75 and win_prob >= 55:
                if final_action in ["MUA THÄM DÃ", "CHá» XÃC NHáº¬N", "THEO DÃI Máº NH"]:
                    final_action = "MUA THÄM DÃ"
                    note += " | OOS á»§ng há»"
                if status == "OOS_STRONG" and ai_conf >= 85:
                    final_action = "MUA Æ¯U TIÃN"
                    note += " | OOS máº¡nh + AI máº¡nh"
            elif status == "LOW_SAMPLE":
                if final_action == "MUA Æ¯U TIÃN":
                    final_action = "MUA THÄM DÃ"
                note += " | Ã­t máº«u OOS, trÃ¡nh há»c váº¹t"

        oos_probs.append(round(oos_prob, 2) if not pd.isna(oos_prob) else np.nan)
        oos_samples.append(sample)
        oos_statuses.append(status)
        wf_notes.append(note)
        final_actions.append(final_action)

    df["OOS Win Probability"] = oos_probs
    df["OOS Samples"] = oos_samples
    df["OOS Status"] = oos_statuses
    df["Walk Forward Note"] = wf_notes
    df["Final Action"] = final_actions

    return df


def apply_history_learning(combined, pattern_stats, market_ret20):
    """
    ThÃªm Win Probability vÃ  Äiá»u chá»nh AI Action báº±ng thá»ng kÃª lá»ch sá»­ cÃ³ kiá»m soÃ¡t.
    KhÃ´ng override hoÃ n toÃ n rule-based AI Äá» trÃ¡nh há»c váº¹t.
    """
    if combined is None or combined.empty:
        return combined

    df = combined.copy()
    market_regime = current_market_regime if 'current_market_regime' in globals() else classify_market_regime(market_ret20)

    if "Pattern Key" not in df.columns:
        df["Pattern Key"] = df.apply(lambda r: make_pattern_key(r, market_regime), axis=1)

    if pattern_stats is None or pattern_stats.empty:
        df["Win Probability"] = BASE_WIN_PROB
        df["History Samples"] = 0
        df["History Note"] = "ChÆ°a Äá»§ lá»ch sá»­"
        return df

    stats_map = pattern_stats.set_index("Pattern Key").to_dict(orient="index")

    win_probs = []
    samples = []
    notes = []
    final_actions = []

    for _, r in df.iterrows():
        key = r.get("Pattern Key")
        stat = stats_map.get(key)

        base_ai_action = str(r.get("AI Action", r.get("Action", "THEO DÃI")))
        ai_conf = safe_float(r.get("AI Confidence"), safe_float(r.get("Score"), 50))

        if not stat:
            win_p = BASE_WIN_PROB
            sample = 0
            note = "Pattern má»i/chÆ°a Äá»§ dá»¯ liá»u"
        else:
            win_p = safe_float(stat.get("Win Probability"), BASE_WIN_PROB)
            sample = int(safe_float(stat.get("Samples"), 0))
            note = f"Pattern {sample} máº«u, win ~{win_p:.1f}%"

        # báº£o vá» chá»ng há»c váº¹t: Ã­t máº«u thÃ¬ áº£nh hÆ°á»ng nháº¹
        if sample < MIN_PATTERN_SAMPLES:
            adjusted_p = BASE_WIN_PROB * 0.7 + win_p * 0.3
            note += " (Ã­t máº«u, giáº£m trá»ng sá»)"
        else:
            adjusted_p = win_p

        # quyáº¿t Äá»nh cuá»i: káº¿t há»£p AI confidence + win probability
        if base_ai_action in ["MUA Æ¯U TIÃN", "MUA THÄM DÃ"] and adjusted_p >= 62 and ai_conf >= 78:
            final_action = "MUA Æ¯U TIÃN"
        elif base_ai_action in ["MUA Æ¯U TIÃN", "MUA THÄM DÃ"] and adjusted_p >= 55:
            final_action = "MUA THÄM DÃ"
        elif base_ai_action in ["MUA Æ¯U TIÃN", "MUA THÄM DÃ"] and adjusted_p < 50:
            final_action = "CHá» XÃC NHáº¬N"
            note += " | lá»ch sá»­ pattern chÆ°a á»§ng há»"
        elif adjusted_p >= 60 and ai_conf >= 70:
            final_action = "THEO DÃI Máº NH"
        elif adjusted_p < 45:
            final_action = "Bá» QUA"
            note += " | xÃ¡c suáº¥t lá»ch sá»­ tháº¥p"
        else:
            final_action = base_ai_action

        win_probs.append(round(adjusted_p, 2))
        samples.append(sample)
        notes.append(note)
        final_actions.append(final_action)

    df["Win Probability"] = win_probs
    df["History Samples"] = samples
    df["History Note"] = notes
    df["Final Action"] = final_actions

    return df


def advanced_ai_filter(row, market_ret20=0):
    """
    AI Filter nÃ¢ng cao:
    - KhÃ´ng thay tháº¿ bá» lá»c ká»¹ thuáº­t gá»c.
    - ThÃªm lá»p ÄÃ¡nh giÃ¡ cháº¥t lÆ°á»£ng tÃ­n hiá»u: AI Confidence, AI Grade, AI Action, AI Reason.
    """
    reasons = []
    warnings = []
    confidence = safe_float(row.get("Score"), 0)

    strategy = str(row.get("Chiáº¿n lÆ°á»£c", ""))
    action = str(row.get("Action", ""))
    risk_status = str(row.get("Risk Status", ""))

    rsi = safe_float(row.get("RSI"), 0)
    rs20 = safe_float(row.get("RS20"), 0)
    atr = safe_float(row.get("ATR %"), 999)
    vol_ratio = safe_float(row.get("Volume Ratio"), 0)
    ret5 = safe_float(row.get("Ret5 %"), 0)
    ret10 = safe_float(row.get("Ret10 %"), 0)
    dist_ma20 = safe_float(row.get("Dist MA20 %"), 0)
    drawdown = safe_float(row.get("Drawdown20 %"), 0)
    rebound = safe_float(row.get("Rebound Low20 %"), 0)
    adx = safe_float(row.get("ADX"), 0)
    macd_up = bool(row.get("MACD Hist Up"))

    # Base: risk fail thÃ¬ háº¡ máº¡nh
    if risk_status == "FAIL" or action == "SKIP":
        confidence -= 25
        warnings.append("Risk/Action chÆ°a Äáº¡t")

    # Thá» trÆ°á»ng chung
    if market_ret20 < -3:
        confidence -= 12
        warnings.append("Thá» trÆ°á»ng chung yáº¿u")
    elif market_ret20 > 3:
        confidence += 5
        reasons.append("Thá» trÆ°á»ng chung thuáº­n lá»£i")

    # Relative strength
    if rs20 >= 8:
        confidence += 12
        reasons.append("RS20 ráº¥t máº¡nh")
    elif rs20 >= 3:
        confidence += 7
        reasons.append("RS20 tá»t")
    elif rs20 < -8:
        confidence -= 15
        warnings.append("RS20 yáº¿u")
    elif rs20 < -3:
        confidence -= 7
        warnings.append("RS20 chÆ°a khá»e")

    # Volume confirmation
    if vol_ratio >= 1.5:
        confidence += 8
        reasons.append("Volume xÃ¡c nháº­n máº¡nh")
    elif vol_ratio >= 1.1:
        confidence += 4
        reasons.append("Volume á»n")
    elif vol_ratio < 0.8:
        confidence -= 10
        warnings.append("Volume yáº¿u")

    # Risk by ATR
    if atr <= 5:
        confidence += 6
        reasons.append("Biáº¿n Äá»ng tháº¥p")
    elif atr <= 8:
        confidence += 2
    elif atr > 10:
        confidence -= 18
        warnings.append("ATR quÃ¡ cao")
    elif atr > 8:
        confidence -= 8
        warnings.append("ATR hÆ¡i cao")

    # FOMO filter for momentum
    if strategy in ["MOMENTUM", "MOMENTUM_WATCH"]:
        if rsi > 82:
            confidence -= 18
            warnings.append("Momentum quÃ¡ nÃ³ng")
        elif rsi > 75:
            confidence -= 8
            warnings.append("RSI cao, khÃ´ng mua Äuá»i")
        elif 55 <= rsi <= 72:
            confidence += 7
            reasons.append("RSI momentum Äáº¹p")

        if dist_ma20 > 14:
            confidence -= 15
            warnings.append("GiÃ¡ xa MA20, dá» pullback")
        elif 0 <= dist_ma20 <= 10:
            confidence += 6
            reasons.append("Khoáº£ng cÃ¡ch MA20 há»£p lÃ½")

        if ret5 > 10:
            confidence -= 12
            warnings.append("TÄng ngáº¯n háº¡n quÃ¡ nhanh")
        elif ret5 > 2 and ret10 > 3:
            confidence += 6
            reasons.append("ÄÃ  tÄng xÃ¡c nháº­n")

        if adx > 22:
            confidence += 5
            reasons.append("Xu hÆ°á»ng cÃ³ lá»±c")

    # Falling knife filter for bottom
    if strategy in ["BOTTOM", "BOTTOM_WATCH"]:
        if 35 <= rsi <= 48:
            confidence += 7
            reasons.append("RSI vÃ¹ng há»i phá»¥c há»£p lÃ½")
        elif rsi < 30:
            confidence -= 12
            warnings.append("RSI quÃ¡ yáº¿u, rá»§i ro dao rÆ¡i")
        elif rsi > 55:
            confidence -= 6
            warnings.append("Bottom nhÆ°ng RSI ÄÃ£ há»i cao")

        if drawdown <= -7 and rebound >= 2:
            confidence += 8
            reasons.append("CÃ³ há»i phá»¥c tá»« ÄÃ¡y")
        elif drawdown <= -7 and rebound < 1:
            confidence -= 12
            warnings.append("ChÆ°a cÃ³ lá»±c há»i tá»« ÄÃ¡y")

        if rs20 < -8:
            confidence -= 12
            warnings.append("Báº¯t ÄÃ¡y nhÆ°ng yáº¿u hÆ¡n thá» trÆ°á»ng")
        elif rs20 > -3:
            confidence += 5
            reasons.append("Bottom khÃ´ng quÃ¡ yáº¿u so vá»i thá» trÆ°á»ng")

        if vol_ratio >= 1:
            confidence += 5
            reasons.append("CÃ³ volume Äá»¡ giÃ¡")

    # MACD confirmation
    if macd_up:
        confidence += 5
        reasons.append("MACD Hist tÄng")
    else:
        confidence -= 5
        warnings.append("MACD chÆ°a xÃ¡c nháº­n")

    confidence = max(0, min(100, round(confidence, 0)))

    if confidence >= 90:
        grade = "A+"
    elif confidence >= 80:
        grade = "A"
    elif confidence >= 70:
        grade = "B+"
    elif confidence >= 60:
        grade = "B"
    elif confidence >= 50:
        grade = "C"
    else:
        grade = "D"

    # AI Action thá»±c táº¿
    if action == "BUY NOW" and confidence >= 85:
        ai_action = "MUA Æ¯U TIÃN"
    elif action == "BUY NOW" and confidence >= 75:
        ai_action = "MUA THÄM DÃ"
    elif action == "BUY NOW" and confidence < 75:
        ai_action = "CHá» XÃC NHáº¬N"
    elif action == "WAIT" and confidence >= 75:
        ai_action = "CHá» PULLBACK"
    elif action == "WATCHLIST" and confidence >= 65:
        ai_action = "THEO DÃI Máº NH"
    elif confidence < 50:
        ai_action = "Bá» QUA"
    else:
        ai_action = "THEO DÃI"

    reason_text = "; ".join(reasons[:4])
    warning_text = "; ".join(warnings[:4])

    if not reason_text:
        reason_text = "ChÆ°a cÃ³ Äiá»m cá»ng ná»i báº­t"
    if not warning_text:
        warning_text = "KhÃ´ng cÃ³ cáº£nh bÃ¡o lá»n"

    return confidence, grade, ai_action, reason_text, warning_text


def apply_advanced_ai_filter(df, market_ret20=0):
    if df is None or df.empty:
        return df

    df = df.copy()

    results = df.apply(lambda r: advanced_ai_filter(r, market_ret20), axis=1)
    df["AI Confidence"] = [x[0] for x in results]
    df["AI Grade"] = [x[1] for x in results]
    df["AI Action"] = [x[2] for x in results]
    df["AI Reason"] = [x[3] for x in results]
    df["AI Warning"] = [x[4] for x in results]

    return df


def build_portfolio_and_action_plan(combined, ai_risk):
    portfolio = safe_read_csv(PORTFOLIO_PATH)

    if not portfolio.empty and "MÃ£" in portfolio.columns:
        tracker = portfolio.merge(
            combined,
            on="MÃ£",
            how="left",
            suffixes=("", "_signal")
        )

        tracker["GiÃ¡ vá»n"] = pd.to_numeric(tracker.get("GiÃ¡ vá»n"), errors="coerce")
        tracker["Sá» lÆ°á»£ng"] = pd.to_numeric(tracker.get("Sá» lÆ°á»£ng"), errors="coerce")
        tracker["Close"] = pd.to_numeric(tracker.get("Close"), errors="coerce")

        tracker["GiÃ¡ trá» vá»n"] = tracker["GiÃ¡ vá»n"] * tracker["Sá» lÆ°á»£ng"]
        tracker["GiÃ¡ trá» hiá»n táº¡i"] = tracker["Close"] * tracker["Sá» lÆ°á»£ng"]
        tracker["LÃ£i/Lá» %"] = (tracker["Close"] / tracker["GiÃ¡ vá»n"] - 1) * 100
        tracker["LÃ£i/Lá» tiá»n"] = tracker["GiÃ¡ trá» hiá»n táº¡i"] - tracker["GiÃ¡ trá» vá»n"]

        def holding_action(row):
            pnl = safe_float(row.get("LÃ£i/Lá» %"), 0)
            action = str(row.get("Action", ""))
            risk = str(row.get("Risk Status", ""))
            rsi = safe_float(row.get("RSI"), 0)
            strategy = str(row.get("Chiáº¿n lÆ°á»£c", ""))

            if pd.isna(row.get("Close")):
                return "CHÆ¯A CÃ DATA"
            if risk == "FAIL":
                return "GIáº¢M / BÃN"
            if pnl <= -5:
                return "Cáº®T Lá»"
            if pnl >= 10 and rsi >= 75:
                return "CHá»T Lá»I Má»T PHáº¦N"
            if pnl >= 7:
                return "GIá»® / CANH CHá»T"
            if action == "BUY NOW":
                return "GIá»® Máº NH"
            if strategy in ["MOMENTUM", "BOTTOM", "MOMENTUM_WATCH", "BOTTOM_WATCH"]:
                return "GIá»®"
            return "THEO DÃI"

        tracker["HÃ nh Äá»ng"] = tracker.apply(holding_action, axis=1)

        def risk_flag(row):
            pnl = safe_float(row.get("LÃ£i/Lá» %"), 0)
            rsi = safe_float(row.get("RSI"), 0)
            risk = str(row.get("Risk Status", ""))

            if risk == "FAIL":
                return "â RISK FAIL"
            if pnl <= -4:
                return "ð´ NGUY HIá»M"
            if pnl <= -2:
                return "ð¡ Cáº¢NH BÃO"
            if rsi >= 80:
                return "â ï¸ QUÃ MUA"
            if pnl > 0:
                return "ð¢ ÄANG LÃI"
            return "ð¢ á»N"

        tracker["Cáº£nh bÃ¡o"] = tracker.apply(risk_flag, axis=1)

        keep_tracker = [
            "MÃ£", "GiÃ¡ vá»n", "Close", "Sá» lÆ°á»£ng",
            "GiÃ¡ trá» vá»n", "GiÃ¡ trá» hiá»n táº¡i",
            "LÃ£i/Lá» %", "LÃ£i/Lá» tiá»n",
            "Signal", "Chiáº¿n lÆ°á»£c", "Score", "RSI",
            "Risk Status", "Risk Reason", "Action",
            "HÃ nh Äá»ng", "Cáº£nh bÃ¡o"
        ]
        tracker = tracker[[c for c in keep_tracker if c in tracker.columns]]

    else:
        tracker = pd.DataFrame([{
            "MÃ£": "NO_PORTFOLIO",
            "HÃ nh Äá»ng": "ChÆ°a cÃ³ portfolio_current.csv",
            "Cáº£nh bÃ¡o": "â ï¸ CHÆ¯A CÃ DANH Má»¤C"
        }])

    tracker.to_csv(PORTFOLIO_TRACKER_PATH, index=False, encoding="utf-8-sig")

    buy_plan = ai_risk[ai_risk["Action"] == "BUY NOW"].copy()

    if not buy_plan.empty:
        buy_plan["HÃ nh Äá»ng"] = "MUA Má»I"
        buy_plan["LÃ½ do"] = buy_plan["Signal"].astype(str) + " | Score " + buy_plan["Score"].astype(str)
        keep_buy = [
            "NgÃ y", "MÃ£", "HÃ nh Äá»ng", "LÃ½ do",
            "Signal", "Chiáº¿n lÆ°á»£c", "Score", "AI Confidence", "AI Grade", "AI Action", "Win Probability", "History Samples", "OOS Win Probability", "OOS Samples", "OOS Status", "Regime Win Probability", "Regime Samples", "Market Regime Now", "Final Action", "History Note", "Walk Forward Note", "Regime Note", "AI Reason", "AI Warning",
            "RSI", "Close", "RS20", "Volume Ratio",
            "ADX", "ATR %", "Risk Status"
        ]
        buy_plan = buy_plan[[c for c in keep_buy if c in buy_plan.columns]]
    else:
        buy_plan = pd.DataFrame()

    hold_plan = tracker.copy()

    if not hold_plan.empty and "MÃ£" in hold_plan.columns:
        hold_plan["NgÃ y"] = now_vietnam().strftime("%Y-%m-%d")
        hold_plan["LÃ½ do"] = "Theo dÃµi danh má»¥c hiá»n cÃ³"

        keep_hold = [
            "NgÃ y", "MÃ£", "HÃ nh Äá»ng", "Cáº£nh bÃ¡o", "LÃ½ do",
            "LÃ£i/Lá» %", "LÃ£i/Lá» tiá»n",
            "Signal", "Chiáº¿n lÆ°á»£c", "Score", "AI Confidence", "AI Grade", "AI Action", "Win Probability", "History Samples", "OOS Win Probability", "OOS Samples", "OOS Status", "Regime Win Probability", "Regime Samples", "Market Regime Now", "Final Action", "History Note", "Walk Forward Note", "Regime Note", "AI Reason", "AI Warning",
            "RSI", "Close", "Risk Status", "Risk Reason"
        ]
        hold_plan = hold_plan[[c for c in keep_hold if c in hold_plan.columns]]
    else:
        hold_plan = pd.DataFrame()

    action_plan = pd.concat([buy_plan, hold_plan], ignore_index=True)

    if action_plan.empty:
        action_plan = pd.DataFrame([{
            "NgÃ y": now_vietnam().strftime("%Y-%m-%d"),
            "MÃ£": "NO_ACTION",
            "HÃ nh Äá»ng": "KHÃNG LÃM GÃ",
            "LÃ½ do": "KhÃ´ng cÃ³ tÃ­n hiá»u mua vÃ  chÆ°a cÃ³ danh má»¥c"
        }])

    action_plan.to_csv(ACTION_PLAN_PATH, index=False, encoding="utf-8-sig")

    return tracker, action_plan



def get_env_secret(*names):
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None




def normalize_outcome_dtype(df):
    """
    Fix lá»i dtype: cá»t Outcome luÃ´n lÃ  text/object Äá» gÃ¡n PENDING/WIN/LOSS khÃ´ng crash.
    """
    if df is None:
        return df
    try:
        if "Outcome" not in df.columns:
            df["Outcome"] = "PENDING"
        df["Outcome"] = df["Outcome"].astype("object")
        df["Outcome"] = df["Outcome"].fillna("PENDING").astype(str)
    except Exception:
        pass
    return df


def safe_numeric_columns(df, cols=None):
    if df is None or df.empty:
        return df
    if cols is None:
        cols = [
            "Score", "AI Confidence", "Win Probability", "OOS Win Probability",
            "Regime Win Probability", "RSI", "RS20", "Close", "ATR %",
            "Volume Ratio", "History Samples", "OOS Samples", "Regime Samples"
        ]
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def vi_action_label(action):
    s = str(action or "").upper()
    if "MUA Æ¯U TIÃN" in s or "UU TIEN" in s:
        return "MUA Æ¯U TIÃN (PRIORITY BUY)"
    if "MUA THÄM DÃ" in s or "THAM DO" in s:
        return "MUA THÄM DÃ (PROBE BUY)"
    if "BUY NOW" in s:
        return "MUA NGAY (BUY NOW)"
    if "CHá» XÃC NHáº¬N" in s or "CHO XAC NHAN" in s:
        return "CHá» XÃC NHáº¬N (WAIT CONFIRM)"
    if "CHá» PULLBACK" in s or "PULLBACK" in s:
        return "CHá» PULLBACK (WAIT PULLBACK)"
    if "THEO DÃI Máº NH" in s or "THEO DOI MANH" in s:
        return "THEO DÃI Máº NH (STRONG WATCH)"
    if "THEO DÃI" in s or "WATCH" in s or "WATCHLIST" in s:
        return "THEO DÃI (WATCH)"
    if "Bá» QUA" in s or "BO QUA" in s or "SKIP" in s:
        return "Bá» QUA (SKIP)"
    if "WAIT" in s:
        return "CHá» (WAIT)"
    return str(action or "")


def vi_regime_label(regime):
    s = str(regime or "").upper()
    mapping = {
        "UPTREND": "TÄNG Máº NH (UPTREND)",
        "POSITIVE": "TÃCH Cá»°C (POSITIVE)",
        "SIDEWAY": "ÄI NGANG (SIDEWAY)",
        "WEAK": "Yáº¾U (WEAK)",
        "DOWNTREND": "GIáº¢M (DOWNTREND)",
        "HIGH_VOL_UP": "BIáº¾N Äá»NG CAO - TÄNG (HIGH VOL UP)",
        "HIGH_VOL_DOWN": "BIáº¾N Äá»NG CAO - GIáº¢M (HIGH VOL DOWN)",
    }
    return mapping.get(s, str(regime or ""))


def short_note(text_value, limit=90):
    s = str(text_value or "").replace("\n", " ").replace("\r", " ").strip()
    if s.lower() in ["nan", "none", ""]:
        return ""
    return s[:limit]

def now_vietnam():
    return datetime.utcnow() + timedelta(hours=7)


def now_vietnam():
    return datetime.utcnow() + timedelta(hours=7)


def get_price_data_date(df):
    """
    Lay ngay du lieu gia cuoi cung trong dataframe.
    Khong dung ngay run bot, vi GitHub co the chay sang 01/05 nhung data van la phien 30/04.
    """
    try:
        if df is None or df.empty:
            return now_vietnam().strftime("%Y-%m-%d")

        last = df.iloc[-1]
        for col in ["time", "date", "ngay", "NgÃ y"]:
            if col in df.columns:
                val = last.get(col)
                if pd.notna(val):
                    return str(val)[:10]

        return now_vietnam().strftime("%Y-%m-%d")
    except Exception:
        return now_vietnam().strftime("%Y-%m-%d")


def get_report_data_date(*dfs):
    """
    Lay ngay du lieu lon nhat tu cac file output de hien thi tren Telegram/dashboard.
    """
    dates = []
    for df in dfs:
        try:
            if df is not None and not df.empty and "NgÃ y" in df.columns:
                s = pd.to_datetime(df["NgÃ y"], errors="coerce").dropna()
                if not s.empty:
                    dates.append(s.max())
        except Exception:
            pass

    if dates:
        return max(dates).strftime("%Y-%m-%d")

    return now_vietnam().strftime("%Y-%m-%d")

def build_telegram_message(entry, action_plan, combined, tracker):
    """
    Telegram V9 Stable Final:
    - Tiáº¿ng Viá»t + English label
    - Gá»n, dá» Äá»c
    - UTF-8 chuáº©n
    - KhÃ´ng spam quÃ¡ dÃ i
    """
    run_time = now_vietnam().strftime("%Y-%m-%d %H:%M:%S")
    data_date = get_report_data_date(entry, action_plan, combined)

    try:
        total_codes = len(set(combined["MÃ£"].dropna().astype(str)) & set(UNIVERSE))
        missing_codes = sorted(set(UNIVERSE) - set(combined["MÃ£"].dropna().astype(str)))
    except Exception:
        total_codes = 0
        missing_codes = []

    source_df = entry.copy() if entry is not None and not entry.empty else pd.DataFrame()

    if source_df.empty and action_plan is not None and not action_plan.empty:
        source_df = action_plan.copy()

    if source_df.empty and combined is not None and not combined.empty:
        source_df = combined.copy()

    if source_df is None or source_df.empty:
        return (
            "ð¤ BOT GIAO Dá»CH V9 STABLE\n"
            f"â° Thá»i gian cháº¡y (Run time): {run_time}\n"
            f"ð NgÃ y dá»¯ liá»u (Data date): {data_date}\n"
            "KhÃ´ng cÃ³ dá»¯ liá»u tÃ­n hiá»u.\n"
            "Dashboard HTML ÄÆ°á»£c gá»­i kÃ¨m náº¿u cÃ³."
        )

    source_df = safe_numeric_columns(source_df)

    # Current regime
    try:
        current_regime = str(combined.get("Market Regime Now").dropna().iloc[0]) if "Market Regime Now" in combined.columns else ""
    except Exception:
        current_regime = ""

    # Count final actions
    action_col = "Final Action" if "Final Action" in source_df.columns else "AI Action" if "AI Action" in source_df.columns else "Action" if "Action" in source_df.columns else None

    def count_action_contains(keywords):
        if not action_col:
            return 0
        s = source_df[action_col].astype(str).str.upper()
        mask = False
        for kw in keywords:
            mask = mask | s.str.contains(kw.upper(), na=False)
        return int(mask.sum())

    buy_count = count_action_contains(["MUA", "BUY"])
    wait_count = count_action_contains(["CHá»", "CHO", "WAIT"])
    watch_count = count_action_contains(["THEO DÃI", "THEO DOI", "WATCH"])
    skip_count = count_action_contains(["Bá» QUA", "BO QUA", "SKIP"])

    # Focus top rows
    focus = source_df.copy()
    if action_col:
        s = focus[action_col].astype(str).str.upper()
        preferred = s.str.contains("MUA|BUY|CHá»|CHO|WAIT|WATCH|THEO", na=False)
        if preferred.any():
            focus = focus[preferred].copy()

    sort_cols = [c for c in ["Regime Win Probability", "OOS Win Probability", "Win Probability", "AI Confidence", "Score"] if c in focus.columns]
    if sort_cols:
        focus = focus.sort_values(sort_cols, ascending=False)
    elif "Score" in focus.columns:
        focus = focus.sort_values("Score", ascending=False)

    focus = focus.head(5)

    lines = []
    lines.append("ð¤ BOT GIAO Dá»CH V9 STABLE")
    lines.append(f"â° Thá»i gian cháº¡y (Run): {run_time}")
    lines.append(f"ð NgÃ y dá»¯ liá»u (Data): {data_date}")
    lines.append(f"ð Version: {SYSTEM_VERSION}")
    if current_regime:
        lines.append(f"ð Thá» trÆ°á»ng (Regime): {vi_regime_label(current_regime)}")
    lines.append(f"â Coverage: {total_codes}/{len(UNIVERSE)} mÃ£")

    if missing_codes:
        lines.append(f"â ï¸ Thiáº¿u {len(missing_codes)} mÃ£")
        lines.append("MÃ£ thiáº¿u Äáº§u tiÃªn: " + ", ".join(missing_codes[:10]))

    lines.append("")
    lines.append(f"ð¥ Mua (Buy): {buy_count} | ð¡ Chá» (Wait): {wait_count} | ð Theo dÃµi (Watch): {watch_count} | â Bá» qua: {skip_count}")
    if tracker is not None and not tracker.empty:
        lines.append(f"ð¦ Danh má»¥c (Portfolio rows): {len(tracker)}")

    lines.append("")
    lines.append("ð TÃN HIá»U Ná»I Báº¬T (TOP SIGNALS):")

    def fnum(row, col, digits=0):
        try:
            v = row.get(col)
            if pd.isna(v):
                return ""
            return f"{float(v):.{digits}f}"
        except Exception:
            return ""

    for _, r in focus.iterrows():
        code = str(r.get("MÃ£", r.get("Ma", ""))).strip()
        final_action = vi_action_label(r.get("Final Action", r.get("AI Action", r.get("Action", ""))))
        grade = str(r.get("AI Grade", "")).strip()

        ai = fnum(r, "AI Confidence", 0)
        win = fnum(r, "Win Probability", 0)
        oos = fnum(r, "OOS Win Probability", 0)
        reg = fnum(r, "Regime Win Probability", 0)
        score = fnum(r, "Score", 0)
        close = fnum(r, "Close", 2)
        rsi = fnum(r, "RSI", 0)
        rs20 = fnum(r, "RS20", 1)

        lines.append(f"- {code} | {final_action}")
        detail = []
        if grade and grade.lower() != "nan":
            detail.append(f"Grade {grade}")
        if ai:
            detail.append(f"AI {ai}")
        if score:
            detail.append(f"Score {score}")
        if win:
            detail.append(f"Win {win}%")
        if oos:
            detail.append(f"OOS {oos}%")
        if reg:
            detail.append(f"Reg {reg}%")

        if detail:
            lines.append("  " + " | ".join(detail))

        market = []
        if close:
            market.append(f"GiÃ¡ {close}")
        if rsi:
            market.append(f"RSI {rsi}")
        if rs20:
            market.append(f"RS20 {rs20}")
        if market:
            lines.append("  " + " | ".join(market))

        wf_note = short_note(r.get("Walk Forward Note", ""), 85)
        regime_note = short_note(r.get("Regime Note", ""), 85)
        hist_note = short_note(r.get("History Note", ""), 75)

        if wf_note:
            lines.append(f"  ð§ª WF: {wf_note}")
        if regime_note:
            lines.append(f"  ð Regime: {regime_note}")
        elif hist_note:
            lines.append(f"  ð History: {hist_note}")

    lines.append("")
    lines.append("ð Dashboard HTML ÄÃ£ gá»­i kÃ¨m Äá» xem chi tiáº¿t.")
    return "\n".join(lines)


def send_telegram_document(token, chat_id, file_path, caption=""):
    if not os.path.exists(file_path):
        print(f"â ï¸ KhÃ´ng tháº¥y file ÄÃ­nh kÃ¨m: {file_path}")
        return

    try:
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        with open(file_path, "rb") as f:
            r = requests.post(
                url,
                data={
                    "chat_id": chat_id,
                    "caption": caption,
                    "disable_web_page_preview": True
                },
                files={
                    "document": (os.path.basename(file_path), f, "text/html")
                },
                timeout=60
            )

        if r.status_code == 200:
            print("â Telegram dashboard file sent")
        else:
            print(f"â ï¸ Telegram dashboard send failed: {r.status_code} - {r.text}")

    except Exception as e:
        print("â ï¸ Telegram dashboard error:", repr(e))


def send_telegram_alert(entry, action_plan, combined, tracker):
    if not TELEGRAM_ENABLED:
        print("Telegram alert disabled")
        return

    token = get_env_secret("TELEGRAM_TOKEN", "TELEGRAM_BOT_TOKEN", "BOT_TOKEN")
    chat_id = get_env_secret("TELEGRAM_CHAT_ID", "CHAT_ID", "TELEGRAM_CHAT")

    if not token or not chat_id:
        print("â ï¸ Thiáº¿u TELEGRAM_TOKEN hoáº·c TELEGRAM_CHAT_ID â bá» qua Telegram")
        return

    msg = build_telegram_message(entry, action_plan, combined, tracker)

    try:
        # 1) Gá»­i tin nháº¯n tÃ³m táº¯t ngáº¯n
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": msg,
                "disable_web_page_preview": True
            },
            timeout=30
        )

        if r.status_code == 200:
            print("â Telegram alert sent")
        else:
            print(f"â ï¸ Telegram send failed: {r.status_code} - {r.text}")

        # 2) Gá»­i kÃ¨m file dashboard HTML
        send_telegram_document(
            token,
            chat_id,
            DASHBOARD_PATH,
            caption="ð Dashboard HTML - má» file Äá» xem chi tiáº¿t"
        )

    except Exception as e:
        print("â ï¸ Telegram error:", repr(e))


def html_style():
    return """
<style>
body {
    background-color: #0f1117;
    color: #f1f1f1;
    font-family: Arial, sans-serif;
    padding: 20px;
}
h2 {
    font-size: 34px;
}
h3 {
    margin-top: 35px;
    color: #ff4d4f;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin-bottom: 24px;
    font-size: 14px;
}
th {
    background-color: #1f2430;
    color: #ffffff;
    padding: 8px;
    border: 1px solid #333;
}
td {
    padding: 8px;
    border: 1px solid #333;
}
tr:nth-child(even) {
    background-color: #171b24;
}
tr:nth-child(odd) {
    background-color: #11151d;
}
</style>
"""



def get_backfill_state():
    df = safe_read_csv(BACKFILL_STATE_PATH)
    if df.empty or "next_start" not in df.columns:
        return 0
    try:
        return int(df["next_start"].iloc[-1])
    except Exception:
        return 0


def save_backfill_state(next_start):
    pd.DataFrame([{
        "updated_at": now_vietnam().strftime("%Y-%m-%d %H:%M:%S"),
        "next_start": next_start,
        "version": SYSTEM_VERSION
    }]).to_csv(BACKFILL_STATE_PATH, index=False, encoding="utf-8-sig")


def classify_backfill_row(row, market_ret20=0):
    """
    Táº¡o láº¡i tÃ­n hiá»u quÃ¡ khá»© báº±ng chÃ­nh logic hiá»n táº¡i.
    ÄÃ¢y lÃ  backfill giáº£ láº­p, khÃ´ng dÃ¹ng tÆ°Æ¡ng lai Äá» táº¡o tÃ­n hiá»u.
    """
    close = safe_float(row.get("close"))
    ma5 = safe_float(row.get("MA5"))
    ma20 = safe_float(row.get("MA20"))
    rsi = safe_float(row.get("RSI"))

    if pd.isna(close) or pd.isna(ma5) or pd.isna(ma20) or pd.isna(rsi):
        return None

    ret20 = safe_float(row.get("Ret20 %"), 0)
    rs20 = ret20 - market_ret20

    r = {
        "Close": round(close, 2),
        "MA5": round(ma5, 2),
        "MA20": round(ma20, 2),
        "RSI": round(rsi, 2),
        "Ret5 %": round(safe_float(row.get("Ret5 %"), 0), 2),
        "Ret10 %": round(safe_float(row.get("Ret10 %"), 0), 2),
        "Ret20 %": round(ret20, 2),
        "RS20": round(rs20, 2),
        "Volume Ratio": round(safe_float(row.get("Volume Ratio"), 0), 2),
        "ADX": round(safe_float(row.get("ADX"), 0), 2),
        "ATR %": round(safe_float(row.get("ATR %"), 999), 2),
        "MACD Hist": round(safe_float(row.get("MACD Hist"), 0), 4),
        "MACD Hist Up": bool(row.get("MACD Hist Up")),
        "Dist MA20 %": round(safe_float(row.get("Dist MA20 %"), 0), 2),
        "Drawdown20 %": round(safe_float(row.get("Drawdown20 %"), 0), 2),
        "Rebound Low20 %": round(safe_float(row.get("Rebound Low20 %"), 0), 2),
        "Low20": round(safe_float(row.get("Low20"), 0), 2),
        "High20": round(safe_float(row.get("High20"), 0), 2),
    }

    r["Momentum Score"] = score_momentum(r)
    r["Bottom Score"] = score_bottom(r)
    r["Score"] = max(r["Momentum Score"], r["Bottom Score"])
    r["Chiáº¿n lÆ°á»£c"] = classify_strategy(r)

    risk_status, risk_reason = risk_filter(r)
    r["Risk Status"] = risk_status
    r["Risk Reason"] = risk_reason
    r["Action"] = classify_action(r)
    r["Signal"] = make_signal(r)

    return r


def get_price_date_col(df):
    if "time" in df.columns:
        return "time"
    if "date" in df.columns:
        return "date"
    return None


def compute_outcome_from_price_df(price_df, entry_idx, entry_price):
    out = {}

    for hold in HOLD_DAYS_LIST:
        target_idx = entry_idx + hold
        if target_idx < len(price_df):
            future_close = safe_float(price_df.loc[target_idx, "close"], np.nan)
            ret = (future_close / entry_price - 1) * 100 if entry_price and not pd.isna(future_close) else np.nan
            out[f"Ret+{hold}D %"] = round(ret, 2) if not pd.isna(ret) else np.nan
        else:
            out[f"Ret+{hold}D %"] = np.nan

    end_idx = min(entry_idx + 10, len(price_df) - 1)
    window = price_df.iloc[entry_idx:end_idx + 1]

    if not window.empty:
        if "high" in window.columns:
            max_high = pd.to_numeric(window["high"], errors="coerce").max()
            out["Max+10D %"] = round((max_high / entry_price - 1) * 100, 2) if entry_price and not pd.isna(max_high) else np.nan
        if "low" in window.columns:
            min_low = pd.to_numeric(window["low"], errors="coerce").min()
            out["Min+10D %"] = round((min_low / entry_price - 1) * 100, 2) if entry_price and not pd.isna(min_low) else np.nan

    max_ret = safe_float(out.get("Max+10D %"), np.nan)
    min_ret = safe_float(out.get("Min+10D %"), np.nan)
    ret5 = safe_float(out.get("Ret+5D %"), np.nan)
    ret10 = safe_float(out.get("Ret+10D %"), np.nan)

    if not pd.isna(max_ret) and max_ret >= TP_LEARN_PCT:
        out["Outcome"] = "WIN_TP"
    elif not pd.isna(min_ret) and min_ret <= SL_LEARN_PCT:
        out["Outcome"] = "LOSS_SL"
    elif not pd.isna(ret10):
        out["Outcome"] = "WIN" if ret10 > 0 else "LOSS"
    elif not pd.isna(ret5):
        out["Outcome"] = "WIN" if ret5 > 0 else "LOSS"
    else:
        out["Outcome"] = "PENDING"

    return out


def add_months(ts, months):
    """
    Cá»ng thÃ¡ng khÃ´ng cáº§n dateutil, Äá»§ dÃ¹ng cho block 3/4/6 thÃ¡ng.
    """
    ts = pd.Timestamp(ts)
    month = ts.month - 1 + int(months)
    year = ts.year + month // 12
    month = month % 12 + 1
    return pd.Timestamp(year=year, month=month, day=1)


def get_backfill_block_info(date_value):
    """
    Chia lá»ch sá»­ theo block Äá»ng.
    Máº·c Äá»nh V8 dÃ¹ng 3 thÃ¡ng:
    Q1: Jan-Mar, Q2: Apr-Jun, Q3: Jul-Sep, Q4: Oct-Dec.
    Náº¿u Äá»i BACKFILL_BLOCK_MONTHS = 4/6 thÃ¬ tá»± chia tÆ°Æ¡ng á»©ng.
    """
    d = pd.to_datetime(date_value, errors="coerce")
    if pd.isna(d):
        return "", pd.NaT, pd.NaT

    block_months = max(1, int(BACKFILL_BLOCK_MONTHS))
    start_month = ((d.month - 1) // block_months) * block_months + 1

    block_start = pd.Timestamp(year=d.year, month=start_month, day=1)
    block_end = add_months(block_start, block_months)

    block_no = ((start_month - 1) // block_months) + 1
    block = f"{d.year}-B{block_no}_{block_months}M"

    return block, block_start, block_end


def get_train_test_tag(date_value, block_start, block_end):
    """
    Trong má»i block:
    80% thá»i gian Äáº§u = TRAIN
    20% thá»i gian cuá»i = TEST giáº£ láº­p chÆ°a biáº¿t.
    """
    d = pd.to_datetime(date_value, errors="coerce")
    if pd.isna(d) or pd.isna(block_start) or pd.isna(block_end):
        return "UNKNOWN"

    total_days = max((block_end - block_start).days, 1)
    split_day = block_start + pd.Timedelta(days=int(total_days * BACKFILL_TRAIN_RATIO))

    return "TRAIN" if d < split_day else "TEST"



def detect_market_regime_detail(market_df=None, market_ret20=0):
    """
    Regime detection:
    UPTREND / POSITIVE / SIDEWAY / WEAK / DOWNTREND / HIGH_VOL_UP / HIGH_VOL_DOWN.
    """
    fallback = classify_market_regime(market_ret20)

    try:
        if market_df is None or market_df.empty or len(market_df) < REGIME_LONG_MA + 5:
            return fallback

        df = add_indicators(market_df.copy())
        last = df.iloc[-1]

        ret20 = safe_float(last.get("Ret20 %"), market_ret20)
        atr = safe_float(last.get("ATR %"), 0)

        if "close" in df.columns:
            close = pd.to_numeric(df["close"], errors="coerce")
            ma20 = close.rolling(REGIME_SHORT_MA).mean().iloc[-1]
            ma50 = close.rolling(REGIME_LONG_MA).mean().iloc[-1]
        else:
            ma20 = np.nan
            ma50 = np.nan

        if atr >= REGIME_HIGH_VOL_ATR:
            return "HIGH_VOL_UP" if ret20 >= 0 else "HIGH_VOL_DOWN"

        if not pd.isna(ma20) and not pd.isna(ma50):
            if ma20 > ma50 and ret20 >= REGIME_STRONG_RET20:
                return "UPTREND"
            if ma20 < ma50 and ret20 <= REGIME_WEAK_RET20:
                return "DOWNTREND"

        if abs(ret20) <= REGIME_SIDEWAY_ABS_RET20:
            return "SIDEWAY"

        return "POSITIVE" if ret20 > 0 else "WEAK"

    except Exception:
        return fallback


def get_market_regime_from_cache(market_ret20=0):
    for benchmark in ["VNINDEX", "VN30"]:
        try:
            cache_path = os.path.join(CACHE_DIR, f"{benchmark}.csv")
            if not os.path.exists(cache_path):
                continue

            df = safe_read_csv(cache_path)
            if df.empty:
                continue

            regime = detect_market_regime_detail(df, market_ret20)
            print(f"ð Market regime: {regime}")
            return regime
        except Exception:
            continue

    regime = classify_market_regime(market_ret20)
    print(f"ð Market regime fallback: {regime}")
    return regime


def compute_recent_decay_weight(date_value):
    d = pd.to_datetime(date_value, errors="coerce")
    if pd.isna(d):
        return RECENT_WEIGHT_MIN

    try:
        age_days = max((pd.Timestamp(now_vietnam().date()) - d).days, 0)
    except Exception:
        age_days = 0

    w = np.exp(-np.log(2) * age_days / max(DECAY_HALFLIFE_DAYS, 1))
    return max(RECENT_WEIGHT_MIN, float(w))


def build_regime_stats(hist):
    """
    Thá»ng kÃª hiá»u quáº£ pattern theo regime, cÃ³ time-decay.
    """
    if hist is None or hist.empty:
        return pd.DataFrame()

    h = hist.copy()
    h = normalize_outcome_dtype(h)
    if "Pattern Key" not in h.columns or "Market Regime" not in h.columns:
        return pd.DataFrame()

    h["NgÃ y"] = pd.to_datetime(h["NgÃ y"], errors="coerce")
    h = h.dropna(subset=["NgÃ y", "Pattern Key", "Market Regime"])
    h["Outcome"] = h.get("Outcome", "PENDING").astype(str)
    h = h[~h["Outcome"].isin(["PENDING", "", "nan"])].copy()

    if h.empty:
        return pd.DataFrame()

    h["Win Flag"] = h["Outcome"].isin(["WIN", "WIN_TP"]).astype(int)
    h["Decay Weight"] = h["NgÃ y"].apply(compute_recent_decay_weight)

    rows = []
    for (regime, key), g in h.groupby(["Market Regime", "Pattern Key"]):
        sample = len(g)
        weighted_n = g["Decay Weight"].sum()
        weighted_win = (g["Win Flag"] * g["Decay Weight"]).sum()

        prior_n = 8
        prior_p = BASE_WIN_PROB / 100
        win_p = ((weighted_win + prior_p * prior_n) / (weighted_n + prior_n)) * 100

        rows.append({
            "Market Regime": regime,
            "Pattern Key": key,
            "Regime Samples": sample,
            "Regime Weighted Samples": round(weighted_n, 2),
            "Regime Win Probability": round(win_p, 2),
            "Updated": now_vietnam().strftime("%Y-%m-%d %H:%M:%S")
        })

    stats = pd.DataFrame(rows)
    if not stats.empty:
        stats = stats.sort_values(["Regime Win Probability", "Regime Weighted Samples"], ascending=False)
        stats.to_csv(REGIME_STATS_PATH, index=False, encoding="utf-8-sig")
        print(f"â Regime stats updated: {len(stats)} rows")

    return stats


def apply_regime_decay_filter(combined, regime_stats, current_regime):
    """
    Final filter V9: Äiá»u chá»nh Final Action theo regime hiá»n táº¡i + time-decay stats.
    """
    if combined is None or combined.empty:
        return combined

    df = combined.copy()
    df["Market Regime Now"] = current_regime

    if "Final Action" not in df.columns:
        df["Final Action"] = df.get("AI Action", df.get("Action", "THEO DÃI"))

    if regime_stats is None or regime_stats.empty or "Pattern Key" not in df.columns:
        df["Regime Win Probability"] = np.nan
        df["Regime Samples"] = 0
        df["Regime Note"] = "ChÆ°a Äá»§ regime stats"
        return df

    rs = regime_stats[regime_stats["Market Regime"].astype(str) == str(current_regime)].copy()

    if rs.empty:
        df["Regime Win Probability"] = np.nan
        df["Regime Samples"] = 0
        df["Regime Note"] = f"ChÆ°a cÃ³ stats cho regime {current_regime}"
        return df

    rmap = rs.set_index("Pattern Key").to_dict(orient="index")

    probs, samples, notes, final_actions, adjusted_conf = [], [], [], [], []

    for _, r in df.iterrows():
        key = r.get("Pattern Key")
        stat = rmap.get(key)

        final_action = str(r.get("Final Action", r.get("AI Action", r.get("Action", "THEO DÃI"))))
        conf = safe_float(r.get("AI Confidence"), safe_float(r.get("Score"), 50))

        if not stat:
            probs.append(np.nan)
            samples.append(0)
            notes.append(f"Pattern chÆ°a cÃ³ dá»¯ liá»u trong regime {current_regime}")
            final_actions.append(final_action)
            adjusted_conf.append(round(conf, 0))
            continue

        p = safe_float(stat.get("Regime Win Probability"), BASE_WIN_PROB)
        n = int(safe_float(stat.get("Regime Samples"), 0))
        note = f"{current_regime}: {n} máº«u, win decay ~{p:.1f}%"

        if n >= MIN_PATTERN_SAMPLES and p >= 62:
            conf += REGIME_BONUS_STRONG
            note += " | regime á»§ng há»"
            if final_action in ["MUA THÄM DÃ", "THEO DÃI Máº NH", "CHá» XÃC NHáº¬N"] and conf >= 78:
                final_action = "MUA THÄM DÃ"
            if final_action == "MUA THÄM DÃ" and conf >= 88:
                final_action = "MUA Æ¯U TIÃN"

        elif n >= MIN_PATTERN_SAMPLES and p < 48:
            conf -= REGIME_PENALTY_BAD
            note += " | regime yáº¿u, háº¡ tÃ­n hiá»u"
            if final_action in ["MUA Æ¯U TIÃN", "MUA THÄM DÃ"]:
                final_action = "CHá» XÃC NHáº¬N"
            elif final_action in ["CHá» XÃC NHáº¬N", "THEO DÃI Máº NH"] and p < 42:
                final_action = "Bá» QUA"

        elif n < MIN_PATTERN_SAMPLES:
            note += " | Ã­t máº«u regime, khÃ´ng nÃ¢ng máº¡nh"
            if final_action == "MUA Æ¯U TIÃN":
                final_action = "MUA THÄM DÃ"

        probs.append(round(p, 2))
        samples.append(n)
        notes.append(note)
        final_actions.append(final_action)
        adjusted_conf.append(round(max(0, min(100, conf)), 0))

    df["Regime Win Probability"] = probs
    df["Regime Samples"] = samples
    df["Regime Note"] = notes
    df["Final Action"] = final_actions
    df["AI Confidence"] = adjusted_conf

    return df


def build_backfill_history_from_cache(market_ret20=0):
    """
    Backfill lá»ch sá»­ tá»« cache_stock:
    - Chia tá»«ng block thá»i gian.
    - Trong má»i ná»­a nÄm: 80% Äáº§u TRAIN, 20% cuá»i TEST.
    - TEST ÄÆ°á»£c dÃ¹ng Äá» ÄÃ¡nh giÃ¡ ngoÃ i máº«u, trÃ¡nh há»c váº¹t.
    """
    if not BACKFILL_ENABLED:
        print("Backfill disabled")
        return safe_read_csv(BACKFILL_SIGNAL_HISTORY_PATH)

    os.makedirs(CACHE_DIR, exist_ok=True)

    start_idx = get_backfill_state()
    if start_idx >= len(UNIVERSE):
        start_idx = 0

    end_idx = min(start_idx + BACKFILL_MAX_SYMBOLS_PER_RUN, len(UNIVERSE))
    symbols = UNIVERSE[start_idx:end_idx]

    print(f"ð§  Backfill V7: {start_idx} â {end_idx} / {len(UNIVERSE)}")

    rows = []
    market_regime = current_market_regime if 'current_market_regime' in globals() else classify_market_regime(market_ret20)

    cutoff = pd.Timestamp(now_vietnam().date()) - pd.Timedelta(days=BACKFILL_LOOKBACK_DAYS)

    for symbol in symbols:
        cache_path = os.path.join(CACHE_DIR, f"{symbol}.csv")
        if not os.path.exists(cache_path):
            continue

        dfp = safe_read_csv(cache_path)
        if dfp.empty or "close" not in dfp.columns:
            continue

        date_col = get_price_date_col(dfp)
        if date_col is None:
            continue

        dfp = dfp.copy()
        dfp[date_col] = pd.to_datetime(dfp[date_col], errors="coerce")
        dfp = dfp.dropna(subset=[date_col, "close"]).sort_values(date_col).reset_index(drop=True)

        for col in ["open", "high", "low", "close", "volume"]:
            if col in dfp.columns:
                dfp[col] = pd.to_numeric(dfp[col], errors="coerce")

        dfp = dfp[dfp[date_col] >= cutoff].reset_index(drop=True)

        if len(dfp) < BACKFILL_MIN_ROWS_PER_SYMBOL:
            continue

        ind = add_indicators(dfp)

        for i in range(60, len(ind) - max(HOLD_DAYS_LIST) - 1):
            row0 = ind.iloc[i]
            date_value = row0.get(date_col)

            signal_row = classify_backfill_row(row0, market_ret20)
            if not signal_row:
                continue

            # chá» lÆ°u cÃ¡c tÃ­n hiá»u cÃ³ Ã½ nghÄ©a, bá» WATCH ráº¥t yáº¿u Äá» nháº¹ file
            if signal_row["Score"] < 55:
                continue

            entry_price = safe_float(signal_row.get("Close"), np.nan)
            if pd.isna(entry_price):
                continue

            out = compute_outcome_from_price_df(ind, i, entry_price)

            d = pd.to_datetime(date_value, errors="coerce")
            if pd.isna(d):
                continue

            block, block_start, block_end = get_backfill_block_info(d)
            split_tag = get_train_test_tag(d, block_start, block_end)

            rec = {
                "NgÃ y": d.strftime("%Y-%m-%d"),
                "MÃ£": symbol,
                "Run At": now_vietnam().strftime("%Y-%m-%d %H:%M:%S"),
                "Market Ret20": round(safe_float(market_ret20, 0), 2),
                "Market Regime": market_regime,
                "Backfill Block": block,
                "Train/Test": split_tag,
                "Block Start": block_start.strftime("%Y-%m-%d"),
                "Block End": block_end.strftime("%Y-%m-%d"),
            }

            rec.update(signal_row)
            rec.update(out)
            rec["Pattern Key"] = make_pattern_key(rec, market_regime)

            rows.append(rec)

    new_hist = pd.DataFrame(rows)

    old = safe_read_csv(BACKFILL_SIGNAL_HISTORY_PATH)
    if not old.empty and not new_hist.empty:
        hist = pd.concat([old, new_hist], ignore_index=True)
    elif not old.empty:
        hist = old
    else:
        hist = new_hist

    if not hist.empty and "NgÃ y" in hist.columns and "MÃ£" in hist.columns:
        hist = hist.drop_duplicates(subset=["NgÃ y", "MÃ£", "Pattern Key"], keep="last")
        hist = hist.sort_values(["NgÃ y", "MÃ£"])

    hist = normalize_outcome_dtype(hist)
    hist.to_csv(BACKFILL_SIGNAL_HISTORY_PATH, index=False, encoding="utf-8-sig")

    next_start = end_idx
    if next_start >= len(UNIVERSE):
        next_start = 0
    save_backfill_state(next_start)

    print(f"â Backfill history rows: {len(hist)} | new rows: {len(new_hist)} | next: {next_start}")

    return hist


def build_backfill_walk_forward_stats(backfill_hist):
    """
    ÄÃ¡nh giÃ¡ theo block thá»i gian:
    TRAIN 80% Äáº§u chá» Äá» xÃ¡c Äá»nh pattern ÄÃ£ xuáº¥t hiá»n.
    TEST 20% sau dÃ¹ng Äá» Äo OOS winrate.
    """
    if backfill_hist is None or backfill_hist.empty:
        return pd.DataFrame()

    h = backfill_hist.copy()
    h = normalize_outcome_dtype(h)

    if "Train/Test" not in h.columns or "Pattern Key" not in h.columns:
        return pd.DataFrame()

    h["Outcome"] = h.get("Outcome", "PENDING").astype(str)
    h = h[~h["Outcome"].isin(["PENDING", "", "nan"])].copy()

    if h.empty:
        return pd.DataFrame()

    h["Win Flag"] = h["Outcome"].isin(["WIN", "WIN_TP"]).astype(int)

    rows = []

    for block, gb in h.groupby("Backfill Block"):
        train = gb[gb["Train/Test"].astype(str) == "TRAIN"].copy()
        test = gb[gb["Train/Test"].astype(str) == "TEST"].copy()

        if train.empty or test.empty:
            continue

        train_patterns = set(train["Pattern Key"].dropna().astype(str))
        test = test[test["Pattern Key"].astype(str).isin(train_patterns)].copy()

        if test.empty:
            continue

        for key, g in test.groupby("Pattern Key"):
            sample = len(g)
            win_rate = g["Win Flag"].mean() * 100
            avg_ret5 = pd.to_numeric(g.get("Ret+5D %"), errors="coerce").mean()
            avg_ret10 = pd.to_numeric(g.get("Ret+10D %"), errors="coerce").mean()

            rows.append({
                "Pattern Key": key,
                "Backfill Block": block,
                "OOS Samples": sample,
                "OOS Win Rate": round(win_rate, 2),
                "OOS Avg Ret+5D %": round(avg_ret5, 2) if not pd.isna(avg_ret5) else np.nan,
                "OOS Avg Ret+10D %": round(avg_ret10, 2) if not pd.isna(avg_ret10) else np.nan,
            })

    raw = pd.DataFrame(rows)

    if raw.empty:
        return pd.DataFrame()

    agg = []
    for key, g in raw.groupby("Pattern Key"):
        total_samples = int(g["OOS Samples"].sum())
        windows = len(g)
        weighted_win = (g["OOS Win Rate"] * g["OOS Samples"]).sum() / max(total_samples, 1)
        avg_ret5 = pd.to_numeric(g.get("OOS Avg Ret+5D %"), errors="coerce").mean()
        avg_ret10 = pd.to_numeric(g.get("OOS Avg Ret+10D %"), errors="coerce").mean()

        reliability = min(1.0, (windows / max(WF_MIN_WINDOWS, 1)) * 0.5 + (total_samples / max(WF_MIN_TEST_SAMPLES * 3, 1)) * 0.5)

        if windows < WF_MIN_WINDOWS or total_samples < WF_MIN_TEST_SAMPLES:
            status = "LOW_SAMPLE"
        elif weighted_win >= 60:
            status = "OOS_STRONG"
        elif weighted_win >= WF_MIN_OOS_WIN_PROB:
            status = "OOS_OK"
        elif weighted_win < 45:
            status = "OOS_BAD"
        else:
            status = "OOS_WEAK"

        agg.append({
            "Pattern Key": key,
            "OOS Windows": windows,
            "OOS Samples": total_samples,
            "OOS Win Probability": round(weighted_win, 2),
            "OOS Avg Ret+5D %": round(avg_ret5, 2) if not pd.isna(avg_ret5) else np.nan,
            "OOS Avg Ret+10D %": round(avg_ret10, 2) if not pd.isna(avg_ret10) else np.nan,
            "OOS Reliability": round(reliability, 2),
            "OOS Status": status,
            "Updated": now_vietnam().strftime("%Y-%m-%d %H:%M:%S")
        })

    stats = pd.DataFrame(agg)
    if not stats.empty:
        stats = stats.sort_values(["OOS Win Probability", "OOS Samples"], ascending=False)
        stats.to_csv(BACKFILL_WALK_FORWARD_PATH, index=False, encoding="utf-8-sig")
        print(f"â Backfill walk-forward stats: {len(stats)} patterns")

    return stats


def merge_walk_forward_sources(live_wf, backfill_wf):
    """
    Æ¯u tiÃªn live walk-forward náº¿u cÃ³.
    Náº¿u live chÆ°a Äá»§, bá» sung báº±ng backfill walk-forward.
    """
    if live_wf is None or live_wf.empty:
        return backfill_wf if backfill_wf is not None else pd.DataFrame()

    if backfill_wf is None or backfill_wf.empty:
        return live_wf

    live = live_wf.copy()
    live["WF Source"] = "LIVE"

    back = backfill_wf.copy()
    back["WF Source"] = "BACKFILL"

    combined = pd.concat([live, back], ignore_index=True)
    combined = combined.sort_values(["WF Source", "OOS Samples"], ascending=[False, False])
    combined = combined.drop_duplicates(subset=["Pattern Key"], keep="first")

    combined.to_csv(WALK_FORWARD_STATS_PATH, index=False, encoding="utf-8-sig")
    return combined


# ================================
# MAIN
# ================================

print("ð RUN BATCH TRADING ENGINE - KBS")
print(f"ð SYSTEM VERSION: {SYSTEM_VERSION}")
print("â°", now_vietnam())

start_idx = load_state()
if start_idx >= len(UNIVERSE):
    start_idx = 0

end_idx = min(start_idx + BATCH_SIZE, len(UNIVERSE))
batch = UNIVERSE[start_idx:end_idx]

print(f"ð Batch: {start_idx} â {end_idx} / {len(UNIVERSE)}")
print("ð MÃ£:", batch)

market_ret20 = get_market_ret20()
current_market_regime = get_market_regime_from_cache(market_ret20)

rows = []

for i, symbol in enumerate(batch, 1):
    print(f"ð¡ {i}/{len(batch)} Fetch {symbol}")
    result = None

    try:
        result = analyze_symbol(symbol, market_ret20)
        if result:
            rows.append(result)
            print("â", symbol, result["Signal"], result["Action"], result["Score"])
        else:
            print("â ï¸", symbol, "khÃ´ng Äá»§ dá»¯ liá»u")
    except Exception as e:
        print("â", symbol, repr(e))

    if result and result.get("Fetch Mode") == "API":
        time.sleep(API_SLEEP_SEC)
    else:
        time.sleep(CACHE_SLEEP_SEC)

new_df = pd.DataFrame(rows)
old_df = safe_read_csv(ALL_RESULT_PATH)

if not old_df.empty and "MÃ£" in old_df.columns:
    old_df = old_df[~old_df["MÃ£"].isin(batch)]
    combined = pd.concat([old_df, new_df], ignore_index=True)
else:
    combined = new_df.copy()

if combined.empty:
    combined = pd.DataFrame([{
        "NgÃ y": now_vietnam().strftime("%Y-%m-%d"),
        "MÃ£": "NO_SIGNAL",
        "Close": np.nan,
        "Signal": "NO SIGNAL",
        "Chiáº¿n lÆ°á»£c": "SYSTEM",
        "Score": 0,
        "Action": "WAIT",
        "Risk Status": "SYSTEM",
        "Risk Reason": "",
        "Updated": now_vietnam().strftime("%Y-%m-%d %H:%M:%S"),
        "Version": SYSTEM_VERSION
    }])

needed_cols = ["Risk Status", "Action", "Chiáº¿n lÆ°á»£c", "Score", "MÃ£"]
for col in needed_cols:
    if col not in combined.columns:
        combined[col] = ""

combined["Score"] = pd.to_numeric(combined["Score"], errors="coerce").fillna(0)

# AI Filter nÃ¢ng cao
combined = apply_advanced_ai_filter(combined, market_ret20)

# AI Level 2: há»c lá»ch sá»­ cÃ³ kiá»m soÃ¡t, trÃ¡nh há»c váº¹t
signal_history = append_signal_history(combined, market_ret20)
signal_history = update_history_outcomes(signal_history)
pattern_stats = build_pattern_stats(signal_history)
walk_forward_stats = build_walk_forward_stats(signal_history)

# Backfill 3 thÃ¡ng: 80% train / 20% test Äá» táº¡o OOS stats ngay tá»« dá»¯ liá»u cache
backfill_history = build_backfill_history_from_cache(market_ret20)
backfill_wf_stats = build_backfill_walk_forward_stats(backfill_history)
walk_forward_stats = merge_walk_forward_sources(walk_forward_stats, backfill_wf_stats)

combined = apply_history_learning(combined, pattern_stats, market_ret20)
combined = apply_walk_forward_filter(combined, walk_forward_stats)

# V9: time-decay + regime detection filter
learning_hist_for_regime = backfill_history if 'backfill_history' in globals() and backfill_history is not None and not backfill_history.empty else signal_history
regime_stats = build_regime_stats(learning_hist_for_regime)
combined = apply_regime_decay_filter(combined, regime_stats, current_market_regime)
combined = safe_numeric_columns(combined)

sort_cols = [c for c in ["Final Action", "Win Probability", "AI Confidence", "Score"] if c in combined.columns]
if "Win Probability" in combined.columns:
    combined["Win Probability"] = pd.to_numeric(combined["Win Probability"], errors="coerce").fillna(BASE_WIN_PROB)
sort_by = [c for c in ["Regime Win Probability", "OOS Win Probability", "Win Probability", "AI Confidence", "Score"] if c in combined.columns]
combined = combined.sort_values(sort_by, ascending=False)

combined.to_csv(ALL_RESULT_PATH, index=False, encoding="utf-8-sig")

# Kiá»m tra nhanh dá»¯ liá»u ÄÃ£ Äá»§ mÃ£ chÆ°a
try:
    valid_codes = set(combined["MÃ£"].dropna().astype(str)) & set(UNIVERSE)
    missing_codes = sorted(set(UNIVERSE) - valid_codes)
    print(f"Coverage: {len(valid_codes)} / {len(UNIVERSE)} mÃ£")
    if missing_codes:
        print("Thiáº¿u mÃ£:", missing_codes)
    else:
        print("â Äá»§ mÃ£ trong all_signal_results.csv")
except Exception as e:
    print("â ï¸ KhÃ´ng kiá»m tra ÄÆ°á»£c coverage:", repr(e))

raw_signals = combined[
    combined["Chiáº¿n lÆ°á»£c"].isin([
        "MOMENTUM", "BOTTOM", "MOMENTUM_WATCH", "BOTTOM_WATCH", "WATCH"
    ])
].copy()
raw_signals = raw_signals.sort_values("AI Confidence" if "AI Confidence" in raw_signals.columns else "Score", ascending=False)
raw_signals.to_csv(RAW_SIGNAL_PATH, index=False, encoding="utf-8-sig")

ai_risk = combined[
    (combined["Risk Status"] == "PASS") &
    (combined["Action"].isin(["BUY NOW", "WAIT", "WATCHLIST"]))
].copy()
ai_risk = ai_risk.sort_values("AI Confidence" if "AI Confidence" in ai_risk.columns else "Score", ascending=False)
ai_risk.to_csv(AI_RISK_PATH, index=False, encoding="utf-8-sig")

bottom = ai_risk[
    ai_risk["Chiáº¿n lÆ°á»£c"].isin(["BOTTOM", "BOTTOM_WATCH"])
].copy()
momentum = ai_risk[
    ai_risk["Chiáº¿n lÆ°á»£c"].isin(["MOMENTUM", "MOMENTUM_WATCH"])
].copy()

bottom.to_csv(BOTTOM_PATH, index=False, encoding="utf-8-sig")
momentum.to_csv(MOMENTUM_PATH, index=False, encoding="utf-8-sig")

entry = ai_risk[
    ai_risk["Action"].isin(["BUY NOW", "WAIT", "WATCHLIST"])
].copy()
entry = entry.sort_values("AI Confidence" if "AI Confidence" in entry.columns else "Score", ascending=False).head(10)

if entry.empty:
    entry = pd.DataFrame([{
        "NgÃ y": now_vietnam().strftime("%Y-%m-%d"),
        "MÃ£": "NO_SIGNAL",
        "Action": "WAIT",
        "Chiáº¿n lÆ°á»£c": "SYSTEM",
        "Score": 0,
        "Risk Reason": "KhÃ´ng cÃ³ tÃ­n hiá»u Äáº¡t chuáº©n"
    }])
else:
    keep = [
        "NgÃ y", "MÃ£", "Action", "Signal", "Chiáº¿n lÆ°á»£c", "Score",
        "Momentum Score", "Bottom Score", "AI Confidence", "AI Grade", "AI Action", "Win Probability", "History Samples", "OOS Win Probability", "OOS Samples", "OOS Status", "Regime Win Probability", "Regime Samples", "Market Regime Now", "Final Action", "History Note", "Walk Forward Note", "Regime Note", "AI Reason", "AI Warning", "Risk Status", "Risk Reason",
        "RSI", "Close", "MA5", "MA20", "Ret5 %", "Ret10 %",
        "RS20", "Volume Ratio", "ADX", "ATR %", "Dist MA20 %"
    ]
    entry = entry[[c for c in keep if c in entry.columns]]

entry.to_csv(ENTRY_PATH, index=False, encoding="utf-8-sig")

tracker, action_plan = build_portfolio_and_action_plan(combined, ai_risk)

raw_html = raw_signals.to_html(index=False)
ai_html = ai_risk.to_html(index=False)
entry_html = entry.to_html(index=False)
tracker_html = tracker.to_html(index=False)
action_html = action_plan.to_html(index=False)

html_full = f"""
<html>
<head>
<meta charset="utf-8">
<title>Trading Dashboard</title>
{html_style()}
</head>
<body>

<h2>ð TRADING BOT CONTROL CENTER</h2>
<p><b>Generated:</b> {now_vietnam()}</p>
<p><b>Data date:</b> {get_report_data_date(combined, entry, action_plan)}</p>
<p><b>Version:</b> {SYSTEM_VERSION}</p>
<p><b>Batch:</b> {start_idx} â {end_idx} / {len(UNIVERSE)}</p>

<h3>ð TÃN HIá»U THÃ (RAW SIGNAL)</h3>
{raw_html}

<h3>ð¥ AI FINAL - Lá»C TINH</h3>
{ai_html}

<h3>ð ÄIá»M VÃO Lá»NH (ENTRY)</h3>
{entry_html}

<h3>ð¦ THEO DÃI DANH Má»¤C (PORTFOLIO TRACKER)</h3>
{tracker_html}

<h3>ð¯ Káº¾ HOáº CH HÃNH Äá»NG (ACTION PLAN)</h3>
{action_html}

</body>
</html>
"""

with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
    f.write(html_full)

# Gá»­i Telegram summary + dashboard HTML
send_telegram_alert(entry, action_plan, combined, tracker)

next_start = end_idx
if next_start >= len(UNIVERSE):
    next_start = 0

save_state(next_start)

print("â CREATED OUTPUT FILES")
print("Rows combined:", len(combined))
print("Raw signals:", len(raw_signals))
print("AI risk rows:", len(ai_risk))
print("Bottom rows:", len(bottom))
print("Momentum rows:", len(momentum))
print("Entry rows:", len(entry))
print("Portfolio rows:", len(tracker))
print("Action plan rows:", len(action_plan))
print("Next batch start:", next_start)
