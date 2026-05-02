from v10_config import *
from v10_utils import *
from v10_indicators import *
from v10_market_data import fetch_history

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
