from v10_config import *
from v10_utils import *
from v10_learning import ai_trust_label, build_row_evidence, add_explainable_columns

# ============================================================
# Output safety helpers
# - Normalize column names to ASCII
# - Drop duplicated columns/index to avoid pandas InvalidIndexError
# ============================================================
def normalize_output_columns(df):
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

def safe_concat_frames(frames):
    clean_frames = []
    for df in frames:
        if df is None:
            continue
        df = normalize_output_columns(df)
        if df is not None and not df.empty:
            clean_frames.append(df.loc[:, ~df.columns.duplicated()].reset_index(drop=True))
    if not clean_frames:
        return pd.DataFrame()
    return pd.concat(clean_frames, ignore_index=True, sort=False)


def build_portfolio_and_action_plan(combined, ai_risk):
    combined = normalize_output_columns(combined)
    ai_risk = normalize_output_columns(ai_risk)
    if combined is not None and not combined.empty and "Ma" in combined.columns:
        combined = combined.drop_duplicates(subset=["Ma"], keep="last").reset_index(drop=True)
    portfolio = normalize_output_columns(safe_read_csv(PORTFOLIO_PATH))

    if portfolio is not None and not portfolio.empty and "Ma" in portfolio.columns:
        tracker = portfolio.merge(
            combined,
            on="Ma",
            how="left",
            suffixes=("", "_signal")
        )

        tracker["Gia von"] = pd.to_numeric(tracker.get("Gia von"), errors="coerce")
        tracker["So luong"] = pd.to_numeric(tracker.get("So luong"), errors="coerce")
        tracker["Close"] = pd.to_numeric(tracker.get("Close"), errors="coerce")

        tracker["Gia tri von"] = tracker["Gia von"] * tracker["So luong"]
        tracker["Gia tri hien tai"] = tracker["Close"] * tracker["So luong"]
        tracker["Lai/Lo %"] = (tracker["Close"] / tracker["Gia von"] - 1) * 100
        tracker["Lai/Lo tien"] = tracker["Gia tri hien tai"] - tracker["Gia tri von"]

        def holding_action(row):
            pnl = safe_float(row.get("Lai/Lo %"), 0)
            action = str(row.get("Action", ""))
            risk = str(row.get("Risk Status", ""))
            rsi = safe_float(row.get("RSI"), 0)
            strategy = str(row.get("Chien luoc", ""))

            if pd.isna(row.get("Close")):
                return "CHUA CO DATA"
            if risk == "FAIL":
                return "GIAM / BAN"
            if pnl <= -5:
                return "CAT LO"
            if pnl >= 10 and rsi >= 75:
                return "CHOT LOI MOT PHAN"
            if pnl >= 7:
                return "GIU / CANH CHOT"
            if action == "BUY NOW":
                return "GIU MANH"
            if strategy in ["MOMENTUM", "BOTTOM", "MOMENTUM_WATCH", "BOTTOM_WATCH"]:
                return "GIU"
            return "THEO DOI"

        tracker["Hanh dong"] = tracker.apply(holding_action, axis=1)

        def risk_flag(row):
            pnl = safe_float(row.get("Lai/Lo %"), 0)
            rsi = safe_float(row.get("RSI"), 0)
            risk = str(row.get("Risk Status", ""))

            if risk == "FAIL":
                return "â RISK FAIL"
            if pnl <= -4:
                return "RISK HIGH"
            if pnl <= -2:
                return "WARNING"
            if rsi >= 80:
                return "OVERBOUGHT"
            if pnl > 0:
                return "PROFIT"
            return "OK"

        tracker["Canh bao"] = tracker.apply(risk_flag, axis=1)

        keep_tracker = [
            "Ma", "Gia von", "Close", "So luong",
            "Gia tri von", "Gia tri hien tai",
            "Lai/Lo %", "Lai/Lo tien",
            "Signal", "Chien luoc", "Score", "RSI",
            "Risk Status", "Risk Reason", "Action",
            "Hanh dong", "Canh bao"
        ]
        tracker = tracker[[c for c in keep_tracker if c in tracker.columns]]

    else:
        tracker = pd.DataFrame([{
            "Ma": "NO_PORTFOLIO",
            "Hanh dong": "ChÆ°a cÃ³ portfolio_current.csv",
            "Canh bao": "â ï¸ CHÆ¯A CÃ DANH Má»¤C"
        }])

    tracker.to_csv(PORTFOLIO_TRACKER_PATH, index=False, encoding="utf-8-sig")

    buy_plan = ai_risk[ai_risk["Action"] == "BUY NOW"].copy()

    if not buy_plan.empty:
        buy_plan["Hanh dong"] = "MUA MOI"
        buy_plan["Ly do"] = buy_plan["Signal"].astype(str) + " | Score " + buy_plan["Score"].astype(str)
        keep_buy = [
            "Ngay", "Ma", "Hanh dong", "Ly do",
            "Signal", "Chien luoc", "Score", "AI Confidence", "AI Grade", "AI Action", "Win Probability", "History Samples", "OOS Win Probability", "OOS Samples", "OOS Status", "Regime Win Probability", "Regime Samples", "Market Regime Now", "Final Action", "History Note", "Walk Forward Note", "Regime Note", "AI Reason", "AI Warning",
            "RSI", "Close", "RS20", "Volume Ratio",
            "ADX", "ATR %", "Risk Status"
        ]
        buy_plan = buy_plan[[c for c in keep_buy if c in buy_plan.columns]]
    else:
        buy_plan = pd.DataFrame()

    hold_plan = tracker.copy()

    if not hold_plan.empty and "Ma" in hold_plan.columns:
        hold_plan["Ngay"] = now_vietnam().strftime("%Y-%m-%d")
        hold_plan["Ly do"] = "Theo doi danh muc hien co"

        keep_hold = [
            "Ngay", "Ma", "Hanh dong", "Canh bao", "Ly do",
            "Lai/Lo %", "Lai/Lo tien",
            "Signal", "Chien luoc", "Score", "AI Confidence", "AI Grade", "AI Action", "Win Probability", "History Samples", "OOS Win Probability", "OOS Samples", "OOS Status", "Regime Win Probability", "Regime Samples", "Market Regime Now", "Final Action", "History Note", "Walk Forward Note", "Regime Note", "AI Reason", "AI Warning",
            "RSI", "Close", "Risk Status", "Risk Reason"
        ]
        hold_plan = hold_plan[[c for c in keep_hold if c in hold_plan.columns]]
    else:
        hold_plan = pd.DataFrame()

    action_plan = safe_concat_frames([buy_plan, hold_plan])

    if action_plan.empty:
        action_plan = pd.DataFrame([{
            "Ngay": now_vietnam().strftime("%Y-%m-%d"),
            "Ma": "NO_ACTION",
            "Hanh dong": "KHONG LAM GI",
            "Ly do": "Khong co tin hieu mua va chua co danh muc"
        }])

    action_plan.to_csv(ACTION_PLAN_PATH, index=False, encoding="utf-8-sig")

    return tracker, action_plan

def build_simple_recommendation(row):
    action = display_action_ascii(row.get("Final Action", row.get("AI Action", row.get("Action", ""))))
    score = safe_float(row.get("Score"), 0)
    ai = safe_float(row.get("AI Confidence"), score)
    rsi = safe_float(row.get("RSI"), 0)
    risk = str(row.get("Risk Status", "")).upper()

    trust = ai_trust_label(
        row.get("OOS Win Probability"),
        row.get("OOS Samples"),
        row.get("Regime Win Probability"),
        row.get("Regime Samples")
    )

    if risk == "FAIL":
        return "BO QUA / SKIP"

    # ANTI OVERFIT:
    # Trust LOW must never become PRIORITY BUY.
    if str(trust).startswith("LOW"):
        if score >= 85 and ai >= 80:
            return "MUA THAM DO / PROBE BUY"
        return "THEO DOI / WATCH"

    if "PRIORITY BUY" in action or (score >= 90 and ai >= 85 and rsi < 75):
        return "MUA UU TIEN / PRIORITY BUY"

    if "PROBE BUY" in action or "BUY NOW" in action:
        return "MUA THAM DO / PROBE BUY"

    if "PULLBACK" in action:
        return "CHO PULLBACK / WAIT PULLBACK"

    if "WAIT" in action:
        return "CHO XAC NHAN / WAIT CONFIRM"

    if "WATCH" in action:
        return "THEO DOI / WATCH"

    return action or "THEO DOI / WATCH"

def build_simple_reason(row):
    parts = []
    score = safe_float(row.get("Score"), 0)
    ai = safe_float(row.get("AI Confidence"), score)
    rsi = safe_float(row.get("RSI"), 0)
    rs20 = safe_float(row.get("RS20"), 0)
    vol = safe_float(row.get("Volume Ratio"), 0)
    atr = safe_float(row.get("ATR %"), 0)
    risk = str(row.get("Risk Status", "")).upper()
    strategy = str(row.get("Strategy", row.get("Chien luoc", ""))).upper()

    if risk == "FAIL":
        parts.append("Risk FAIL")
    if score >= 85:
        parts.append("Score cao")
    elif score >= 70:
        parts.append("Score kha")
    else:
        parts.append("Score thap")

    if ai >= 85:
        parts.append("AI manh")
    elif ai >= 70:
        parts.append("AI kha")

    if rs20 > 0:
        parts.append("RS20 tot")
    elif rs20 <= -8:
        parts.append("RS20 yeu")

    if vol >= 1.2:
        parts.append("Volume tot")
    elif vol < 0.8:
        parts.append("Volume yeu")

    if rsi >= 75:
        parts.append("RSI nong")
    elif 45 <= rsi <= 70:
        parts.append("RSI on")

    if atr > 8:
        parts.append("ATR cao")

    if "MOMENTUM" in strategy:
        parts.append("Momentum")
    elif "BOTTOM" in strategy:
        parts.append("Bottom")

    return "; ".join(parts[:5])

def build_buy_zone(row):
    close = safe_float(row.get("Close"), np.nan)
    atr = safe_float(row.get("ATR %"), 0)
    if pd.isna(close) or close <= 0:
        return ""
    # simple zone: +/- 0.5 ATR percent from close, capped for readability
    band = max(0.8, min(2.5, atr * 0.35))
    low = close * (1 - band/100)
    high = close * (1 + band/100)
    return f"{low:.2f}-{high:.2f}"

def build_stop_loss(row):
    close = safe_float(row.get("Close"), np.nan)
    atr = safe_float(row.get("ATR %"), 0)
    if pd.isna(close) or close <= 0:
        return ""
    risk_pct = max(3.0, min(6.0, atr * 0.9))
    sl = close * (1 - risk_pct/100)
    return f"{sl:.2f}"

def make_dashboard_view(df, kind=""):
    """
    Actionable dashboard for phone:
    - hide useless empty OOS/regime columns when not available
    - add Rec / Why / Buy Zone / SL
    """
    if df is None or df.empty:
        return pd.DataFrame()

    df = normalize_output_columns(df)
    view = df.copy()

    rename = {
        "Ngay": "Date",
        "Ma": "Code",
        "Chien luoc": "Strategy",
        "AI Confidence": "AI",
        "Win Probability": "Win%",
        "OOS Win Probability": "OOS%",
        "Regime Win Probability": "Reg%",
        "Market Regime Now": "Regime",
        "Final Action": "Final Action",
        "History Samples": "HistN",
        "OOS Samples": "OOSN",
        "Regime Samples": "RegN",
    }
    view = view.rename(columns={k: v for k, v in rename.items() if k in view.columns})

    for col in ["Action", "Final Action", "AI Action"]:
        if col in view.columns:
            view[col] = view[col].apply(display_action_ascii)

    if "Regime" in view.columns:
        view["Regime"] = view["Regime"].apply(display_regime_ascii)

    if "Strategy" in view.columns:
        view["Strategy"] = view["Strategy"].astype(str).str.encode("ascii", "ignore").str.decode("ascii")

    if "Risk Status" in view.columns:
        view["Risk Status"] = view["Risk Status"].astype(str).str.encode("ascii", "ignore").str.decode("ascii")

    # Actionable columns
    view = add_explainable_columns(view)
    view["Rec"] = view.apply(build_simple_recommendation, axis=1)
    view["Why"] = view.apply(build_simple_reason, axis=1)
    view["Buy Zone"] = view.apply(build_buy_zone, axis=1)
    view["Stop Loss"] = view.apply(build_stop_loss, axis=1)

    # Do not show long/broken notes
    drop_cols = [
        "Risk Reason", "AI Reason", "AI Warning", "History Note",
        "WF Note", "Walk Forward Note", "Regime Note", "Pattern Key",
        "Signal", "AI Action", "Final Action"
    ]
    view = view.drop(columns=[c for c in drop_cols if c in view.columns], errors="ignore")

    # Hide OOS/Reg columns if all empty/zero
    for col in ["OOS%", "OOSN", "OOS Status", "Reg%", "RegN", "HistN"]:
        if col in view.columns:
            s = view[col]
            try:
                numeric = pd.to_numeric(s, errors="coerce").fillna(0)
                if numeric.sum() == 0:
                    view = view.drop(columns=[col])
            except Exception:
                if s.astype(str).replace(["", "nan", "NaN", "NO_WF_DATA"], "").eq("").all():
                    view = view.drop(columns=[col])

    preferred = [
        "Date", "Code", "Close", "Rec", "Trust", "Evidence", "Why", "Buy Zone", "Stop Loss",
        "Strategy", "Score", "AI", "AI Grade", "Win%", "OOS%", "Reg%",
        "Regime", "RSI", "RS20", "Volume Ratio", "ATR %",
        "Risk Status", "HistN", "OOSN", "OOS Status", "RegN"
    ]
    cols = [c for c in preferred if c in view.columns]
    if cols:
        view = view[cols]

    view = view.replace({np.nan: ""})
    return view.head(20)

def build_telegram_message(entry, action_plan, combined, tracker):
    entry = normalize_output_columns(entry)
    action_plan = normalize_output_columns(action_plan)
    combined = normalize_output_columns(combined)
    tracker = normalize_output_columns(tracker)
    run_time = now_vietnam().strftime("%Y-%m-%d %H:%M:%S")
    data_date = get_report_data_date(entry, action_plan, combined)

    try:
        total_codes = len(set(combined["Ma"].dropna().astype(str)) & set(UNIVERSE))
        missing_codes = sorted(set(UNIVERSE) - set(combined["Ma"].dropna().astype(str)))
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
            "TRADING BOT V9 ACTIONABLE\n"
            f"Run time: {run_time}\n"
            f"Data date: {data_date}\n"
            "No signal data.\n"
            "Dashboard HTML attached."
        )

    source_df = safe_numeric_columns(source_df)

    try:
        current_regime = str(combined.get("Market Regime Now").dropna().iloc[0]) if "Market Regime Now" in combined.columns else ""
    except Exception:
        current_regime = ""

    action_col = "Final Action" if "Final Action" in source_df.columns else "AI Action" if "AI Action" in source_df.columns else "Action" if "Action" in source_df.columns else None

    def count_action_contains(words):
        if not action_col:
            return 0
        s = source_df[action_col].astype(str).str.upper()
        mask = False
        for w in words:
            mask = mask | s.str.contains(w.upper(), na=False)
        return int(mask.sum())

    buy_count = count_action_contains(["BUY", "MUA"])
    wait_count = count_action_contains(["WAIT", "CHO", "CH"])
    watch_count = count_action_contains(["WATCH", "THEO"])
    skip_count = count_action_contains(["SKIP", "BO QUA"])

    focus = source_df.copy()
    sort_cols = [c for c in ["Regime Win Probability", "OOS Win Probability", "Win Probability", "AI Confidence", "Score"] if c in focus.columns]
    if sort_cols:
        focus = focus.sort_values(sort_cols, ascending=False)
    elif "Score" in focus.columns:
        focus = focus.sort_values("Score", ascending=False)
    focus = focus.head(5)

    lines = [
        "TRADING BOT V9 ACTIONABLE",
        f"Run time: {run_time}",
        f"Data date: {data_date}",
        f"Version: {SYSTEM_VERSION}",
    ]

    if current_regime:
        lines.append(f"Market regime: {display_regime_ascii(current_regime)}")

    lines.append(f"Coverage: {total_codes}/{len(UNIVERSE)} codes")
    if missing_codes:
        lines.append(f"Missing: {len(missing_codes)} codes")
        lines.append("First missing: " + ", ".join(missing_codes[:10]))

    lines.append("")
    lines.append(f"Buy: {buy_count} | Wait: {wait_count} | Watch: {watch_count} | Skip: {skip_count}")
    if tracker is not None and not tracker.empty:
        lines.append(f"Portfolio rows: {len(tracker)}")

    lines.append("")
    lines.append("TOP RECOMMENDATIONS:")

    def fnum(row, col, digits=0):
        try:
            v = row.get(col)
            if pd.isna(v):
                return ""
            return f"{float(v):.{digits}f}"
        except Exception:
            return ""

    for _, r in focus.iterrows():
        code = clean_display_na(r.get("Ma", ""))
        rec = build_simple_recommendation(r)
        why = build_simple_reason(r)
        zone = build_buy_zone(r)
        sl = build_stop_loss(r)

        ai = fnum(r, "AI Confidence", 0)
        win = fnum(r, "Win Probability", 0)
        oos = fnum(r, "OOS Win Probability", 0)
        reg = fnum(r, "Regime Win Probability", 0)
        score = fnum(r, "Score", 0)
        close = fnum(r, "Close", 2)
        rsi = fnum(r, "RSI", 0)
        rs20 = fnum(r, "RS20", 1)

        trust = ai_trust_label(r.get("OOS Win Probability"), r.get("OOS Samples"), r.get("Regime Win Probability"), r.get("Regime Samples"))
        evidence = build_row_evidence(r)

        lines.append(f"- {code} | {rec} | Trust: {trust}")
        lines.append(f"  Evidence: {evidence}")
        detail = []
        if score:
            detail.append(f"Score {score}")
        if ai:
            detail.append(f"AI {ai}")
        if win:
            detail.append(f"Win {win}%")
        if oos and oos != "nan":
            detail.append(f"OOS {oos}%")
        if reg and reg != "nan":
            detail.append(f"Reg {reg}%")
        if detail:
            lines.append("  " + " | ".join(detail))

        lines.append(f"  Price {close} | RSI {rsi} | RS20 {rs20}")
        if zone:
            lines.append(f"  Buy zone: {zone} | SL: {sl}")
        if why:
            lines.append(f"  Why: {why}")

    lines.append("")
    lines.append("Dashboard HTML attached below.")
    return "\n".join(lines)

def send_telegram_document(token, chat_id, file_path, caption=""):
    if not os.path.exists(file_path):
        print(f"Khong thay file dinh kem: {file_path}")
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
            print("Telegram dashboard file sent")
        else:
            print(f"Telegram dashboard send failed: {r.status_code} - {r.text}")

    except Exception as e:
        print("Telegram dashboard error:", repr(e))

def send_telegram_alert(entry, action_plan, combined, tracker):
    if not TELEGRAM_ENABLED:
        print("Telegram alert disabled")
        return

    token = get_env_secret("TELEGRAM_TOKEN", "TELEGRAM_BOT_TOKEN", "BOT_TOKEN")
    chat_id = get_env_secret("TELEGRAM_CHAT_ID", "CHAT_ID", "TELEGRAM_CHAT")

    if not token or not chat_id:
        print("Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID, skip Telegram")
        return

    msg = build_telegram_message(entry, action_plan, combined, tracker)

    try:
        # 1) Send short summary message
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
            print("Telegram alert sent")
        else:
            print(f"Telegram send failed: {r.status_code} - {r.text}")

        # 2) Send dashboard HTML file
        send_telegram_document(
            token,
            chat_id,
            DASHBOARD_PATH,
            caption="Dashboard HTML - open file to view details"
        )

    except Exception as e:
        print("Telegram error:", repr(e))

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

# ============================================================
# PRO MAX: Proven Pattern T+2 / T+5 helpers
# ============================================================

def _pm_find_col(df, candidates):
    if df is None or df.empty:
        return None
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _pm_prepare_pattern_table(pattern_df):
    if pattern_df is None or pattern_df.empty:
        return pd.DataFrame(), None, None, None

    pat = pattern_df.copy()

    pattern_col = _pm_find_col(pat, ["Pattern", "Pattern Key"])
    if pattern_col is None:
        return pd.DataFrame(), None, None, None

    oos_pct_col = _pm_find_col(pat, ["OOS%", "OOS Win Probability", "OOS Win Rate"])
    oos_n_col = _pm_find_col(pat, ["OOSN", "OOS N", "OOS Samples"])

    if oos_pct_col is None:
        return pd.DataFrame(), None, None, None

    if oos_n_col is None:
        pat["OOSN"] = 0
        oos_n_col = "OOSN"

    pat[oos_pct_col] = pd.to_numeric(pat[oos_pct_col], errors="coerce")
    pat[oos_n_col] = pd.to_numeric(pat[oos_n_col], errors="coerce").fillna(0)

    for c in ["Avg+2D", "Avg+5D", "Avg+10D", "OOS Avg Ret+2D %", "OOS Avg Ret+5D %", "OOS Avg Ret+10D %"]:
        if c in pat.columns:
            pat[c] = pd.to_numeric(pat[c], errors="coerce")

    # Normalize avg names if table uses OOS names
    if "Avg+2D" not in pat.columns and "OOS Avg Ret+2D %" in pat.columns:
        pat["Avg+2D"] = pat["OOS Avg Ret+2D %"]
    if "Avg+5D" not in pat.columns and "OOS Avg Ret+5D %" in pat.columns:
        pat["Avg+5D"] = pat["OOS Avg Ret+5D %"]
    if "Avg+10D" not in pat.columns and "OOS Avg Ret+10D %" in pat.columns:
        pat["Avg+10D"] = pat["OOS Avg Ret+10D %"]

    return pat, pattern_col, oos_pct_col, oos_n_col


def _pm_select_patterns(pattern_df, mode="T2"):
    pat, pattern_col, oos_pct_col, oos_n_col = _pm_prepare_pattern_table(pattern_df)
    if pat.empty:
        return pd.DataFrame(), pattern_col, oos_pct_col, oos_n_col

    if mode == "T2":
        avg_col = "Avg+2D"
        avg_min = 0.5
    elif mode == "T5":
        avg_col = "Avg+5D"
        avg_min = 1.0
    else:
        avg_col = "Avg+5D"
        avg_min = 0.0

    if avg_col not in pat.columns:
        pat[avg_col] = 0

    # Balanced VN-market rules:
    # Tier 1: OOS >= 80, OOSN >= 3
    # Tier 2: OOS >= 70, OOSN >= 5
    # Plus avg return filter matching the holding horizon.
    mask_strength = (
        ((pat[oos_pct_col] >= 80) & (pat[oos_n_col] >= 3)) |
        ((pat[oos_pct_col] >= 70) & (pat[oos_n_col] >= 5))
    )
    mask_avg = pd.to_numeric(pat[avg_col], errors="coerce").fillna(-999) > avg_min

    strong = pat[mask_strength & mask_avg].copy()

    if strong.empty:
        return pd.DataFrame(), pattern_col, oos_pct_col, oos_n_col

    strong["PM Mode"] = mode
    strong["PM Avg Used"] = avg_col
    strong["PM Avg Value"] = pd.to_numeric(strong[avg_col], errors="coerce")

    keep = [pattern_col, oos_pct_col, oos_n_col, "PM Mode", "PM Avg Used", "PM Avg Value"]
    for c in ["Avg+2D", "Avg+5D", "Avg+10D", "Trust", "Note", "Source"]:
        if c in strong.columns and c not in keep:
            keep.append(c)

    strong = strong[keep].drop_duplicates(subset=[pattern_col], keep="first")
    strong = strong.sort_values([oos_pct_col, oos_n_col, "PM Avg Value"], ascending=False)
    return strong, pattern_col, oos_pct_col, oos_n_col


def build_top_codes_by_proven_pattern(signal_df, pattern_df, mode="ALL", limit=20):
    """
    PRO MAX:
    Map proven patterns back to current tickers.
    mode:
    - T2: short trade, requires Avg+2D > 0.5
    - T5: swing T+5, requires Avg+5D > 1.0
    - ALL: combine both T2 and T5 patterns
    """

    if signal_df is None or signal_df.empty:
        return pd.DataFrame()
    if pattern_df is None or pattern_df.empty:
        return pd.DataFrame()

    sig = normalize_output_columns(signal_df.copy())
    signal_pattern_col = _pm_find_col(sig, ["Pattern", "Pattern Key"])
    if signal_pattern_col is None:
        return pd.DataFrame()

    if mode == "T2":
        strong, pattern_col, oos_pct_col, oos_n_col = _pm_select_patterns(pattern_df, "T2")
    elif mode == "T5":
        strong, pattern_col, oos_pct_col, oos_n_col = _pm_select_patterns(pattern_df, "T5")
    else:
        t2, pattern_col, oos_pct_col, oos_n_col = _pm_select_patterns(pattern_df, "T2")
        t5, _, _, _ = _pm_select_patterns(pattern_df, "T5")
        strong = safe_concat_frames([t2, t5])
        if strong is not None and not strong.empty and pattern_col:
            strong = strong.drop_duplicates(subset=[pattern_col, "PM Mode"], keep="first")

    if strong is None or strong.empty or pattern_col is None:
        return pd.DataFrame()

    merged = sig.merge(
        strong,
        left_on=signal_pattern_col,
        right_on=pattern_col,
        how="inner",
        suffixes=("", "_pattern")
    )

    if merged.empty:
        return pd.DataFrame()

    merged["Rec"] = merged.apply(build_simple_recommendation, axis=1)
    merged["Why"] = merged.apply(build_simple_reason, axis=1)
    merged["Buy Zone"] = merged.apply(build_buy_zone, axis=1)
    merged["Stop Loss"] = merged.apply(build_stop_loss, axis=1)

    rename = {
        "Ngay": "Date",
        "Ma": "Code",
        "Close": "Price",
        "AI Confidence": "AI",
        oos_pct_col: "OOS%",
        oos_n_col: "OOSN",
        "PM Mode": "Trade Mode",
        "PM Avg Value": "Avg Used",
        "PM Avg Used": "Avg Type",
    }
    merged = merged.rename(columns={k: v for k, v in rename.items() if k in merged.columns})

    for c in ["OOS%", "OOSN", "Score", "AI", "RSI", "RS20", "Price", "Avg Used", "Avg+2D", "Avg+5D", "Avg+10D"]:
        if c in merged.columns:
            merged[c] = pd.to_numeric(merged[c], errors="coerce")

    sort_cols = [c for c in ["OOS%", "OOSN", "Avg Used", "AI", "Score"] if c in merged.columns]
    if sort_cols:
        merged = merged.sort_values(sort_cols, ascending=False)

    preferred = [
        "Trade Mode", "Date", "Code", "Price", "Rec",
        "OOS%", "OOSN", "Avg Type", "Avg Used",
        "Avg+2D", "Avg+5D", "Avg+10D",
        "Trust", "Note", "Score", "AI", "AI Grade",
        "Strategy", "Chien luoc", "RSI", "RS20", "Volume Ratio", "ATR %",
        "Buy Zone", "Stop Loss", "Risk Status", "Why", "Pattern"
    ]

    cols = [c for c in preferred if c in merged.columns]
    view = merged[cols].copy() if cols else merged.copy()
    return view.replace({np.nan: ""}).head(limit)


def build_pattern_to_codes_map(signal_df, pattern_df, mode="ALL", limit=20):
    """
    PRO MAX:
    Group tickers by proven pattern, so user can see:
    Pattern -> which tickers today belong to it.
    """

    codes = build_top_codes_by_proven_pattern(signal_df, pattern_df, mode=mode, limit=999)
    if codes is None or codes.empty:
        return pd.DataFrame()

    pattern_col = "Pattern" if "Pattern" in codes.columns else None
    code_col = "Code" if "Code" in codes.columns else None
    if pattern_col is None or code_col is None:
        return pd.DataFrame()

    rows = []
    for pat_key, g in codes.groupby(pattern_col):
        g = g.copy()
        top_codes = ", ".join(g[code_col].astype(str).head(8).tolist())
        best = g.iloc[0]

        rows.append({
            "Trade Mode": str(best.get("Trade Mode", mode)),
            "Pattern": str(pat_key)[:120],
            "OOS%": best.get("OOS%", ""),
            "OOSN": best.get("OOSN", ""),
            "Avg Used": best.get("Avg Used", ""),
            "Num Codes": len(g),
            "Top Codes": top_codes,
            "Best Code": best.get("Code", ""),
            "Best Rec": best.get("Rec", ""),
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        for c in ["OOS%", "OOSN", "Avg Used", "Num Codes"]:
            out[c] = pd.to_numeric(out[c], errors="coerce")
        out = out.sort_values(["Trade Mode", "OOS%", "OOSN", "Avg Used", "Num Codes"], ascending=[True, False, False, False, False])
    return out.replace({np.nan: ""}).head(limit)

# ============================================================
# STABLE PRO: Top codes by nearest proven stats
# ============================================================
# This version is intentionally simple and robust:
# - It starts from today's signals (combined), so codes always come from real current output.
# - It uses historical pattern stats only as evidence.
# - Matching is soft by Regime + Strategy first, then Regime fallback.
# - It does not change buy/sell logic; only dashboard display.

def _stable_find_col(df, names):
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.columns:
            return n
    return None


def _stable_extract_parts(pattern_value):
    try:
        return [p.strip() for p in str(pattern_value).split("|") if p.strip() and p.strip().lower() not in ["nan", "none"]]
    except Exception:
        return []


def _stable_core2(pattern_value):
    parts = _stable_extract_parts(pattern_value)
    if len(parts) >= 2:
        return f"{parts[0]}|{parts[1]}"
    if len(parts) == 1:
        return parts[0]
    return ""


def _stable_core1(pattern_value):
    parts = _stable_extract_parts(pattern_value)
    if parts:
        return parts[0]
    return ""


def _stable_prepare_pattern_stats(pattern_df):
    if pattern_df is None or pattern_df.empty:
        return pd.DataFrame()

    pat = pattern_df.copy()
    pattern_col = _stable_find_col(pat, ["Pattern Key", "Pattern"])
    if pattern_col is None:
        return pd.DataFrame()

    oos_col = _stable_find_col(pat, ["OOS Win Probability", "OOS%", "OOS Win Rate"])
    n_col = _stable_find_col(pat, ["OOS Samples", "OOSN", "OOS N"])

    if oos_col is None:
        return pd.DataFrame()
    if n_col is None:
        pat["OOSN"] = 0
        n_col = "OOSN"

    pat["OOS%"] = pd.to_numeric(pat[oos_col], errors="coerce")
    pat["OOSN"] = pd.to_numeric(pat[n_col], errors="coerce").fillna(0)

    # Normalize Avg names
    if "Avg+2D" not in pat.columns and "OOS Avg Ret+2D %" in pat.columns:
        pat["Avg+2D"] = pat["OOS Avg Ret+2D %"]
    if "Avg+5D" not in pat.columns and "OOS Avg Ret+5D %" in pat.columns:
        pat["Avg+5D"] = pat["OOS Avg Ret+5D %"]
    if "Avg+10D" not in pat.columns and "OOS Avg Ret+10D %" in pat.columns:
        pat["Avg+10D"] = pat["OOS Avg Ret+10D %"]

    for c in ["Avg+2D", "Avg+5D", "Avg+10D"]:
        if c in pat.columns:
            pat[c] = pd.to_numeric(pat[c], errors="coerce")
        else:
            pat[c] = np.nan

    pat["Pattern Text"] = pat[pattern_col].astype(str)
    pat["Core2"] = pat["Pattern Text"].apply(_stable_core2)
    pat["Core1"] = pat["Pattern Text"].apply(_stable_core1)

    # Keep useful proven rows only, but not too strict
    pat = pat[
        (pat["OOS%"] >= 65) &
        (pat["OOSN"] >= 3)
    ].copy()

    if pat.empty:
        return pd.DataFrame()

    # Rank stronger historical evidence first
    pat = pat.sort_values(["OOS%", "OOSN", "Avg+5D"], ascending=False)
    return pat


def _stable_prepare_current_signals(signal_df):
    if signal_df is None or signal_df.empty:
        return pd.DataFrame()

    sig = normalize_output_columns(signal_df.copy())

    # Need code column
    if "Ma" not in sig.columns:
        return pd.DataFrame()

    # Ensure Pattern Key exists if possible
    if "Pattern Key" not in sig.columns:
        try:
            sig["Pattern Key"] = sig.apply(lambda r: make_pattern_key(r, str(r.get("Market Regime Now", ""))), axis=1)
        except Exception:
            sig["Pattern Key"] = ""

    # If Pattern Key still empty, create approximate key using regime + strategy
    missing = sig["Pattern Key"].isna() | (sig["Pattern Key"].astype(str).str.strip() == "")
    if missing.any():
        regime = sig.get("Market Regime Now", "")
        strategy = sig.get("Chien luoc", sig.get("Strategy", ""))
        sig.loc[missing, "Pattern Key"] = (
            sig.loc[missing].get("Market Regime Now", "").astype(str) + "|" +
            sig.loc[missing].get("Chien luoc", sig.loc[missing].get("Strategy", "")).astype(str)
        )

    sig["Core2"] = sig["Pattern Key"].astype(str).apply(_stable_core2)
    sig["Core1"] = sig["Pattern Key"].astype(str).apply(_stable_core1)

    return sig


def build_top_codes_by_proven_pattern_stable(signal_df, pattern_df, mode="T5", limit=20):
    """
    Stable dashboard table:
    Codes today + nearest proven historical stats.

    mode:
    - T2 uses Avg+2D > 0.3
    - T5 uses Avg+5D > 0.8
    """

    sig = _stable_prepare_current_signals(signal_df)
    pat = _stable_prepare_pattern_stats(pattern_df)

    if sig.empty or pat.empty:
        return pd.DataFrame()

    if mode == "T2":
        avg_col = "Avg+2D"
        avg_min = 0.3
    else:
        avg_col = "Avg+5D"
        avg_min = 0.8

    pat_mode = pat[pd.to_numeric(pat[avg_col], errors="coerce").fillna(-999) > avg_min].copy()
    if pat_mode.empty:
        return pd.DataFrame()

    # First match by Regime + Strategy
    m2 = sig.merge(
        pat_mode,
        on="Core2",
        how="inner",
        suffixes=("", "_hist")
    )
    if not m2.empty:
        m2["Match Level"] = "REGIME+STRATEGY"
    else:
        m2 = pd.DataFrame()

    # Fallback match by Regime only
    m1 = sig.merge(
        pat_mode,
        on="Core1",
        how="inner",
        suffixes=("", "_hist")
    )
    if not m1.empty:
        m1["Match Level"] = "REGIME"
    else:
        m1 = pd.DataFrame()

    merged = safe_concat_frames([m2, m1])
    if merged.empty:
        return pd.DataFrame()

    # Prefer stricter match and stronger stats
    merged["Match Rank"] = merged["Match Level"].map({"REGIME+STRATEGY": 1, "REGIME": 2}).fillna(9)
    merged = merged.sort_values(["Match Rank", "OOS%", "OOSN", avg_col, "Score"], ascending=[True, False, False, False, False])
    merged = merged.drop_duplicates(subset=["Ma"], keep="first").reset_index(drop=True)

    # Add action helpers
    try:
        merged["Rec"] = merged.apply(build_simple_recommendation, axis=1)
    except Exception:
        merged["Rec"] = merged.get("Action", "")

    try:
        merged["Why"] = merged.apply(build_simple_reason, axis=1)
    except Exception:
        merged["Why"] = ""

    try:
        merged["Buy Zone"] = merged.apply(build_buy_zone, axis=1)
    except Exception:
        merged["Buy Zone"] = ""

    try:
        merged["Stop Loss"] = merged.apply(build_stop_loss, axis=1)
    except Exception:
        merged["Stop Loss"] = ""

    merged["Trade Mode"] = mode
    merged["Avg Used"] = pd.to_numeric(merged[avg_col], errors="coerce")
    merged["Avg Type"] = avg_col

    rename = {
        "Ngay": "Date",
        "Ma": "Code",
        "Close": "Price",
        "AI Confidence": "AI",
        "Chien luoc": "Strategy",
    }
    merged = merged.rename(columns={k: v for k, v in rename.items() if k in merged.columns})

    for c in ["Price", "OOS%", "OOSN", "Avg Used", "Avg+2D", "Avg+5D", "Avg+10D", "Score", "AI", "RSI", "RS20"]:
        if c in merged.columns:
            merged[c] = pd.to_numeric(merged[c], errors="coerce")

    preferred = [
        "Trade Mode", "Match Level", "Date", "Code", "Price", "Rec",
        "OOS%", "OOSN", "Avg Type", "Avg Used", "Avg+2D", "Avg+5D", "Avg+10D",
        "Score", "AI", "Strategy", "RSI", "RS20", "Volume Ratio", "ATR %",
        "Buy Zone", "Stop Loss", "Risk Status", "Why", "Core2", "Core1"
    ]

    cols = [c for c in preferred if c in merged.columns]
    return merged[cols].replace({np.nan: ""}).head(limit)


def build_pattern_to_codes_map_stable(signal_df, pattern_df, mode="ALL", limit=20):
    t2 = build_top_codes_by_proven_pattern_stable(signal_df, pattern_df, mode="T2", limit=999)
    t5 = build_top_codes_by_proven_pattern_stable(signal_df, pattern_df, mode="T5", limit=999)

    codes = safe_concat_frames([t2, t5])
    if codes.empty or "Core2" not in codes.columns:
        return pd.DataFrame()

    rows = []
    for core, g in codes.groupby("Core2"):
        best = g.iloc[0]
        rows.append({
            "Pattern Group": core,
            "Trade Modes": ", ".join(sorted(set(g["Trade Mode"].astype(str)))),
            "Num Codes": len(g),
            "Top Codes": ", ".join(g["Code"].astype(str).head(10).tolist()) if "Code" in g.columns else "",
            "Best Code": best.get("Code", ""),
            "Best Rec": best.get("Rec", ""),
            "Best OOS%": best.get("OOS%", ""),
            "Best Avg": best.get("Avg Used", ""),
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        for c in ["Num Codes", "Best OOS%", "Best Avg"]:
            out[c] = pd.to_numeric(out[c], errors="coerce")
        out = out.sort_values(["Best OOS%", "Best Avg", "Num Codes"], ascending=False)

    return out.replace({np.nan: ""}).head(limit)


# ============================================================
# STABLE TOPCODES REGIME NORMALIZATION FIX
# Override stable helpers to fix:
# "TANG MANH / UPTREND" != "UPTREND"
# ============================================================

def _stable_norm_text(x):
    try:
        s = str(x).strip().upper()
        s = s.replace(" ", "")
        return s
    except Exception:
        return ""


def _stable_norm_regime(x):
    """
    Normalize regime text so current signal regime can match historical pattern regime.

    Examples:
    "TANG MANH / UPTREND" -> "UPTREND"
    "TANG MANH/UPTREND" -> "UPTREND"
    "UPTREND" -> "UPTREND"
    """
    try:
        s = str(x).strip().upper()
        if "/" in s:
            s = s.split("/")[-1].strip()
        s = s.replace(" ", "")
        return s
    except Exception:
        return ""


def _stable_norm_strategy(x):
    try:
        s = str(x).strip().upper()
        s = s.replace(" ", "_")
        return s
    except Exception:
        return ""


def _stable_core2(pattern_value):
    parts = _stable_extract_parts(pattern_value)
    if len(parts) >= 2:
        return f"{_stable_norm_regime(parts[0])}|{_stable_norm_strategy(parts[1])}"
    if len(parts) == 1:
        return _stable_norm_regime(parts[0])
    return ""


def _stable_core1(pattern_value):
    parts = _stable_extract_parts(pattern_value)
    if parts:
        return _stable_norm_regime(parts[0])
    return ""


def _stable_prepare_current_signals(signal_df):
    if signal_df is None or signal_df.empty:
        return pd.DataFrame()

    sig = normalize_output_columns(signal_df.copy())

    if "Ma" not in sig.columns:
        return pd.DataFrame()

    # Current regime: normalize "TANG MANH / UPTREND" -> "UPTREND"
    regime_col = _stable_find_col(sig, ["Market Regime Now", "Regime"])
    if regime_col:
        sig["PM Regime"] = sig[regime_col].apply(_stable_norm_regime)
    else:
        sig["PM Regime"] = ""

    # Current strategy
    strategy_col = _stable_find_col(sig, ["Chien luoc", "Strategy", "Chiến lược"])
    if strategy_col:
        sig["PM Strategy"] = sig[strategy_col].apply(_stable_norm_strategy)
    else:
        sig["PM Strategy"] = ""

    # Try Pattern Key fallback if regime/strategy missing
    if "Pattern Key" not in sig.columns:
        try:
            sig["Pattern Key"] = sig.apply(lambda r: make_pattern_key(r, str(r.get("Market Regime Now", ""))), axis=1)
        except Exception:
            sig["Pattern Key"] = ""

    missing_regime = sig["PM Regime"].astype(str).str.strip() == ""
    if missing_regime.any() and "Pattern Key" in sig.columns:
        sig.loc[missing_regime, "PM Regime"] = sig.loc[missing_regime, "Pattern Key"].apply(_stable_core1)

    missing_strategy = sig["PM Strategy"].astype(str).str.strip() == ""
    if missing_strategy.any() and "Pattern Key" in sig.columns:
        sig.loc[missing_strategy, "PM Strategy"] = sig.loc[missing_strategy, "Pattern Key"].apply(
            lambda x: _stable_core2(x).split("|")[-1] if "|" in _stable_core2(x) else ""
        )

    sig["PM Key2"] = sig["PM Regime"].astype(str) + "|" + sig["PM Strategy"].astype(str)
    sig["PM Key1"] = sig["PM Regime"].astype(str)

    return sig
