from v10_config import *

def fix_vietnamese_columns(df):
    """
    Normalize broken Vietnamese column names into ASCII-safe names.
    This avoids mojibake issues like: MÃ£, GiÃ¡, LÃ£i/Lá».
    """
    if df is None or df.empty:
        return df

    rename_map = {
        "MÃÂ£": "Ma",
        "MÃ£": "Ma",
        "Ma": "Ma",

        "NgÃ y": "Ngay",
        "NgÃ y": "Ngay",
        "NgÃ y": "Ngay",
        "Ngay": "Ngay",

        "ChiÃ¡ÂºÂ¿n lÃÂ°Ã¡Â»Â£c": "Chien luoc",
        "Chiáº¿n lÆ°á»£c": "Chien luoc",
        "ChiÃ¡ÂºÂ¿n lÆ°á»£c": "Chien luoc",

        "HÃ nh ÃâÃ¡Â»â¢ng": "Hanh dong",
        "HÃ nh Äá»ng": "Hanh dong",
        "Hanh dong": "Hanh dong",

        "CÃ¡ÂºÂ£nh bÃÂ¡o": "Canh bao",
        "Cáº£nh bÃ¡o": "Canh bao",
        "Canh bao": "Canh bao",

        "LÃÂ½ do": "Ly do",
        "LÃ½ do": "Ly do",
        "Ly do": "Ly do",

        "GiÃÂ¡ vÃ¡Â»ân": "Gia von",
        "GiÃ¡ vá»n": "Gia von",
        "Gia von": "Gia von",

        "SÃ¡Â»â lÃÂ°Ã¡Â»Â£ng": "So luong",
        "Sá» lÆ°á»£ng": "So luong",
        "So luong": "So luong",

        "GiÃÂ¡ trÃ¡Â»â¹ vÃ¡Â»ân": "Gia tri von",
        "GiÃ¡ trá» vá»n": "Gia tri von",
        "Gia tri von": "Gia tri von",

        "GiÃÂ¡ trÃ¡Â»â¹ hiÃ¡Â»â¡n tÃ¡ÂºÂ¡i": "Gia tri hien tai",
        "GiÃ¡ trá» hiá»n táº¡i": "Gia tri hien tai",
        "Gia tri hien tai": "Gia tri hien tai",

        "LÃÂ£i/LÃ¡Â»â %": "Lai/Lo %",
        "LÃ£i/Lá» %": "Lai/Lo %",
        "Lai/Lo %": "Lai/Lo %",

        "LÃÂ£i/LÃ¡Â»â tiÃ¡Â»Ân": "Lai/Lo tien",
        "LÃ£i/Lá» tiá»n": "Lai/Lo tien",
        "Lai/Lo tien": "Lai/Lo tien",
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
    Keep Outcome as text/object so PENDING/WIN/LOSS assignment will not crash.
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
    if "MUA UU TIEN" in s or "PRIORITY" in s:
        return "MUA UU TIEN (PRIORITY BUY)"
    if "MUA THAM DO" in s or "PROBE" in s:
        return "MUA THAM DO (PROBE BUY)"
    if "BUY NOW" in s:
        return "MUA NGAY (BUY NOW)"
    if "CHO XAC NHAN" in s or "WAIT CONFIRM" in s:
        return "CHO XAC NHAN (WAIT CONFIRM)"
    if "CHO PULLBACK" in s or "PULLBACK" in s:
        return "CHO PULLBACK (WAIT PULLBACK)"
    if "THEO DOI MANH" in s or "STRONG WATCH" in s:
        return "THEO DOI MANH (STRONG WATCH)"
    if "THEO DOI" in s or "WATCH" in s or "WATCHLIST" in s:
        return "THEO DOI (WATCH)"
    if "BO QUA" in s or "SKIP" in s:
        return "BO QUA (SKIP)"
    if "WAIT" in s:
        return "CHO (WAIT)"
    return str(action or "")

def vi_regime_label(regime):
    s = str(regime or "").upper()
    mapping = {
        "UPTREND": "TANG MANH (UPTREND)",
        "POSITIVE": "TICH CUC (POSITIVE)",
        "SIDEWAY": "DI NGANG (SIDEWAY)",
        "WEAK": "YEU (WEAK)",
        "DOWNTREND": "GIAM (DOWNTREND)",
        "HIGH_VOL_UP": "BIEN DONG CAO - TANG (HIGH VOL UP)",
        "HIGH_VOL_DOWN": "BIEN DONG CAO - GIAM (HIGH VOL DOWN)",
    }
    return mapping.get(s, str(regime or ""))

def short_note(text_value, limit=90):
    s = str(text_value or "").replace("\n", " ").replace("\r", " ").strip()
    if s.lower() in ["nan", "none", ""]:
        return ""
    return s[:limit]

def now_vietnam():
    return datetime.utcnow() + timedelta(hours=7)

def get_price_data_date(df):
    """
    Get the latest price-data date from dataframe.
    Do not use bot run date because GitHub can run after midnight while market data is older.
    """
    try:
        if df is None or df.empty:
            return now_vietnam().strftime("%Y-%m-%d")

        last = df.iloc[-1]
        for col in ["time", "date", "ngay", "Ngay", "NgÃ y"]:
            if col in df.columns:
                val = last.get(col)
                if pd.notna(val):
                    return str(val)[:10]

        return now_vietnam().strftime("%Y-%m-%d")
    except Exception:
        return now_vietnam().strftime("%Y-%m-%d")

def get_report_data_date(*dfs):
    """
    Get max data date from output files for Telegram/dashboard.
    """
    dates = []
    for df in dfs:
        try:
            date_col = None
            for c in ["Ngay", "NgÃ y", "NgÃ y"]:
                if df is not None and not df.empty and c in df.columns:
                    date_col = c
                    break
            if date_col:
                s = pd.to_datetime(df[date_col], errors="coerce").dropna()
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

    repl = {
        "MUA Æ¯U TIÃN": "PRIORITY BUY",
        "MUA THÄM DÃ": "PROBE BUY",
        "CHá» XÃC NHáº¬N": "WAIT CONFIRM",
        "CHá» PULLBACK": "WAIT PULLBACK",
        "THEO DÃI Máº NH": "STRONG WATCH",
        "THEO DÃI": "WATCH",
        "Bá» QUA": "SKIP",
        "MUA UU TIEN": "PRIORITY BUY",
        "MUA THAM DO": "PROBE BUY",
        "CHO XAC NHAN": "WAIT CONFIRM",
        "THEO DOI MANH": "STRONG WATCH",
        "THEO DOI": "WATCH",
        "BO QUA": "SKIP",
    }
    for k, v in repl.items():
        s = s.replace(k, v)

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


# ===== THÊM 2 HÀM NÀY VÀO CUỐI FILE =====
def runner_normalize_columns(df):
    """Chuẩn hóa tên cột, loại bỏ duplicate, reset index"""
    if df is None:
        return df
    try:
        if df.empty:
            return df

        rename_map = {
            "MÃÂ£": "Ma",
            "MÃ£": "Ma",
            "Mã": "Ma",
            "Ma": "Ma",

            "NgÃ y": "Ngay",
            "NgÃ y": "Ngay",
            "NgÃ y": "Ngay",
            "Ngày": "Ngay",
            "Ngay": "Ngay",

            "ChiÃ¡ÂºÂ¿n lÃÂ°Ã¡Â»Â£c": "Chien luoc",
            "Chiáº¿n lÆ°á»£c": "Chien luoc",
            "Chiến lược": "Chien luoc",
            "Chien luoc": "Chien luoc",

            "HÃ nh Äá»ng": "Hanh dong",
            "Hành động": "Hanh dong",
            "Hanh dong": "Hanh dong",

            "Cáº£nh bÃ¡o": "Canh bao",
            "Cảnh báo": "Canh bao",
            "Canh bao": "Canh bao",

            "LÃ½ do": "Ly do",
            "Lý do": "Ly do",
            "Ly do": "Ly do",

            "GiÃ¡ vá»n": "Gia von",
            "Giá vốn": "Gia von",
            "Gia von": "Gia von",

            "Sá» lÆ°á»£ng": "So luong",
            "Số lượng": "So luong",
            "So luong": "So luong",

            "GiÃ¡ trá» vá»n": "Gia tri von",
            "Giá trị vốn": "Gia tri von",
            "Gia tri von": "Gia tri von",

            "GiÃ¡ trá» hiá»n táº¡i": "Gia tri hien tai",
            "Giá trị hiện tại": "Gia tri hien tai",
            "Gia tri hien tai": "Gia tri hien tai",

            "LÃ£i/Lá» %": "Lai/Lo %",
            "Lãi/Lỗ %": "Lai/Lo %",
            "Lai/Lo %": "Lai/Lo %",

            "LÃ£i/Lá» tiá»n": "Lai/Lo tien",
            "Lãi/Lỗ tiền": "Lai/Lo tien",
            "Lai/Lo tien": "Lai/Lo tien",
        }

        out = df.copy()
        out.columns = [rename_map.get(str(c), str(c).replace("\ufeff", "").strip()) for c in out.columns]
        out = out.loc[:, ~out.columns.duplicated()].reset_index(drop=True)
        return out
    except Exception:
        return df


def runner_safe_concat(frames):
    """Ghép các DataFrame an toàn, chuẩn hóa cột trước khi ghép"""
    clean_frames = []
    for df in frames:
        if df is None:
            continue
        df = runner_normalize_columns(df)
        if df is not None and not df.empty:
            clean_frames.append(df.loc[:, ~df.columns.duplicated()].reset_index(drop=True))

    if not clean_frames:
        return pd.DataFrame()

    return pd.concat(clean_frames, ignore_index=True, sort=False)
