from v10_config import *
from v10_utils import *
from v10_strategy import *
from v10_backfill_regime import classify_market_regime
def make_pattern_key(row, market_regime="NORMAL"):
    try:
        strategy = str(row.get("Chien luoc", "UNKNOWN"))
        signal = str(row.get("Signal", "UNKNOWN"))
        return f"{strategy}_{signal}_{market_regime}"
    except Exception:
        return "UNKNOWN_PATTERN"
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

    # Always compute T+2 return for short T+2/T+5 trading analysis,
    # even if HOLD_DAYS_LIST does not include 2.
    target_idx_2 = entry_idx + 2
    if target_idx_2 < len(dfp):
        future_close_2 = safe_float(dfp.loc[target_idx_2, "close"], np.nan)
        ret2 = (future_close_2 / entry_price - 1) * 100 if entry_price and not pd.isna(future_close_2) else np.nan
        out["Ret+2D %"] = round(ret2, 2) if not pd.isna(ret2) else np.nan
    else:
        out["Ret+2D %"] = np.nan

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

    outcome_cols = ["Ret+2D %", "Ret+3D %", "Ret+5D %", "Ret+10D %", "Max+10D %", "Min+10D %", "Outcome"]
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

        avg_ret2 = pd.to_numeric(g.get("Ret+2D %"), errors="coerce").mean()
        avg_ret5 = pd.to_numeric(g.get("Ret+5D %"), errors="coerce").mean()
        avg_ret10 = pd.to_numeric(g.get("Ret+10D %"), errors="coerce").mean()

        rows.append({
            "Pattern Key": key,
            "Samples": sample,
            "Weighted Samples": round(weighted_n, 2),
            "Win Probability": round(win_prob, 2),
            "Win Count": int(g["Win Flag"].sum()),
            "Loss Count": int(g["Loss Flag"].sum()),
            "Avg Ret+2D %": round(avg_ret2, 2) if not pd.isna(avg_ret2) else np.nan,
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
                avg_ret2 = pd.to_numeric(g.get("Ret+2D %"), errors="coerce").mean()
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
                    "OOS Avg Ret+2D %": round(avg_ret2, 2) if not pd.isna(avg_ret2) else np.nan,
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
        avg_ret2 = pd.to_numeric(g.get("OOS Avg Ret+2D %"), errors="coerce").mean()
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
            "OOS Avg Ret+2D %": round(avg_ret2, 2) if not pd.isna(avg_ret2) else np.nan,
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

    # ========== PHẦN CHÈN MỚI: RSI DIVERGENCE ==========
    # Lấy các cột đã được tính trong v10_indicators.py
    rsi_5 = safe_float(row.get("RSI_5"), 0)
    rsi_20 = safe_float(row.get("RSI_20"), 0)
    close_5 = safe_float(row.get("Close_5"), 0)
    close_20 = safe_float(row.get("Close_20"), 0)
    rsi_ma5 = safe_float(row.get("RSI_MA5"), 0)
    close = safe_float(row.get("Close"), 0)

    # Phân kỳ giảm (Bearish divergence): giá tạo đỉnh cao hơn 5 phiên nhưng RSI thấp hơn
    if close_5 > 0 and rsi_5 > 0 and close > close_5 and rsi < rsi_5:
        confidence -= 18
        warnings.append("RSI phân kỳ giảm: giá cao hơn 5 phiên nhưng RSI thấp hơn → động lực yếu, rủi ro đảo chiều")
    
    # Phân kỳ tăng (Bullish divergence): giá tạo đáy thấp hơn 20 phiên nhưng RSI cao hơn
    if close_20 > 0 and rsi_20 > 0 and close < close_20 and rsi > rsi_20:
        confidence += 15
        reasons.append("RSI phân kỳ tăng: giá thấp hơn 20 phiên nhưng RSI cao hơn → tín hiệu đáy, tiềm năng hồi phục")
    
    # Phân kỳ ẩn tăng (Hidden bullish): giá tạo đáy cao hơn 20 phiên, RSI tạo đáy thấp hơn → tiếp diễn uptrend
    if close_20 > 0 and rsi_20 > 0 and close > close_20 and rsi < rsi_20:
        confidence += 8
        reasons.append("RSI ẩn phân kỳ tăng (giá đáy cao hơn, RSI đáy thấp hơn) → xu hướng tăng tiếp diễn")
    
    # Phân kỳ ẩn giảm (Hidden bearish): giá tạo đỉnh thấp hơn 5 phiên, RSI tạo đỉnh cao hơn → tiếp diễn downtrend
    if close_5 > 0 and rsi_5 > 0 and close < close_5 and rsi > rsi_5:
        confidence -= 8
        warnings.append("RSI ẩn phân kỳ giảm (giá đỉnh thấp hơn, RSI đỉnh cao hơn) → xu hướng giảm tiếp diễn")
    
    # Fallback khi thiếu dữ liệu lịch sử: dùng RSI_MA5 để ước lượng
    if (rsi_5 == 0 or rsi_20 == 0 or close_5 == 0 or close_20 == 0) and rsi_ma5 > 0:
        if rsi < rsi_ma5 and rsi_ma5 - rsi > 5:
            confidence -= 10
            warnings.append("RSI suy yếu so với MA5, có thể phân kỳ giảm sơ khởi")
        elif rsi > rsi_ma5 and rsi - rsi_ma5 > 5:
            confidence += 8
            reasons.append("RSI mạnh hơn MA5, có thể phân kỳ tăng sơ khởi")
    # ========== KẾT THÚC PHẦN CHÈN ==========

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

def load_ai_evidence_tables():
    """
    Load AI evidence files if available.
    These prove whether learning / OOS testing has real data.
    """
    wf = safe_read_csv(WALK_FORWARD_STATS_PATH)
    back_wf = safe_read_csv(BACKFILL_WALK_FORWARD_PATH) if "BACKFILL_WALK_FORWARD_PATH" in globals() else pd.DataFrame()
    reg = safe_read_csv(REGIME_STATS_PATH) if "REGIME_STATS_PATH" in globals() else pd.DataFrame()
    pat = safe_read_csv(PATTERN_STATS_PATH) if "PATTERN_STATS_PATH" in globals() else pd.DataFrame()
    return wf, back_wf, reg, pat

def ai_trust_label(oos_prob, oos_n, reg_prob=None, reg_n=0):
    oos_prob = safe_float(oos_prob, np.nan)
    oos_n = safe_float(oos_n, 0)
    reg_prob = safe_float(reg_prob, np.nan)
    reg_n = safe_float(reg_n, 0)

    if pd.isna(oos_prob) or oos_n < 5:
        return "LOW - chua du OOS"

    if oos_prob >= 60 and oos_n >= 10:
        if not pd.isna(reg_prob) and reg_prob >= 55 and reg_n >= 5:
            return "HIGH"
        return "MEDIUM-HIGH"

    if oos_prob >= 52 and oos_n >= 5:
        return "MEDIUM"

    if oos_prob < 45 and oos_n >= 5:
        return "LOW - OOS yeu"

    return "LOW-MEDIUM"

def build_row_evidence(row):
    oos = safe_float(row.get("OOS Win Probability"), np.nan)
    oos_n = safe_float(row.get("OOS Samples"), 0)
    reg = safe_float(row.get("Regime Win Probability"), np.nan)
    reg_n = safe_float(row.get("Regime Samples"), 0)
    win = safe_float(row.get("Win Probability"), np.nan)

    parts = []
    if not pd.isna(oos) and oos_n > 0:
        parts.append(f"OOS {oos:.0f}%/{int(oos_n)} mau")
    else:
        parts.append("OOS chua du")

    if not pd.isna(reg) and reg_n > 0:
        parts.append(f"Reg {reg:.0f}%/{int(reg_n)} mau")

    if not pd.isna(win):
        parts.append(f"Win {win:.0f}%")

    return " | ".join(parts)

def build_ai_summary_table(wf_stats, back_wf_stats, regime_stats, pattern_stats):
    rows = []

    def summarize(name, df, prob_col="OOS Win Probability", sample_col="OOS Samples"):
        if df is None or df.empty:
            rows.append({
                "Module": name,
                "Rows": 0,
                "With Data": 0,
                "Avg Win%": "",
                "Strong": 0,
                "Weak": 0,
                "Note": "No data yet"
            })
            return

        d = df.copy()
        if prob_col in d.columns:
            d[prob_col] = pd.to_numeric(d[prob_col], errors="coerce")
        if sample_col in d.columns:
            d[sample_col] = pd.to_numeric(d[sample_col], errors="coerce").fillna(0)

        if prob_col in d.columns:
            valid = d[d[prob_col].notna()]
            strong = int((valid[prob_col] >= 60).sum())
            weak = int((valid[prob_col] < 45).sum())
            avg = valid[prob_col].mean() if not valid.empty else np.nan
            with_data = len(valid)
        else:
            strong = weak = with_data = 0
            avg = np.nan

        rows.append({
            "Module": name,
            "Rows": len(d),
            "With Data": with_data,
            "Avg Win%": round(avg, 1) if not pd.isna(avg) else "",
            "Strong": strong,
            "Weak": weak,
            "Note": "OK" if with_data > 0 else "Chua co mau test"
        })

    summarize("Walk-forward live", wf_stats)
    summarize("Backfill OOS 3M", back_wf_stats)
    summarize("Pattern history", pattern_stats, "Win Probability", "Samples")
    summarize("Regime stats", regime_stats, "Regime Win Probability", "Regime Samples")

    return pd.DataFrame(rows)

def build_top_proven_patterns(wf_stats, back_wf_stats, regime_stats):
    """
    Top proven patterns from OOS evidence.
    """
    frames = []
    for name, df in [("LIVE_WF", wf_stats), ("BACKFILL_WF", back_wf_stats)]:
        if df is None or df.empty:
            continue
        d = df.copy()
        if "OOS Win Probability" not in d.columns or "OOS Samples" not in d.columns:
            continue
        d["Source"] = name
        d["OOS Win Probability"] = pd.to_numeric(d["OOS Win Probability"], errors="coerce")
        d["OOS Samples"] = pd.to_numeric(d["OOS Samples"], errors="coerce").fillna(0)
        frames.append(d)

    if not frames:
        return pd.DataFrame([{
            "Pattern": "NO_OOS_DATA",
            "Source": "",
            "OOS%": "",
            "OOS N": "",
            "Avg+2D": "",
            "Avg+5D": "",
            "Avg+10D": "",
            "Trust": "LOW",
            "Note": "Chua co du lieu OOS"
        }])

    all_wf = pd.concat(frames, ignore_index=True)
    all_wf = all_wf.dropna(subset=["OOS Win Probability"])
    all_wf = all_wf[all_wf["OOS Samples"] >= 5]

    if all_wf.empty:
        return pd.DataFrame([{
            "Pattern": "LOW_SAMPLE",
            "Source": "",
            "OOS%": "",
            "OOS N": "",
            "Avg+2D": "",
            "Avg+5D": "",
            "Avg+10D": "",
            "Trust": "LOW",
            "Note": "Co OOS nhung chua du 5 mau"
        }])

    # Deduplicate by pattern, keep best sample/prob combo
    all_wf["RankScore"] = all_wf["OOS Win Probability"] + np.minimum(all_wf["OOS Samples"], 50) * 0.2
    all_wf = all_wf.sort_values("RankScore", ascending=False)
    all_wf = all_wf.drop_duplicates(subset=["Pattern Key"], keep="first")

    rows = []
    for _, r in all_wf.head(15).iterrows():
        oos = safe_float(r.get("OOS Win Probability"), np.nan)
        n = safe_float(r.get("OOS Samples"), 0)
        trust = ai_trust_label(oos, n)

        rows.append({
            "Pattern": clean_ascii_text(r.get("Pattern Key", ""), 80),
            "Source": clean_ascii_text(r.get("Source", ""), 20),
            "OOS%": round(oos, 1) if not pd.isna(oos) else "",
            "OOS N": int(n),
            "Avg+2D": safe_float(r.get("OOS Avg Ret+2D %"), np.nan),
            "Avg+5D": safe_float(r.get("OOS Avg Ret+5D %"), np.nan),
            "Avg+10D": safe_float(r.get("OOS Avg Ret+10D %"), np.nan),
            "Trust": trust,
            "Note": clean_ascii_text(r.get("OOS Status", ""), 40)
        })

    return pd.DataFrame(rows)

def add_explainable_columns(df):
    if df is None or df.empty:
        return df
    out = df.copy()
    out["Evidence"] = out.apply(build_row_evidence, axis=1)
    out["Trust"] = out.apply(
        lambda r: ai_trust_label(
            r.get("OOS Win Probability"),
            r.get("OOS Samples"),
            r.get("Regime Win Probability"),
            r.get("Regime Samples")
        ),
        axis=1
    )
    return out
