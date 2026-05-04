# -*- coding: utf-8 -*-
"""
V10 runner fixed:
- Normalize broken Vietnamese column names to ASCII-safe names
- Prevent pandas InvalidIndexError from duplicate columns / duplicate index
- Keep original V10 flow
"""

from v10_config import *
from v10_utils import *
from v10_market_data import *
from v10_indicators import *
from v10_strategy import *
from v10_learning import *
from v10_output import *
from v10_backfill_regime import *
import v10_learning
import v10_backfill_regime
from v11_market_overlay import ap_dung_v11_market_overlay, tao_bang_v11_leader, tao_bang_v11_bi_ha_hang
from v11_pattern_stats_vi import build_pattern_stats_chuan_vi, build_pattern_stats_tom_tat_vi


# ============================================================
# Runner safety helpers
# ============================================================
def runner_normalize_columns(df):
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
            "NgÃ y": "Ngay",
            "Ngày": "Ngay",
            "Ngay": "Ngay",

            "ChiÃ¡ÂºÂ¿n lÃÂ°Ã¡Â»Â£c": "Chien luoc",
            "Chiáº¿n lÆ°á»£c": "Chien luoc",
            "Chiến lược": "Chien luoc",
            "Chien luoc": "Chien luoc",

            "HÃ nh Äá»ng": "Hanh dong",
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


def runner_get_col(df, preferred, fallback=None):
    if df is None or df.empty:
        return fallback
    if preferred in df.columns:
        return preferred
    if fallback and fallback in df.columns:
        return fallback
    return preferred


def main():

    print("RUN BATCH TRADING ENGINE - KBS")
    print(f"SYSTEM VERSION: {SYSTEM_VERSION}")
    print("TIME:", now_vietnam())

    start_idx = load_state()
    if start_idx >= len(UNIVERSE):
        start_idx = 0

    end_idx = min(start_idx + BATCH_SIZE, len(UNIVERSE))
    batch = UNIVERSE[start_idx:end_idx]

    print(f"Batch: {start_idx} -> {end_idx} / {len(UNIVERSE)}")
    print("Codes:", batch)

    market_ret20 = get_market_ret20()
    current_market_regime = get_market_regime_from_cache(market_ret20)
    v10_learning.current_market_regime = current_market_regime
    v10_backfill_regime.current_market_regime = current_market_regime

    rows = []

    for i, symbol in enumerate(batch, 1):
        print(f"{i}/{len(batch)} Fetch {symbol}")
        result = None

        try:
            result = analyze_symbol(symbol, market_ret20)
            if result:
                rows.append(result)
                print("OK", symbol, result.get("Signal"), result.get("Action"), result.get("Score"))
            else:
                print("WARN", symbol, "not enough data")
        except Exception as e:
            print("ERR", symbol, repr(e))

        if result and result.get("Fetch Mode") == "API":
            time.sleep(API_SLEEP_SEC)
        else:
            time.sleep(CACHE_SLEEP_SEC)

    new_df = runner_normalize_columns(pd.DataFrame(rows))
    old_df = runner_normalize_columns(safe_read_csv(ALL_RESULT_PATH))

    if old_df is not None and not old_df.empty and "Ma" in old_df.columns:
        old_df = old_df[~old_df["Ma"].astype(str).isin(batch)].reset_index(drop=True)
        combined = runner_safe_concat([old_df, new_df])
    else:
        combined = new_df.copy()

    combined = runner_normalize_columns(combined)

    if combined is not None and not combined.empty and "Ma" in combined.columns:
        combined = combined.drop_duplicates(subset=["Ma"], keep="last").reset_index(drop=True)

    if combined is None or combined.empty:
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

    # Advanced AI filter
    combined = runner_normalize_columns(apply_advanced_ai_filter(combined, market_ret20))

    # Learning / OOS
    signal_history = append_signal_history(combined, market_ret20)
    signal_history = update_history_outcomes(signal_history)
    pattern_stats = build_pattern_stats(signal_history)
    walk_forward_stats = build_walk_forward_stats(signal_history)

    # Backfill / OOS stats
    backfill_history = build_backfill_history_from_cache(market_ret20)
    backfill_wf_stats = build_backfill_walk_forward_stats(backfill_history)
    walk_forward_stats = merge_walk_forward_sources(walk_forward_stats, backfill_wf_stats)

    combined = runner_normalize_columns(apply_history_learning(combined, pattern_stats, market_ret20))
    combined = runner_normalize_columns(apply_walk_forward_filter(combined, walk_forward_stats))

    # Regime filter
    learning_hist_for_regime = (
        backfill_history
        if 'backfill_history' in globals() and backfill_history is not None and not backfill_history.empty
        else signal_history
    )
    regime_stats = build_regime_stats(learning_hist_for_regime)
    combined = runner_normalize_columns(apply_regime_decay_filter(combined, regime_stats, current_market_regime))
    combined = runner_normalize_columns(safe_numeric_columns(combined))

    if "Win Probability" in combined.columns:
        combined["Win Probability"] = pd.to_numeric(combined["Win Probability"], errors="coerce").fillna(BASE_WIN_PROB)

    sort_by = [c for c in ["Regime Win Probability", "OOS Win Probability", "Win Probability", "AI Confidence", "Score"] if c in combined.columns]
    if sort_by:
        combined = combined.sort_values(sort_by, ascending=False).reset_index(drop=True)

    combined = runner_normalize_columns(combined)
    combined.to_csv(ALL_RESULT_PATH, index=False, encoding="utf-8-sig")

    # Coverage check
    try:
        valid_codes = set(combined["Ma"].dropna().astype(str)) & set(UNIVERSE) if "Ma" in combined.columns else set()
        missing_codes = sorted(set(UNIVERSE) - valid_codes)
        print(f"Coverage: {len(valid_codes)} / {len(UNIVERSE)} codes")
        if missing_codes:
            print("Missing codes:", missing_codes)
        else:
            print("OK: full coverage in all_signal_results.csv")
    except Exception as e:
        print("WARN: cannot check coverage:", repr(e))

    strategy_col = "Chien luoc" if "Chien luoc" in combined.columns else "Chiáº¿n lÆ°á»£c"

    raw_signals = combined[
        combined[strategy_col].isin([
            "MOMENTUM", "BOTTOM", "MOMENTUM_WATCH", "BOTTOM_WATCH", "WATCH"
        ])
    ].copy()
    raw_signals = runner_normalize_columns(raw_signals)
    raw_signals = raw_signals.sort_values("AI Confidence" if "AI Confidence" in raw_signals.columns else "Score", ascending=False)
    raw_signals.to_csv(RAW_SIGNAL_PATH, index=False, encoding="utf-8-sig")

    ai_risk = combined[
        (combined["Risk Status"] == "PASS") &
        (combined["Action"].isin(["BUY NOW", "WAIT", "WATCHLIST"]))
    ].copy()
    ai_risk = runner_normalize_columns(ai_risk)
    ai_risk = ai_risk.sort_values("AI Confidence" if "AI Confidence" in ai_risk.columns else "Score", ascending=False)
    ai_risk.to_csv(AI_RISK_PATH, index=False, encoding="utf-8-sig")

    bottom = ai_risk[
        ai_risk[strategy_col].isin(["BOTTOM", "BOTTOM_WATCH"])
    ].copy() if strategy_col in ai_risk.columns else pd.DataFrame()

    momentum = ai_risk[
        ai_risk[strategy_col].isin(["MOMENTUM", "MOMENTUM_WATCH"])
    ].copy() if strategy_col in ai_risk.columns else pd.DataFrame()

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
            "Risk Reason": "No qualified signal"
        }])
    else:
        keep = [
            "Ngay", "Ma", "Action", "Signal", "Chien luoc", "Score",
            "Momentum Score", "Bottom Score", "AI Confidence", "AI Grade", "AI Action",
            "Win Probability", "History Samples", "OOS Win Probability", "OOS Samples",
            "OOS Status", "Regime Win Probability", "Regime Samples", "Market Regime Now",
            "Final Action", "History Note", "Walk Forward Note", "Regime Note",
            "AI Reason", "AI Warning", "Risk Status", "Risk Reason",
            "RSI", "Close", "MA5", "MA20", "Ret5 %", "Ret10 %",
            "RS20", "Volume Ratio", "ADX", "ATR %", "Dist MA20 %"
        ]
        entry = entry[[c for c in keep if c in entry.columns]]

    entry = runner_normalize_columns(entry)
    entry.to_csv(ENTRY_PATH, index=False, encoding="utf-8-sig")

    tracker, action_plan = build_portfolio_and_action_plan(combined, ai_risk)
    tracker = runner_normalize_columns(tracker)
    action_plan = runner_normalize_columns(action_plan)

    wf_stats_disp, back_wf_stats_disp, regime_stats_disp, pattern_stats_disp = load_ai_evidence_tables()
    # V11 MARKET OVERLAY - lop phu, khong thay doi core V10
    try:
        print("CALLING V11 MARKET OVERLAY...")
        _market_score_v11 = 0

        # Neu runner co bien market_ret20 thi lay, neu khong co thi de 0
        try:
            _market_score_v11 = float(market_ret20)
        except Exception:
            _market_score_v11 = 0

        v11_combined, v11_market_summary_view = ap_dung_v11_market_overlay(
            combined,
            market_score=_market_score_v11,
            universe=UNIVERSE
        )
        v11_leader_view = tao_bang_v11_leader(v11_combined, limit=10)
        v11_downgrade_view = tao_bang_v11_bi_ha_hang(v11_combined, limit=20)
        print("V11 MARKET OVERLAY OK")
    except Exception as e:
        print("WARN: V11 market overlay error:", repr(e))
        v11_combined = combined.copy() if hasattr(combined, "copy") else combined
        v11_market_summary_view = pd.DataFrame([{
            "Chi tieu": "V11 Overlay",
            "Gia tri": "Loi nhung da bo qua de khong crash: " + repr(e)
        }])
        v11_leader_view = pd.DataFrame()
        v11_downgrade_view = pd.DataFrame()

    ai_summary_view = build_ai_summary_table(wf_stats_disp, back_wf_stats_disp, regime_stats_disp, pattern_stats_disp)
    top_patterns_view = build_top_proven_patterns(wf_stats_disp, back_wf_stats_disp, regime_stats_disp)

    # V11 PATTERN STATS VI - bang pattern de doc, co goi y hanh dong
    try:
        pattern_stats_chuan_view = build_pattern_stats_chuan_vi(back_wf_stats_disp, min_count=3, limit=30)
        pattern_stats_tom_tat_view = build_pattern_stats_tom_tat_vi(pattern_stats_chuan_view)
    except Exception as e:
        print("WARN: pattern stats vi error:", repr(e))
        pattern_stats_chuan_view = pd.DataFrame()
        pattern_stats_tom_tat_view = pd.DataFrame()

    # STABLE TOP CODES:
    # Use today's signals from combined + raw historical OOS stats from back_wf_stats_disp.
    # This is display-only. It does not change trading logic.
    try:
        top_codes_t2_view = build_top_codes_by_proven_pattern_stable(
            combined,
            back_wf_stats_disp,
            mode="T2",
            limit=20
        )
    except Exception as e:
        print("WARN: TOP CODES T+2 stable error:", repr(e))
        top_codes_t2_view = pd.DataFrame()

    try:
        top_codes_t5_view = build_top_codes_by_proven_pattern_stable(
            combined,
            back_wf_stats_disp,
            mode="T5",
            limit=20
        )
    except Exception as e:
        print("WARN: TOP CODES T+5 stable error:", repr(e))
        top_codes_t5_view = pd.DataFrame()

    try:
        pattern_codes_map_view = build_pattern_to_codes_map_stable(
            combined,
            back_wf_stats_disp,
            mode="ALL",
            limit=20
        )
    except Exception as e:
        print("WARN: PATTERN TO CODES MAP stable error:", repr(e))
        pattern_codes_map_view = pd.DataFrame()

    raw_view = make_dashboard_view(raw_signals, "raw")
    ai_view = make_dashboard_view(ai_risk, "ai")
    entry_view = make_dashboard_view(entry, "entry")
    tracker_view = make_dashboard_view(tracker, "tracker")
    action_view = make_dashboard_view(action_plan, "action")

    # FAIL ANALYSIS - Vietnamese diagnostic tables
    try:
        fail_summary_view = build_fail_analysis_summary(combined)
        fail_by_code_view = build_fail_analysis_by_code(combined, limit=30)
        fail_by_strategy_view = build_fail_analysis_by_strategy(combined)
    except Exception as e:
        print("WARN: fail analysis error:", repr(e))
        fail_summary_view = pd.DataFrame()
        fail_by_code_view = pd.DataFrame()
        fail_by_strategy_view = pd.DataFrame()

    ai_summary_html = ai_summary_view.to_html(index=False, escape=True)
    try:
        v11_market_summary_html = v11_market_summary_view.to_html(index=False, escape=True)
    except Exception:
        v11_market_summary_html = ""
    try:
        v11_leader_html = v11_leader_view.to_html(index=False, escape=True)
    except Exception:
        v11_leader_html = ""
    try:
        v11_downgrade_html = v11_downgrade_view.to_html(index=False, escape=True)
    except Exception:
        v11_downgrade_html = ""
    top_patterns_html = top_patterns_view.to_html(index=False, escape=True)
    pattern_stats_chuan_html = pattern_stats_chuan_view.to_html(index=False, escape=True)
    pattern_stats_tom_tat_html = pattern_stats_tom_tat_view.to_html(index=False, escape=True)
    top_codes_t2_html = top_codes_t2_view.to_html(index=False, escape=True)
    top_codes_t5_html = top_codes_t5_view.to_html(index=False, escape=True)
    pattern_codes_map_html = pattern_codes_map_view.to_html(index=False, escape=True)
    raw_html = raw_view.to_html(index=False, escape=True)
    ai_html = ai_view.to_html(index=False, escape=True)
    entry_html = entry_view.to_html(index=False, escape=True)
    tracker_html = tracker_view.to_html(index=False, escape=True)
    action_html = action_view.to_html(index=False, escape=True)
    fail_summary_html = fail_summary_view.to_html(index=False, escape=True)
    fail_by_code_html = fail_by_code_view.to_html(index=False, escape=True)
    fail_by_strategy_html = fail_by_strategy_view.to_html(index=False, escape=True)

    html_full = f"""
<html>
<head>
<meta charset="utf-8">
<title>Trading Dashboard</title>
{html_style()}
</head>
<body>

<h2>TRADING BOT ACTION CENTER</h2>
<p><b>Generated:</b> {now_vietnam()}</p>
<p><b>Data date:</b> {get_report_data_date(combined, entry, action_plan)}</p>
<p><b>Version:</b> {SYSTEM_VERSION}</p>
<p><b>Batch:</b> {start_idx} -> {end_idx} / {len(UNIVERSE)}</p>

<h3>AI TEST SUMMARY</h3>
{ai_summary_html}

<h3>DANH GIA THI TRUONG V11</h3>
{v11_market_summary_html}

<h3>V11 - TOP LEADER RS20</h3>
{v11_leader_html}

<h3>V11 - MA BI HA HANG DO BOI CANH THI TRUONG</h3>
{v11_downgrade_html}

<h3>TOP PROVEN PATTERNS</h3>
{top_patterns_html}

<h3>V11 - THONG KE MAU CHUAN DE DOC</h3>
{pattern_stats_chuan_html}

<h3>V11 - TOM TAT XEP HANG MAU</h3>
{pattern_stats_tom_tat_html}

<h3>TOP CODES T+2 - SHORT TRADE</h3>
{top_codes_t2_html}

<h3>TOP CODES T+5 - SWING</h3>
{top_codes_t5_html}

<h3>PATTERN TO CODES MAP</h3>
{pattern_codes_map_html}

<h3>RAW SIGNAL - ACTION VIEW</h3>
{raw_html}

<h3>AI FINAL - ACTION VIEW</h3>
{ai_html}

<h3>ENTRY PLAN</h3>
{entry_html}

<h3>PORTFOLIO</h3>
{tracker_html}

<h3>PHAN TICH LY DO BI LOAI - TONG HOP</h3>
{fail_summary_html}

<h3>PHAN TICH LY DO BI LOAI - THEO MA</h3>
{fail_by_code_html}

<h3>PHAN TICH LY DO BI LOAI - THEO CHIEN LUOC</h3>
{fail_by_strategy_html}

<h3>ACTION PLAN</h3>
{action_html}

</body>
</html>
"""

    with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
        f.write(html_full)

    send_telegram_alert(entry, action_plan, combined, tracker)

    next_start = end_idx
    if next_start >= len(UNIVERSE):
        next_start = 0

    save_state(next_start)

    print("CREATED OUTPUT FILES")
    print("Rows combined:", len(combined))
    print("Raw signals:", len(raw_signals))
    print("AI risk rows:", len(ai_risk))
    print("Bottom rows:", len(bottom))
    print("Momentum rows:", len(momentum))
    print("Entry rows:", len(entry))
    print("Portfolio rows:", len(tracker))
    print("Action plan rows:", len(action_plan))
    print("Next batch start:", next_start)


if __name__ == "__main__":
    main()
