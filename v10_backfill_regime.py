from v10_config import *
from v10_utils import *
from v10_indicators import *
from v10_strategy import *


# ============================================================
# MARKET REGIME FALLBACK
# ============================================================

def classify_market_regime(market_ret20):
    """
    Safe local fallback.
    This prevents NameError when get_market_regime_from_cache calls this function.
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


# ============================================================
# BACKFILL SAFETY HELPERS
# ============================================================

def bf_normalize_columns(df):
    if df is None:
        return df
    try:
        if df.empty:
            return df

        rename_map = {
            "M": "Ma",
            "Ma": "Ma",
            "MÃ£": "Ma",
            "MÃÂ£": "Ma",

            "Ng y": "Ngay",
            "Ngy": "Ngay",
            "Ngay": "Ngay",
            "NgÃ y": "Ngay",
            "NgÃÂ y": "Ngay",

            "Chin lc": "Chien luoc",
            "Chien luoc": "Chien luoc",
            "Chiáº¿n lÆ°á»£c": "Chien luoc",
            "ChiÃ¡ÂºÂ¿n lÃÂ°Ã¡Â»Â£c": "Chien luoc",
        }

        out = df.copy()
        out.columns = [rename_map.get(str(c), str(c).replace("\ufeff", "").strip()) for c in out.columns]
        out = out.loc[:, ~out.columns.duplicated()]
        out = out.reset_index(drop=True)
        return out
    except Exception:
        return df


def bf_safe_concat(frames):
    clean = []
    for df in frames:
        if df is None:
            continue
        df = bf_normalize_columns(df)
        if df is not None and not df.empty:
            clean.append(df.loc[:, ~df.columns.duplicated()].reset_index(drop=True))

    if not clean:
        return pd.DataFrame()

    return pd.concat(clean, ignore_index=True, sort=False)


def bf_deduplicate_history(hist):
    hist = bf_normalize_columns(hist)
    if hist is None or hist.empty:
        return hist

    subset = []
    for c in ["Ngay", "Ma", "Pattern Key"]:
        if c in hist.columns:
            subset.append(c)

    if subset:
        hist = hist.drop_duplicates(subset=subset, keep="last")

    return hist.reset_index(drop=True)


def get_backfill_state():
    df = bf_normalize_columns(safe_read_csv(BACKFILL_STATE_PATH))
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
    ts = pd.Timestamp(ts)
    month = ts.month - 1 + int(months)
    year = ts.year + month // 12
    month = month % 12 + 1
    return pd.Timestamp(year=year, month=month, day=1)


def get_backfill_block_info(date_value):
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
    d = pd.to_datetime(date_value, errors="coerce")
    if pd.isna(d) or pd.isna(block_start) or pd.isna(block_end):
        return "UNKNOWN"

    total_days = max((block_end - block_start).days, 1)
    split_day = block_start + pd.Timedelta(days=int(total_days * BACKFILL_TRAIN_RATIO))

    return "TRAIN" if d < split_day else "TEST"


def detect_market_regime_detail(market_df=None, market_ret20=0):
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

            df = bf_normalize_columns(safe_read_csv(cache_path))
            if df.empty:
                continue

            regime = detect_market_regime_detail(df, market_ret20)
            print(f"Market regime: {regime}")
            return regime
        except Exception:
            continue

    regime = classify_market_regime(market_ret20)
    print(f"Market regime fallback: {regime}")
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
    if hist is None or hist.empty:
        return pd.DataFrame()

    h = hist.copy()
    h = normalize_outcome_dtype(h)
    if "Pattern Key" not in h.columns or "Market Regime" not in h.columns:
        return pd.DataFrame()

    h = bf_normalize_columns(h)
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
        print(f"Regime stats updated: {len(stats)} rows")

    return stats


def apply_regime_decay_filter(combined, regime_stats, current_regime):
    if combined is None or combined.empty:
        return combined

    df = combined.copy()
    df["Market Regime Now"] = current_regime

    if "Final Action" not in df.columns:
        df["Final Action"] = df.get("AI Action", df.get("Action", "THEO DOI"))

    if regime_stats is None or regime_stats.empty or "Pattern Key" not in df.columns:
        df["Regime Win Probability"] = np.nan
        df["Regime Samples"] = 0
        df["Regime Note"] = "No regime stats"
        return df

    rs = regime_stats[regime_stats["Market Regime"].astype(str) == str(current_regime)].copy()

    if rs.empty:
        df["Regime Win Probability"] = np.nan
        df["Regime Samples"] = 0
        df["Regime Note"] = f"No stats for regime {current_regime}"
        return df

    rmap = rs.set_index("Pattern Key").to_dict(orient="index")

    probs, samples, notes, final_actions, adjusted_conf = [], [], [], [], []

    for _, r in df.iterrows():
        key = r.get("Pattern Key")
        stat = rmap.get(key)

        final_action = str(r.get("Final Action", r.get("AI Action", r.get("Action", "THEO DOI"))))
        conf = safe_float(r.get("AI Confidence"), safe_float(r.get("Score"), 50))

        if not stat:
            probs.append(np.nan)
            samples.append(0)
            notes.append(f"Pattern has no data in regime {current_regime}")
            final_actions.append(final_action)
            adjusted_conf.append(round(conf, 0))
            continue

        p = safe_float(stat.get("Regime Win Probability"), BASE_WIN_PROB)
        n = int(safe_float(stat.get("Regime Samples"), 0))
        note = f"{current_regime}: {n} samples, win decay ~{p:.1f}%"

        if n >= MIN_PATTERN_SAMPLES and p >= 62:
            conf += REGIME_BONUS_STRONG
            note += " | regime supports signal"
            if final_action in ["MUA THAM DO", "THEO DOI MANH", "CHO XAC NHAN"] and conf >= 78:
                final_action = "MUA THAM DO"
            if final_action == "MUA THAM DO" and conf >= 88:
                final_action = "MUA UU TIEN"

        elif n >= MIN_PATTERN_SAMPLES and p < 48:
            conf -= REGIME_PENALTY_BAD
            note += " | weak regime signal"
            if final_action in ["MUA UU TIEN", "MUA THAM DO"]:
                final_action = "CHO XAC NHAN"
            elif final_action in ["CHO XAC NHAN", "THEO DOI MANH"] and p < 42:
                final_action = "BO QUA"

        elif n < MIN_PATTERN_SAMPLES:
            note += " | low regime sample"
            if final_action == "MUA UU TIEN":
                final_action = "MUA THAM DO"

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
    if not BACKFILL_ENABLED:
        print("Backfill disabled")
        return safe_read_csv(BACKFILL_SIGNAL_HISTORY_PATH)

    os.makedirs(CACHE_DIR, exist_ok=True)

    start_idx = get_backfill_state()
    if start_idx >= len(UNIVERSE):
        start_idx = 0

    end_idx = min(start_idx + BACKFILL_MAX_SYMBOLS_PER_RUN, len(UNIVERSE))
    symbols = UNIVERSE[start_idx:end_idx]

    print(f"Backfill V7: {start_idx} -> {end_idx} / {len(UNIVERSE)}")

    rows = []
    market_regime = current_market_regime if 'current_market_regime' in globals() else classify_market_regime(market_ret20)

    cutoff = pd.Timestamp(now_vietnam().date()) - pd.Timedelta(days=BACKFILL_LOOKBACK_DAYS)

    for symbol in symbols:
        cache_path = os.path.join(CACHE_DIR, f"{symbol}.csv")
        if not os.path.exists(cache_path):
            continue

        dfp = bf_normalize_columns(safe_read_csv(cache_path))
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

    new_hist = bf_normalize_columns(pd.DataFrame(rows))

    old = bf_normalize_columns(safe_read_csv(BACKFILL_SIGNAL_HISTORY_PATH))
    hist = bf_safe_concat([old, new_hist])
    hist = bf_deduplicate_history(hist)

    if not hist.empty:
        sort_cols = [c for c in ["Ngay", "Ma"] if c in hist.columns]
        if sort_cols:
            hist = hist.sort_values(sort_cols).reset_index(drop=True)

    hist = normalize_outcome_dtype(hist)
    hist.to_csv(BACKFILL_SIGNAL_HISTORY_PATH, index=False, encoding="utf-8-sig")

    next_start = end_idx
    if next_start >= len(UNIVERSE):
        next_start = 0
    save_backfill_state(next_start)

    print(f"Backfill history rows: {len(hist)} | new rows: {len(new_hist)} | next: {next_start}")

    return hist


def build_backfill_walk_forward_stats(backfill_hist):
    if backfill_hist is None or backfill_hist.empty:
        return pd.DataFrame()

    h = bf_normalize_columns(backfill_hist.copy())
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

    raw = bf_normalize_columns(pd.DataFrame(rows))

    if raw.empty:
        return pd.DataFrame()

    agg = []
    for key, g in raw.groupby("Pattern Key"):
        total_samples = int(g["OOS Samples"].sum())
        windows = len(g)
        weighted_win = (g["OOS Win Rate"] * g["OOS Samples"]).sum() / max(total_samples, 1)
        avg_ret5 = pd.to_numeric(g.get("OOS Avg Ret+5D %"), errors="coerce").mean()
        avg_ret10 = pd.to_numeric(g.get("OOS Avg Ret+10D %"), errors="coerce").mean()

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

    stats = bf_normalize_columns(pd.DataFrame(agg))
    if not stats.empty:
        stats = stats.sort_values(["OOS Win Probability", "OOS Samples"], ascending=False)
        stats.to_csv(BACKFILL_WALK_FORWARD_PATH, index=False, encoding="utf-8-sig")
        print(f"Backfill walk-forward stats: {len(stats)} patterns")

    return stats


def merge_walk_forward_sources(live_wf, backfill_wf):
    if live_wf is None or live_wf.empty:
        return backfill_wf if backfill_wf is not None else pd.DataFrame()

    if backfill_wf is None or backfill_wf.empty:
        return live_wf

    live = live_wf.copy()
    live["WF Source"] = "LIVE"

    back = backfill_wf.copy()
    back["WF Source"] = "BACKFILL"

    combined = bf_safe_concat([live, back])
    combined = combined.sort_values(["WF Source", "OOS Samples"], ascending=[False, False])
    combined = combined.drop_duplicates(subset=["Pattern Key"], keep="first").reset_index(drop=True)

    combined.to_csv(WALK_FORWARD_STATS_PATH, index=False, encoding="utf-8-sig")
    return combined
