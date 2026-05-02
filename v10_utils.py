from v10_config import *

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

def clean_ascii_text(x, limit=120):
    """
    Clean display text for Telegram/iPhone HTML.
    Avoid mojibake by using ASCII-only labels.
    """
    if x is None:
        return ""
    s = str(x)
    if s.lower() in ["nan", "none"]:
        return ""
    # Replace common Vietnamese action labels with ASCII
    repl = {
        "MUA Æ¯U TIÃN": "PRIORITY BUY",
        "MUA THÄM DÃ": "PROBE BUY",
        "CHá» XÃC NHáº¬N": "WAIT CONFIRM",
        "CHá» PULLBACK": "WAIT PULLBACK",
        "THEO DÃI Máº NH": "STRONG WATCH",
        "THEO DÃI": "WATCH",
        "Bá» QUA": "SKIP",
    }
    for k, v in repl.items():
        s = s.replace(k, v)

    # Remove non-ascii chars
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.replace("\n", " ").replace("\r", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]

def ascii_action_label(action):
    s = clean_ascii_text(action, 80).upper()
    if "PRIORITY" in s or "UU TIEN" in s:
        return "MUA UU TIEN / PRIORITY BUY"
    if "PROBE" in s or "THAM" in s:
        return "MUA THAM DO / PROBE BUY"
    if "BUY NOW" in s:
        return "MUA NGAY / BUY NOW"
    if "WAIT CONFIRM" in s or "XAC NHAN" in s:
        return "CHO XAC NHAN / WAIT CONFIRM"
    if "PULLBACK" in s:
        return "CHO PULLBACK / WAIT PULLBACK"
    if "STRONG WATCH" in s:
        return "THEO DOI MANH / STRONG WATCH"
    if "WATCH" in s:
        return "THEO DOI / WATCH"
    if "SKIP" in s:
        return "BO QUA / SKIP"
    if "WAIT" in s:
        return "CHO / WAIT"
    return clean_ascii_text(action, 80)

def ascii_regime_label(regime):
    s = clean_ascii_text(regime, 50).upper()
    mapping = {
        "UPTREND": "TANG MANH / UPTREND",
        "POSITIVE": "TICH CUC / POSITIVE",
        "SIDEWAY": "DI NGANG / SIDEWAY",
        "WEAK": "YEU / WEAK",
        "DOWNTREND": "GIAM / DOWNTREND",
        "HIGH_VOL_UP": "BIEN DONG CAO - TANG / HIGH VOL UP",
        "HIGH_VOL_DOWN": "BIEN DONG CAO - GIAM / HIGH VOL DOWN",
    }
    return mapping.get(s, s)

def clean_display_na(x):
    return clean_ascii_text(x, 120)

def display_action_ascii(action):
    return ascii_action_label(action)

def display_regime_ascii(regime):
    return ascii_regime_label(regime)
