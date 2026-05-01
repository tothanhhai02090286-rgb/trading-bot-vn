import os
import re
import unicodedata
import time
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from pandas.errors import EmptyDataError

from universe import UNIVERSE

API_KEY = os.getenv("VNSTOCK_API_KEY")

SYSTEM_VERSION = "PRO_V12_PRO_FINAL_NO_FONT_ERROR_FIX2_2026_05_01"

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
    VÃ­ dá»¥: MÃÂ£ -> Ma, NgÃ y -> Ngay.
    """
    if df is None or df.empty:
        return df

    rename_map = {
        "MÃÂ£": "Ma",
        "Ma": "Ma",
        "NgÃ y": "Ngay",
        "Ngay": "Ngay",
        "ChiÃ¡ÂºÂ¿n lÃÂ°Ã¡Â»Â£c": "Chien luoc",
        "HÃ nh ÃâÃ¡Â»â¢ng": "HÃ nh Äá»ng",
        "CÃ¡ÂºÂ£nh bÃÂ¡o": "Cáº£nh bÃ¡o",
        "LÃÂ½ do": "Ly do",
        "GiÃÂ¡ vÃ¡Â»ân": "GiÃ¡ vá»n",
        "SÃ¡Â»â lÃÂ°Ã¡Â»Â£ng": "Sá» lÆ°á»£ng",
        "GiÃÂ¡ trÃ¡Â»â¹ vÃ¡Â»ân": "GiÃ¡ trá» vá»n",
        "GiÃÂ¡ trÃ¡Â»â¹ hiÃ¡Â»â¡n tÃ¡ÂºÂ¡i": "GiÃ¡ trá» hien tai",
        "LÃÂ£i/LÃ¡Â»â %": "LÃ£i/Lá» %",
        "LÃÂ£i/LÃ¡Â»â tiÃ¡Â»Ân": "LÃ£i/Lá» tiá»n",
    }

    df = df.copy()
    df.columns = [rename_map.get(str(c), str(c).replace("\ufeff", "").strip()) for c in df.columns]
    return df



# ================================
# FONT SAFE UI HELPERS
# ================================

def vn_no_accent(x):
    """
    Chuyen tieng Viet co dau -> khong dau bang unicodedata.
    Khong dung str.maketrans nen khong bi loi key dai hon 1 ky tu.
    """
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass

    s = str(x)
    try:
        s = fix_mojibake_text(s)
    except Exception:
        pass

    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("Ä", "d").replace("Ä", "D")
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s+", " ", s.replace("\n", " ").replace("\r", " ")).strip()

    if s.lower() in ["nan", "none"]:
        return ""
    return s


def v12_clean(x, limit=160):
    s = vn_no_accent(x)
    return s[:limit]



def v12_action_label(row):
    raw = vn_no_accent(row.get("Final Action", row.get("AI Action", row.get("Action", "")))).upper()
    risk = str(row.get("Risk Status", "")).upper()
    score = safe_float(row.get("Score"), 0)
    ai = safe_float(row.get("AI Confidence"), score)
    rsi = safe_float(row.get("RSI"), 0)

    if risk == "FAIL" or "SKIP" in raw or "BO QUA" in raw:
        return "BO QUA / SKIP"
    if "PRIORITY" in raw or "UU TIEN" in raw or (score >= 90 and ai >= 85 and rsi < 78):
        return "MUA UU TIEN / PRIORITY BUY"
    if "PROBE" in raw or "BUY NOW" in raw or "MUA" in raw:
        return "MUA THAM DO / PROBE BUY"
    if "PULLBACK" in raw:
        return "CHO PULLBACK / WAIT PULLBACK"
    if "WAIT" in raw or "CHO" in raw:
        return "CHO XAC NHAN / WAIT CONFIRM"
    if "WATCH" in raw or "THEO" in raw:
        return "THEO DOI / WATCH"
    return raw[:60] or "THEO DOI / WATCH"



def v12_regime_label(regime):
    s = vn_no_accent(regime).upper()
    if "UPTREND" in s:
        return "TANG MANH / UPTREND"
    if "POSITIVE" in s:
        return "TICH CUC / POSITIVE"
    if "SIDEWAY" in s:
        return "DI NGANG / SIDEWAY"
    if "DOWNTREND" in s:
        return "GIAM / DOWNTREND"
    if "HIGH_VOL_UP" in s:
        return "BIEN DONG CAO - TANG / HIGH VOL UP"
    if "HIGH_VOL_DOWN" in s:
        return "BIEN DONG CAO - GIAM / HIGH VOL DOWN"
    if "WEAK" in s:
        return "YEU / WEAK"
    return s



def v12_main_reason(row):
    parts = []
    score = safe_float(row.get("Score"), 0)
    ai = safe_float(row.get("AI Confidence"), score)
    rsi = safe_float(row.get("RSI"), 0)
    rs20 = safe_float(row.get("RS20"), 0)
    vol = safe_float(row.get("Volume Ratio"), 0)
    atr = safe_float(row.get("ATR %"), 0)
    risk = str(row.get("Risk Status", "")).upper()
    strategy = str(row.get("Chien luoc", row.get("Strategy", ""))).upper()

    if risk == "FAIL":
        parts.append("Risk FAIL")
    if score >= 85:
        parts.append("diem ky thuat cao")
    elif score >= 70:
        parts.append("diem ky thuat kha")
    else:
        parts.append("diem ky thuat thap")

    if ai >= 85:
        parts.append("AI manh")
    elif ai >= 70:
        parts.append("AI kha")

    if rs20 > 5:
        parts.append("RS20 manh")
    elif rs20 > 0:
        parts.append("RS20 duong")
    elif rs20 <= -8:
        parts.append("RS20 yeu")

    if vol >= 1.5:
        parts.append("volume xac nhan manh")
    elif vol >= 1.1:
        parts.append("volume tot")
    elif vol < 0.8:
        parts.append("volume yeu")

    if rsi >= 78:
        parts.append("RSI nong")
    elif 45 <= rsi <= 72:
        parts.append("RSI hop ly")

    if atr > 8:
        parts.append("ATR cao")
    elif atr <= 5:
        parts.append("bien dong thap")

    if "MOMENTUM" in strategy:
        parts.append("momentum")
    elif "BOTTOM" in strategy:
        parts.append("bat day/hoi phuc")

    return "; ".join(parts[:5])


def v12_buy_zone(row):
    close = safe_float(row.get("Close"), np.nan)
    atr = safe_float(row.get("ATR %"), 0)
    if pd.isna(close) or close <= 0:
        return ""
    band = max(0.8, min(2.5, atr * 0.35))
    return f"{close*(1-band/100):.2f} - {close*(1+band/100):.2f}"


def v12_stop_loss(row):
    close = safe_float(row.get("Close"), np.nan)
    atr = safe_float(row.get("ATR %"), 0)
    if pd.isna(close) or close <= 0:
        return ""
    risk_pct = max(3.0, min(6.0, atr * 0.9))
    return f"{close*(1-risk_pct/100):.2f}"


def v12_position_size(row):
    action = v12_action_label(row)
    trust = v12_trust_label(row)
    risk = str(row.get("Risk Status", "")).upper()
    atr = safe_float(row.get("ATR %"), 0)
    if risk == "FAIL" or "Bá» QUA" in action:
        return "0%"
    if "CAO" in trust and "MUA Æ¯U TIÃN" in action and atr <= 6:
        return "50-70% lá»nh thÆ°á»ng"
    if "MUA Æ¯U TIÃN" in action:
        return "40-60% lá»nh thÆ°á»ng"
    if "MUA THÄM DÃ" in action:
        return "20-35% lá»nh thÆ°á»ng"
    if "CHá»" in action:
        return "0-20%, chá» xÃ¡c nháº­n"
    return "0%, chá» theo dÃµi"


def v12_risk_profile(row):
    strategy = str(row.get("Chien luoc", row.get("Strategy", ""))).upper()
    rsi = safe_float(row.get("RSI"), 0)
    atr = safe_float(row.get("ATR %"), 0)
    rs20 = safe_float(row.get("RS20"), 0)
    if atr > 8:
        return "Rá»¦I RO CAO / HIGH VOL"
    if "MOMENTUM" in strategy and rs20 > 5 and rsi < 75:
        return "XU HÆ¯á»NG KHá»E / SAFE TREND"
    if "MOMENTUM" in strategy and rsi >= 75:
        return "MOMENTUM NÃNG / HOT MOMENTUM"
    if "BOTTOM" in strategy:
        return "Há»I PHá»¤C / MEAN REVERSION"
    return "TRUNG TÃNH / NEUTRAL"


def v12_trust_label(row):
    oos = safe_float(row.get("OOS Win Probability"), np.nan)
    oos_n = safe_float(row.get("OOS Samples"), 0)
    reg = safe_float(row.get("Regime Win Probability"), np.nan)
    reg_n = safe_float(row.get("Regime Samples"), 0)
    if pd.isna(oos) or oos_n < 5:
        return "THAP - chua du OOS"
    if oos >= 60 and oos_n >= 10:
        if not pd.isna(reg) and reg >= 55 and reg_n >= 5:
            return "CAO / HIGH"
        return "KHA CAO / MED-HIGH"
    if oos >= 52 and oos_n >= 5:
        return "TRUNG BINH / MEDIUM"
    if oos < 45 and oos_n >= 5:
        return "THAP - OOS yeu"
    return "THAP VUA / LOW-MED"


def v12_evidence(row):
    oos = safe_float(row.get("OOS Win Probability"), np.nan)
    oos_n = safe_float(row.get("OOS Samples"), 0)
    reg = safe_float(row.get("Regime Win Probability"), np.nan)
    reg_n = safe_float(row.get("Regime Samples"), 0)
    win = safe_float(row.get("Win Probability"), np.nan)
    parts = []
    if not pd.isna(oos) and oos_n > 0:
        parts.append(f"OOS {oos:.0f}% ({int(oos_n)} mau)")
    else:
        parts.append("OOS chua du")
    if not pd.isna(reg) and reg_n > 0:
        parts.append(f"Regime {reg:.0f}% ({int(reg_n)} mau)")
    if not pd.isna(win):
        parts.append(f"History {win:.0f}%")
    return " | ".join(parts)


def v12_expected_return(row):
    p3 = safe_float(row.get("Ret+3D %"), np.nan)
    p5 = safe_float(row.get("OOS Avg Ret+5D %"), np.nan)
    p10 = safe_float(row.get("OOS Avg Ret+10D %"), np.nan)
    score = safe_float(row.get("Score"), 0)
    ai = safe_float(row.get("AI Confidence"), score)
    base = max(0, min(3.0, (score - 60) / 20 + (ai - 60) / 40))
    if pd.isna(p3):
        p3 = round(base * 0.6, 2)
    if pd.isna(p5):
        p5 = round(base * 1.0, 2)
    if pd.isna(p10):
        p10 = round(base * 1.4, 2)
    return f"+3 phien: {p3:.1f}% | +5 phien: {p5:.1f}% | +10 phien: {p10:.1f}%"


def v12_expected_drawdown(row):
    min10 = safe_float(row.get("Min+10D %"), np.nan)
    atr = safe_float(row.get("ATR %"), 0)
    if not pd.isna(min10):
        return f"{min10:.1f}%"
    return f"{-max(3.0, min(7.0, atr * 0.9)):.1f}%"


def v12_add_columns(df):
    if df is None or df.empty:
        return df
    out = df.copy()
    out["Khuyen nghi"] = out.apply(v12_action_label, axis=1)
    out["Ly do chinh"] = out.apply(v12_main_reason, axis=1)
    out["Vung mua"] = out.apply(v12_buy_zone, axis=1)
    out["Cat lo"] = out.apply(v12_stop_loss, axis=1)
    out["Ty trong goi y"] = out.apply(v12_position_size, axis=1)
    out["Ho so rui ro"] = out.apply(v12_risk_profile, axis=1)
    out["Do tin cay"] = out.apply(v12_trust_label, axis=1)
    out["Bang chung AI"] = out.apply(v12_evidence, axis=1)
    out["Du bao LN"] = out.apply(v12_expected_return, axis=1)
    out["Rui ro giam"] = out.apply(v12_expected_drawdown, axis=1)
    return out


def v12_table(df, cols, top=20):
    if df is None or df.empty:
        return pd.DataFrame()
    view = df.copy()
    rename = {
        "AI Confidence": "AI",
        "Win Probability": "Win%",
        "OOS Win Probability": "OOS%",
        "Regime Win Probability": "Regime%",
        "Market Regime Now": "Trang thai TT",
        "Volume Ratio": "Vol Ratio",
        "Risk Status": "Risk",
    }
    view = view.rename(columns={k: v for k, v in rename.items() if k in view.columns})
    if "Trang thai TT" in view.columns:
        view["Trang thai TT"] = view["Trang thai TT"].apply(v12_regime_label)
    selected = [c for c in cols if c in view.columns]
    if selected:
        view = view[selected]
    return view.replace({np.nan: ""}).head(top)


def v12_market_context(combined, market_ret20=0):
    try:
        regime = combined["Market Regime Now"].dropna().iloc[0] if "Market Regime Now" in combined.columns else ""
    except Exception:
        regime = ""
    regime_label = v12_regime_label(regime)
    ret20 = safe_float(market_ret20, 0)
    if "UPTREND" in str(regime).upper() or ret20 > 3:
        risk = "Tich cuc, co the mua tham do"
        cash = "Giu tien mat 30-50%"
    elif "SIDEWAY" in str(regime).upper():
        risk = "Di ngang, tranh mua duoi"
        cash = "Giu tien mat 50-70%"
    elif "DOWN" in str(regime).upper() or ret20 < -3:
        risk = "Rui ro cao, uu tien phong thu"
        cash = "Giu tien mat 70-90%"
    else:
        risk = "Trung tinh"
        cash = "Giu tien mat 50-60%"
    return pd.DataFrame([{
        "Trang thai thi truong": regime_label,
        "VNINDEX Ret20": round(ret20, 2),
        "Nhan dinh": risk,
        "Goi y tien mat": cash
    }])


def v12_ai_summary_table(wf_stats, back_wf_stats, regime_stats, pattern_stats):
    rows = []
    backfill_hist = safe_read_csv(BACKFILL_SIGNAL_HISTORY_PATH) if "BACKFILL_SIGNAL_HISTORY_PATH" in globals() else pd.DataFrame()
    live_hist = safe_read_csv(SIGNAL_HISTORY_PATH) if "SIGNAL_HISTORY_PATH" in globals() else pd.DataFrame()

    def date_range(df):
        if df is None or df.empty or "Ngay" not in df.columns:
            return "", ""
        s = pd.to_datetime(df["Ngay"], errors="coerce").dropna()
        if s.empty:
            return "", ""
        return s.min().strftime("%Y-%m-%d"), s.max().strftime("%Y-%m-%d")

    live_from, live_to = date_range(live_hist)
    back_from, back_to = date_range(backfill_hist)
    if backfill_hist is not None and not backfill_hist.empty and "Train/Test" in backfill_hist.columns:
        test_from, test_to = date_range(backfill_hist[backfill_hist["Train/Test"].astype(str).str.upper() == "TEST"])
    else:
        test_from, test_to = "", ""

    def summarize(name, df, prob_col, logic, data_from="", data_to="", test_from="", test_to="", train_window="", test_window=""):
        if df is None or df.empty or prob_col not in df.columns:
            rows.append({
                "Module": name, "Cach test": logic, "Du lieu tu": data_from, "Du lieu den": data_to,
                "Test tá»«": test_from, "Test Äáº¿n": test_to, "Train": train_window, "Test": test_window,
                "Rows": 0, "Co du lieu": 0, "Win TB%": "", "Pattern manh": 0, "Pattern yeu": 0,
                "Y nghia": "ChÆ°a cÃ³ dá»¯ liá»u"
            })
            return
        d = df.copy()
        d[prob_col] = pd.to_numeric(d[prob_col], errors="coerce")
        valid = d[d[prob_col].notna()]
        avg = valid[prob_col].mean() if not valid.empty else np.nan
        rows.append({
            "Module": name, "Cach test": logic, "Du lieu tu": data_from, "Du lieu den": data_to,
            "Test tá»«": test_from, "Test Äáº¿n": test_to, "Train": train_window, "Test": test_window,
            "Rows": len(d), "Co du lieu": len(valid),
            "Win TB%": round(avg, 1) if not pd.isna(avg) else "",
            "Pattern manh": int((valid[prob_col] >= 60).sum()) if not valid.empty else 0,
            "Pattern yeu": int((valid[prob_col] < 45).sum()) if not valid.empty else 0,
            "Y nghia": "Co the tham khao" if len(valid) else "ChÆ°a Äá»§ mau"
        })

    summarize("Walk-forward live", wf_stats, "OOS Win Probability", "Live: hoc doan truoc, test doan sau", live_from, live_to, live_from, live_to, f"{WF_TRAIN_DAYS} ngay", f"{WF_TEST_DAYS} ngay")
    summarize("Backfill OOS 3M", back_wf_stats, "OOS Win Probability", "Moi block 3 thang: 80% Äáº§u há»c, 20% cuá»i test", back_from, back_to, test_from, test_to, "80% dau block", "20% cuoi block")
    summarize("Pattern history", pattern_stats, "Win Probability", "Thong ke win/loss theo pattern", live_from, live_to, "", "", "history cÃ³ outcome", "-")
    summarize("Regime stats", regime_stats, "Regime Win Probability", "Pattern theo trang thai thi truong, co time-decay", back_from or live_from, back_to or live_to, "", "", f"decay {DECAY_HALFLIFE_DAYS} ngay", "regime hien tai")
    return pd.DataFrame(rows)


def v12_top_patterns(wf_stats, back_wf_stats):
    frames = []
    for source, df in [("LIVE", wf_stats), ("BACKFILL", back_wf_stats)]:
        if df is None or df.empty or "OOS Win Probability" not in df.columns or "OOS Samples" not in df.columns:
            continue
        d = df.copy()
        d["Nguon"] = source
        d["OOS Win Probability"] = pd.to_numeric(d["OOS Win Probability"], errors="coerce")
        d["OOS Samples"] = pd.to_numeric(d["OOS Samples"], errors="coerce").fillna(0)
        frames.append(d)
    if not frames:
        return pd.DataFrame([{"Pattern": "ChÆ°a cÃ³ OOS data", "Do tin cay": "Tháº¥p"}])
    x = pd.concat(frames, ignore_index=True).dropna(subset=["OOS Win Probability"])
    x = x[x["OOS Samples"] >= 5]
    if x.empty:
        return pd.DataFrame([{"Pattern": "CÃ³ OOS nhÆ°ng chÆ°a Äá»§ 5 mau", "Do tin cay": "Tháº¥p"}])
    x["Rank"] = x["OOS Win Probability"] + np.minimum(x["OOS Samples"], 50) * 0.2
    x = x.sort_values("Rank", ascending=False).drop_duplicates("Pattern Key", keep="first").head(15)
    rows = []
    for _, r in x.iterrows():
        rows.append({
            "Pattern": v12_clean(r.get("Pattern Key", ""), 80),
            "Nguon": r.get("Nguon", ""),
            "OOS Win%": round(safe_float(r.get("OOS Win Probability"), np.nan), 1),
            "OOS mau": int(safe_float(r.get("OOS Samples"), 0)),
            "Avg +5D": round(safe_float(r.get("OOS Avg Ret+5D %"), np.nan), 2) if not pd.isna(safe_float(r.get("OOS Avg Ret+5D %"), np.nan)) else "",
            "Avg +10D": round(safe_float(r.get("OOS Avg Ret+10D %"), np.nan), 2) if not pd.isna(safe_float(r.get("OOS Avg Ret+10D %"), np.nan)) else ""
        })
    return pd.DataFrame(rows)

def build_telegram_message(entry, action_plan, combined, tracker):
    run_time = now_vietnam().strftime("%Y-%m-%d %H:%M:%S")
    data_date = get_report_data_date(entry, action_plan, combined)

    source_df = entry.copy() if entry is not None and not entry.empty else pd.DataFrame()
    if source_df.empty and action_plan is not None and not action_plan.empty:
        source_df = action_plan.copy()
    if source_df.empty and combined is not None and not combined.empty:
        source_df = combined.copy()

    try:
        total_codes = len(set(combined["Ma"].dropna().astype(str)) & set(UNIVERSE))
    except Exception:
        total_codes = 0

    try:
        current_regime = str(combined["Market Regime Now"].dropna().iloc[0]) if "Market Regime Now" in combined.columns else ""
    except Exception:
        current_regime = ""

    lines = [
        "BAO CAO GIAO DICH V12 PRO FINAL",
        f"Thoi gian chay: {run_time}",
        f"Ngay dá»¯ liá»u: {data_date}",
        f"Phien ban: {SYSTEM_VERSION}",
    ]
    if current_regime:
        lines.append(f"Trang thai thi truong: {v12_regime_label(current_regime)}")
    lines.append(f"Coverage: {total_codes}/{len(UNIVERSE)} mÃ£")
    lines.append("")
    lines.append("Ghi chu: OOS = kiem dinh ngoai mau, pháº§n test khÃ´ng dÃ¹ng Äá» há»c.")

    if source_df is None or source_df.empty:
        lines.append("KhÃ´ng cÃ³ tÃ­n hiá»u hÃ´m nay.")
        return "\n".join(lines)

    source_df = safe_numeric_columns(source_df)
    sort_cols = [c for c in ["Regime Win Probability", "OOS Win Probability", "Win Probability", "AI Confidence", "Score"] if c in source_df.columns]
    if sort_cols:
        source_df = source_df.sort_values(sort_cols, ascending=False)
    elif "Score" in source_df.columns:
        source_df = source_df.sort_values("Score", ascending=False)

    lines.append("")
    lines.append("KHUYEN NGHI CHI TIET:")

    for _, r in source_df.head(7).iterrows():
        code = str(r.get("Ma", r.get("Ma", ""))).strip()
        lines.append("")
        lines.append(f"{code} | {v12_action_label(r)}")
        lines.append(f"- Ly do: {v12_main_reason(r)}")
        lines.append(f"- Vung mua: {v12_buy_zone(r)} | Cat lo: {v12_stop_loss(r)} | Ty trong: {v12_position_size(r)}")
        lines.append(f"- AI/Trust: AI {safe_float(r.get('AI Confidence'), safe_float(r.get('Score'), 0)):.0f} | {v12_trust_label(r)}")
        lines.append(f"- Bang chung: {v12_evidence(r)}")
        lines.append(f"- Du bao: {v12_expected_return(r)} | Rui ro giam: {v12_expected_drawdown(r)}")

    lines.append("")
    lines.append("File dashboard.html da gui kem de xem day du 8 phan.")
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
            caption="Dashboard HTML - mo file de xem chi tiet"
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
    font-size: 13px;
}
th {
    background-color: #1f2430;
    color: #ffffff;
    padding: 6px;
    border: 1px solid #333;
}
td {
    padding: 6px;
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
    Táº¡o láº¡i tÃ­n hiá»u quÃ¡ khá»© báº±ng chÃ­nh logic hien tai.
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
    r["Chien luoc"] = classify_strategy(r)

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
    Thong ke hiá»u quáº£ pattern theo regime, co time-decay.
    """
    if hist is None or hist.empty:
        return pd.DataFrame()

    h = hist.copy()
    h = normalize_outcome_dtype(h)
    if "Pattern Key" not in h.columns or "Market Regime" not in h.columns:
        return pd.DataFrame()

    h["Ngay"] = pd.to_datetime(h["Ngay"], errors="coerce")
    h = h.dropna(subset=["Ngay", "Pattern Key", "Market Regime"])
    h["Outcome"] = h.get("Outcome", "PENDING").astype(str)
    h = h[~h["Outcome"].isin(["PENDING", "", "nan"])].copy()

    if h.empty:
        return pd.DataFrame()

    h["Win Flag"] = h["Outcome"].isin(["WIN", "WIN_TP"]).astype(int)
    h["Decay Weight"] = h["Ngay"].apply(compute_recent_decay_weight)

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
    Final filter V9: Äiá»u chá»nh Final Action theo regime hien tai + time-decay stats.
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
        note = f"{current_regime}: {n} mau, win decay ~{p:.1f}%"

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
            note += " | Ã­t mau regime, khÃ´ng nÃ¢ng máº¡nh"
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
    - TEST ÄÆ°á»£c dÃ¹ng Äá» ÄÃ¡nh giÃ¡ ngoÃ i mau, trÃ¡nh há»c váº¹t.
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

    print(f"ð§  Backfill V7: {start_idx} -> {end_idx} / {len(UNIVERSE)}")

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
                "Ngay": d.strftime("%Y-%m-%d"),
                "Ma": symbol,
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

    if not hist.empty and "Ngay" in hist.columns and "Ma" in hist.columns:
        hist = hist.drop_duplicates(subset=["Ngay", "Ma", "Pattern Key"], keep="last")
        hist = hist.sort_values(["Ngay", "Ma"])

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

print(f"ð Batch: {start_idx} -> {end_idx} / {len(UNIVERSE)}")
print("ð Ma:", batch)

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

if not old_df.empty and "Ma" in old_df.columns:
    old_df = old_df[~old_df["Ma"].isin(batch)]
    combined = pd.concat([old_df, new_df], ignore_index=True)
else:
    combined = new_df.copy()

if combined.empty:
    combined = pd.DataFrame([{
        "Ngay": now_vietnam().strftime("%Y-%m-%d"),
        "Ma": "NO_SIGNAL",
        "Close": np.nan,
        "Signal": "NO SIGNAL",
        "Chien luoc": "SYSTEM",
        "Score": 0,
        "Action": "WAIT",
        "Risk Status": "SYSTEM",
        "Risk Reason": "",
        "Updated": now_vietnam().strftime("%Y-%m-%d %H:%M:%S"),
        "Version": SYSTEM_VERSION
    }])

needed_cols = ["Risk Status", "Action", "Chien luoc", "Score", "Ma"]
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
    valid_codes = set(combined["Ma"].dropna().astype(str)) & set(UNIVERSE)
    missing_codes = sorted(set(UNIVERSE) - valid_codes)
    print(f"Coverage: {len(valid_codes)} / {len(UNIVERSE)} mÃ£")
    if missing_codes:
        print("Thiáº¿u mÃ£:", missing_codes)
    else:
        print("â Äá»§ mÃ£ trong all_signal_results.csv")
except Exception as e:
    print("â ï¸ KhÃ´ng kiá»m tra ÄÆ°á»£c coverage:", repr(e))

raw_signals = combined[
    combined["Chien luoc"].isin([
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
    ai_risk["Chien luoc"].isin(["BOTTOM", "BOTTOM_WATCH"])
].copy()
momentum = ai_risk[
    ai_risk["Chien luoc"].isin(["MOMENTUM", "MOMENTUM_WATCH"])
].copy()

bottom.to_csv(BOTTOM_PATH, index=False, encoding="utf-8-sig")
momentum.to_csv(MOMENTUM_PATH, index=False, encoding="utf-8-sig")

entry = ai_risk[
    ai_risk["Action"].isin(["BUY NOW", "WAIT", "WATCHLIST"])
].copy()
entry = entry.sort_values("AI Confidence" if "AI Confidence" in entry.columns else "Score", ascending=False).head(10)

if entry.empty:
    entry = pd.DataFrame([{
        "Ngay": now_vietnam().strftime("%Y-%m-%d"),
        "Ma": "NO_SIGNAL",
        "Action": "WAIT",
        "Chien luoc": "SYSTEM",
        "Score": 0,
        "Risk Reason": "KhÃ´ng cÃ³ tÃ­n hiá»u Äáº¡t chuáº©n"
    }])
else:
    keep = [
        "Ngay", "Ma", "Action", "Signal", "Chien luoc", "Score",
        "Momentum Score", "Bottom Score", "AI Confidence", "AI Grade", "AI Action", "Win Probability", "History Samples", "OOS Win Probability", "OOS Samples", "OOS Status", "Regime Win Probability", "Regime Samples", "Market Regime Now", "Final Action", "History Note", "Walk Forward Note", "Regime Note", "AI Reason", "AI Warning", "Risk Status", "Risk Reason",
        "RSI", "Close", "MA5", "MA20", "Ret5 %", "Ret10 %",
        "RS20", "Volume Ratio", "ADX", "ATR %", "Dist MA20 %"
    ]
    entry = entry[[c for c in keep if c in entry.columns]]

entry.to_csv(ENTRY_PATH, index=False, encoding="utf-8-sig")

tracker, action_plan = build_portfolio_and_action_plan(combined, ai_risk)


wf_stats_disp, back_wf_stats_disp, regime_stats_disp, pattern_stats_disp = load_ai_evidence_tables()
ai_summary_view = v12_ai_summary_table(wf_stats_disp, back_wf_stats_disp, regime_stats_disp, pattern_stats_disp)
top_patterns_view = v12_top_patterns(wf_stats_disp, back_wf_stats_disp)

decision_df = v12_add_columns(ai_risk if ai_risk is not None and not ai_risk.empty else entry)
decision_cols = ["Ngay", "Ma", "Khuyen nghi", "Ly do chinh", "Vung mua", "Cat lo", "Ty trong goi y", "Ho so rui ro", "Score", "AI Confidence", "RSI", "RS20", "Volume Ratio", "ATR %"]
decision_view = v12_table(decision_df, decision_cols, top=20)

explain_cols = ["Ngay", "Ma", "Khuyen nghi", "Do tin cay", "Bang chung AI", "Ly do chinh", "Score", "AI Confidence", "Win Probability", "OOS Win Probability", "Regime Win Probability", "Market Regime Now"]
explain_view = v12_table(decision_df, explain_cols, top=20)

market_view = v12_market_context(combined, market_ret20)

risk_cols = ["Ngay", "Ma", "Khuyen nghi", "Ho so rui ro", "Cat lo", "Ty trong goi y", "ATR %", "RSI", "Risk Status"]
risk_view = v12_table(decision_df, risk_cols, top=20)

portfolio_view = tracker.head(20).replace({np.nan: ""}) if tracker is not None and not tracker.empty else pd.DataFrame([{"Thong tin": "Chua co portfolio_current.csv hoac chua co danh muc"}])

forecast_cols = ["Ngay", "Ma", "Khuyen nghi", "Du bao LN", "Rui ro giam", "Bang chung AI", "Do tin cay"]
forecast_view = v12_table(decision_df, forecast_cols, top=20)

telegram_summary_view = pd.DataFrame([{
    "Noi dung": "Telegram gui nhan dinh chi tiet tung ma: khuyen nghi, ly do, vung mua, cat lo, ty trong, bang chung AI, du bao +3/+5/+10 phien."
}])

decision_html = decision_view.to_html(index=False, escape=True)
explain_html = explain_view.to_html(index=False, escape=True)
test_html = ai_summary_view.to_html(index=False, escape=True)
patterns_html = top_patterns_view.to_html(index=False, escape=True)
market_html = market_view.to_html(index=False, escape=True)
risk_html = risk_view.to_html(index=False, escape=True)
portfolio_html = portfolio_view.to_html(index=False, escape=True)
forecast_html = forecast_view.to_html(index=False, escape=True)
telegram_html = telegram_summary_view.to_html(index=False, escape=True)

html_full = f"""
<html>
<head>
<meta charset="utf-8">
<title>V12 Pro Trading Dashboard</title>
{html_style()}
<style>
.section-note {{ background:#151a24; border:1px solid #30384a; padding:12px; margin:12px 0 20px 0; line-height:1.55; }}
table {{ font-size:13px; }}
th, td {{ white-space:normal; vertical-align:top; }}
</style>
</head>
<body>

<h2>TRUNG TAM RA QUYET DINH GIAO DICH V12 PRO</h2>
<p><b>Thoi gian chay:</b> {now_vietnam()}</p>
<p><b>Ngay dá»¯ liá»u:</b> {get_report_data_date(combined, entry, action_plan)}</p>
<p><b>Phien ban:</b> {SYSTEM_VERSION}</p>
<p><b>Batch:</b> {start_idx} -> {end_idx} / {len(UNIVERSE)}</p>

<div class="section-note">
<b>Ghi chu doc nhanh:</b><br>
- <b>OOS</b> = kiem dinh ngoai mau, tuc phan test khong duoc dung de hoc.<br>
- <b>Trust</b> = do tin cay dua tren OOS, so mau va regime.<br>
- <b>Vung mua / Cat lo</b> la vung tham khao theo ATR va gia hien tai.
</div>

<h3>1. BANG RA QUYET DINH</h3>
<div class="section-note">Mo phan nay dau tien de biet hom nay uu tien ma nao, mua vung nao, cat lo o dau.</div>
{decision_html}

<h3>2. GIAI THICH AI</h3>
<div class="section-note">Cho biet vi sao AI chon/ha ma: do tin cay, bang chung OOS, regime va ly do chinh.</div>
{explain_html}

<h3>3. KIEM DINH AI</h3>
<div class="section-note">Backfill OOS 3M: má»i block 3 thÃ¡ng, 80% dau dung de hoc, 20% cuoi dung de test gia lap nhu chua biet ket qua.</div>
{test_html}

<h3>3B. TOP PATTERN DA KIEM DINH</h3>
{patterns_html}

<h3>4. BOI CANH THI TRUONG</h3>
{market_html}

<h3>5. QUAN TRI RUI RO</h3>
{risk_html}

<h3>6. THEO DOI DANH MUC</h3>
{portfolio_html}

<h3>7. DU BAO LOI NHUAN KY VONG</h3>
<div class="section-note">Du bao +3/+5/+10 phien dua tren pattern, OOS neu co; neu chua co OOS thi dung uoc luong bao thu tu Score va AI.</div>
{forecast_html}

<h3>8. BAO CAO TELEGRAM / TOM TAT HOM NAY</h3>
{telegram_html}

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
