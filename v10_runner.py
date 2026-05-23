# -*- coding: utf-8 -*-
"""
V10 Runner - Main trading engine
Refactored: modular, clean, easy to maintain
"""

import time
import pandas as pd
import numpy as np

# Config
from v10_config import *

# Core utilities
from v10_utils import (
    safe_read_csv, now_vietnam, load_state, save_state,
    safe_numeric_columns, runner_normalize_columns, runner_safe_concat,
    repair_mojibake
)

# Core modules
from v10_market_data import get_market_ret20
from v10_strategy import analyze_symbol
from v10_learning import (
    append_signal_history, update_history_outcomes, build_pattern_stats,
    build_walk_forward_stats, apply_history_learning, apply_walk_forward_filter,
    apply_advanced_ai_filter
)
from v10_backfill_regime import (
    build_backfill_history_from_cache, build_backfill_walk_forward_stats,
    merge_walk_forward_sources, build_regime_stats, apply_regime_decay_filter,
    get_market_regime_from_cache
)
from v10_output import (
    build_portfolio_and_action_plan, make_dashboard_view, html_style,
    get_report_data_date, load_ai_evidence_tables, build_ai_summary_table,
    build_top_proven_patterns, build_top_codes_by_proven_pattern_stable,
    build_pattern_to_codes_map_stable, build_fail_analysis_summary,
    build_fail_analysis_by_code, build_fail_analysis_by_strategy
)


# UI modules
from v10_ui_dashboard import (
    ui_split_buy_watch_red, ui_table_html, ui_full_v134_html, _ui_find_col,
    ui_compact_top_view, ui_top_sort
)
from v10_ui_style import ui_extra_style
from v10_telegram import send_telegram_alert
from v10_debug import print_ai_council_debug
from v10_intraday_export import safe_export_intraday_watchlist
from v10_soft_match import (
    build_v135_soft_history_match_view, build_v135_softmatch_top_view,
    add_sample_strength_column
)

# V11, V13 modules
from v11_market_overlay import ap_dung_v11_market_overlay, tao_bang_v11_leader, tao_bang_v11_bi_ha_hang
from v13_final_decision_vi import build_v13_final_decision_vi, build_v13_top_picks_vi
from v132_feature_pattern_engine_vi import build_v132_feature_pattern_view_vi, build_v132_top_feature_picks_vi
from v133_feature_pattern_no_empty_vi import build_v133_feature_pattern_view_vi, build_v133_top_picks_vi
from v134_ui_highlight_vi import build_v134_decision_ui_vi

# Global macro
try:
    from global_macro_layer import (
        run_global_macro_layer, apply_global_risk_to_decision,
        render_global_macro_html, render_global_macro_telegram
    )
    GLOBAL_MACRO_AVAILABLE = True
except ImportError:
    GLOBAL_MACRO_AVAILABLE = False
    run_global_macro_layer = None
    apply_global_risk_to_decision = None
    render_global_macro_html = None
    render_global_macro_telegram = None


def main():
    print("RUN BATCH TRADING ENGINE - KBS")
    print(f"SYSTEM VERSION: {SYSTEM_VERSION}")
    print("TIME:", now_vietnam())

    # ===== 1. BATCH PROCESSING =====
    start_idx = load_state()
    if start_idx >= len(UNIVERSE):
        start_idx = 0

    end_idx = min(start_idx + BATCH_SIZE, len(UNIVERSE))
    batch = UNIVERSE[start_idx:end_idx]

    print(f"Batch: {start_idx} -> {end_idx} / {len(UNIVERSE)}")
    print("Codes:", batch)

    market_ret20 = get_market_ret20()
    current_market_regime = get_market_regime_from_cache(market_ret20)

    rows = []
    for i, symbol in enumerate(batch, 1):
        print(f"{i}/{len(batch)} Fetch {symbol}")
        try:
            result = analyze_symbol(symbol, market_ret20)
            if result:
                rows.append(result)
                print("OK", symbol, result.get("Signal"), result.get("Action"), result.get("Score"))
        except Exception as e:
            print("ERR", symbol, repr(e))
        time.sleep(API_SLEEP_SEC if result and result.get("Fetch Mode") == "API" else CACHE_SLEEP_SEC)

    # ===== 2. COMBINE RESULTS =====
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

    # Fallback if empty
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

    # ===== 3. AI FILTERS & LEARNING =====
    needed_cols = ["Risk Status", "Action", "Chien luoc", "Score", "Ma"]
    for col in needed_cols:
        if col not in combined.columns:
            combined[col] = ""

    combined["Score"] = pd.to_numeric(combined["Score"], errors="coerce").fillna(0)

    combined = runner_normalize_columns(apply_advanced_ai_filter(combined, market_ret20))

    signal_history = append_signal_history(combined, market_ret20)
    signal_history = update_history_outcomes(signal_history)
    pattern_stats = build_pattern_stats(signal_history)
    walk_forward_stats = build_walk_forward_stats(signal_history)

    backfill_history = build_backfill_history_from_cache(market_ret20)
    backfill_wf_stats = build_backfill_walk_forward_stats(backfill_history)
    walk_forward_stats = merge_walk_forward_sources(walk_forward_stats, backfill_wf_stats)

    combined = runner_normalize_columns(apply_history_learning(combined, pattern_stats, market_ret20))
    combined = runner_normalize_columns(apply_walk_forward_filter(combined, walk_forward_stats))

    learning_hist_for_regime = backfill_history if backfill_history is not None and not backfill_history.empty else signal_history
    regime_stats = build_regime_stats(learning_hist_for_regime)
    combined = runner_normalize_columns(apply_regime_decay_filter(combined, regime_stats, current_market_regime))
    combined = runner_normalize_columns(safe_numeric_columns(combined))

    if "Win Probability" in combined.columns:
        combined["Win Probability"] = pd.to_numeric(combined["Win Probability"], errors="coerce").fillna(55.0)

    # Sort by confidence
    sort_by = [c for c in ["Regime Win Probability", "OOS Win Probability", "Win Probability", "AI Confidence", "Score"] if c in combined.columns]
    if sort_by:
        combined = combined.sort_values(sort_by, ascending=False).reset_index(drop=True)

    # ===== 4. SAVE COMBINED RESULTS =====
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

    # ===== 5. GENERATE OUTPUT FILES =====
    strategy_col = "Chien luoc" if "Chien luoc" in combined.columns else "Chiáº¿n lÆ°á»£c"

    raw_signals = combined[combined[strategy_col].isin(["MOMENTUM", "BOTTOM", "MOMENTUM_WATCH", "BOTTOM_WATCH", "WATCH"])].copy()
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

    # Bottom and Momentum
    bottom = ai_risk[ai_risk[strategy_col].isin(["BOTTOM", "BOTTOM_WATCH"])].copy() if strategy_col in ai_risk.columns else pd.DataFrame()
    momentum = ai_risk[ai_risk[strategy_col].isin(["MOMENTUM", "MOMENTUM_WATCH"])].copy() if strategy_col in ai_risk.columns else pd.DataFrame()

    bottom.to_csv(BOTTOM_PATH, index=False, encoding="utf-8-sig")
    momentum.to_csv(MOMENTUM_PATH, index=False, encoding="utf-8-sig")

    # Entry plan
    entry = ai_risk[ai_risk["Action"].isin(["BUY NOW", "WAIT", "WATCHLIST"])].copy()
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

    # Portfolio and action plan
    tracker, action_plan = build_portfolio_and_action_plan(combined, ai_risk)
    tracker = runner_normalize_columns(tracker)
    action_plan = runner_normalize_columns(action_plan)

    # ===== 6. AI EVIDENCE TABLES =====
    wf_stats_disp, back_wf_stats_disp, regime_stats_disp, pattern_stats_disp = load_ai_evidence_tables()

    # V11 MARKET OVERLAY
    try:
        print("CALLING V11 MARKET OVERLAY...")
        _market_score_v11 = float(market_ret20) if market_ret20 else 0
        v11_combined, v11_market_summary_view = ap_dung_v11_market_overlay(
            combined, market_score=_market_score_v11, universe=UNIVERSE
        )
        v11_leader_view = tao_bang_v11_leader(v11_combined, limit=10)
        v11_downgrade_view = tao_bang_v11_bi_ha_hang(v11_combined, limit=20)
        print("V11 MARKET OVERLAY OK")
    except Exception as e:
        print("WARN: V11 market overlay error:", repr(e))
        v11_market_summary_view = pd.DataFrame([{"Chi tieu": "V11 Overlay", "Gia tri": "Loi: " + repr(e)}])
        v11_leader_view = pd.DataFrame()
        v11_downgrade_view = pd.DataFrame()

    # AI Summary
    ai_summary_view = build_ai_summary_table(wf_stats_disp, back_wf_stats_disp, regime_stats_disp, pattern_stats_disp)
    top_patterns_view = build_top_proven_patterns(wf_stats_disp, back_wf_stats_disp, regime_stats_disp)

    # V13.3
    try:
        v133_feature_view = build_v133_feature_pattern_view_vi(combined, back_wf_stats_disp, limit=60)
        v133_top_feature_view = build_v133_top_picks_vi(v133_feature_view, limit=8)
        v133_feature_view = add_sample_strength_column(v133_feature_view, mode="hard")
        v133_top_feature_view = add_sample_strength_column(v133_top_feature_view, mode="hard")
        print("V13.3 FEATURE PATTERN OK")
    except Exception as e:
        print("WARN: V13.3 feature pattern error:", repr(e))
        v133_feature_view = pd.DataFrame([{"Trạng thái": "Lỗi V13.3", "Chi tiết": repr(e)}])
        v133_top_feature_view = pd.DataFrame()

    # V13.2
    try:
        v132_feature_view = build_v132_feature_pattern_view_vi(combined, back_wf_stats_disp, min_match_pct=60, limit=60)
        v132_top_feature_view = build_v132_top_feature_picks_vi(v132_feature_view, limit=8)
        print("V13.2 FEATURE PATTERN OK")
    except Exception as e:
        print("WARN: V13.2 feature pattern error:", repr(e))
        v132_feature_view = pd.DataFrame([{"Trạng thái": "Lỗi V13.2", "Chi tiết": repr(e)}])
        v132_top_feature_view = pd.DataFrame()

    # V13 FINAL DECISION
    try:
        _market_score_v13 = float(market_ret20) if market_ret20 else 0
        v13_final_view, v13_market_summary_view = build_v13_final_decision_vi(
            combined, back_wf_stats_disp, market_score=_market_score_v13, universe=UNIVERSE, limit=60
        )
        v13_top_picks_view = build_v13_top_picks_vi(v13_final_view, limit=8)
        print("V13 FINAL DECISION OK")
    except Exception as e:
        print("WARN: V13 final decision error:", repr(e))
        v13_final_view = pd.DataFrame([{"Trạng thái": "Lỗi V13", "Chi tiết": repr(e)}])
        v13_market_summary_view = pd.DataFrame()
        v13_top_picks_view = pd.DataFrame()

    # TOP CODES STABLE
    try:
        top_codes_t2_view = build_top_codes_by_proven_pattern_stable(combined, back_wf_stats_disp, mode="T2", limit=20)
        top_codes_t5_view = build_top_codes_by_proven_pattern_stable(combined, back_wf_stats_disp, mode="T5", limit=20)
        pattern_codes_map_view = build_pattern_to_codes_map_stable(combined, back_wf_stats_disp, mode="ALL", limit=20)
    except Exception as e:
        print("WARN: TOP CODES stable error:", repr(e))
        top_codes_t2_view = top_codes_t5_view = pattern_codes_map_view = pd.DataFrame()

    # Dashboard views
    raw_view = make_dashboard_view(raw_signals, "raw")
    ai_view = make_dashboard_view(ai_risk, "ai")
    entry_view = make_dashboard_view(entry, "entry")
    tracker_view = make_dashboard_view(tracker, "tracker")
    action_view = make_dashboard_view(action_plan, "action")

    # FAIL ANALYSIS
    try:
        fail_summary_view = build_fail_analysis_summary(combined)
        fail_by_code_view = build_fail_analysis_by_code(combined, limit=30)
        fail_by_strategy_view = build_fail_analysis_by_strategy(combined)
    except Exception as e:
        print("WARN: fail analysis error:", repr(e))
        fail_summary_view = fail_by_code_view = fail_by_strategy_view = pd.DataFrame()

    # Convert to HTML
    ai_summary_html = ai_summary_view.to_html(index=False, escape=True)
    v11_market_summary_html = v11_market_summary_view.to_html(index=False, escape=True) if not v11_market_summary_view.empty else ""
    v11_leader_html = v11_leader_view.to_html(index=False, escape=True) if not v11_leader_view.empty else ""
    v11_downgrade_html = v11_downgrade_view.to_html(index=False, escape=True) if not v11_downgrade_view.empty else ""
    top_patterns_html = top_patterns_view.to_html(index=False, escape=True) if not top_patterns_view.empty else ""
    v133_feature_html = v133_feature_view.to_html(index=False, escape=True) if not v133_feature_view.empty else ""
    v133_top_feature_html = v133_top_feature_view.to_html(index=False, escape=True) if not v133_top_feature_view.empty else ""
    v132_feature_html = v132_feature_view.to_html(index=False, escape=True) if not v132_feature_view.empty else ""
    v132_top_feature_html = v132_top_feature_view.to_html(index=False, escape=True) if not v132_top_feature_view.empty else ""
    v13_market_summary_html = v13_market_summary_view.to_html(index=False, escape=True) if not v13_market_summary_view.empty else ""
    v13_top_picks_html = v13_top_picks_view.to_html(index=False, escape=True) if not v13_top_picks_view.empty else ""
    v13_final_html = v13_final_view.to_html(index=False, escape=True) if not v13_final_view.empty else ""
    top_codes_t2_html = top_codes_t2_view.to_html(index=False, escape=True) if not top_codes_t2_view.empty else ""
    top_codes_t5_html = top_codes_t5_view.to_html(index=False, escape=True) if not top_codes_t5_view.empty else ""
    pattern_codes_map_html = pattern_codes_map_view.to_html(index=False, escape=True) if not pattern_codes_map_view.empty else ""
    raw_html = raw_view.to_html(index=False, escape=True)
    ai_html = ai_view.to_html(index=False, escape=True)
    entry_html = entry_view.to_html(index=False, escape=True)
    tracker_html = tracker_view.to_html(index=False, escape=True)
    action_html = action_view.to_html(index=False, escape=True)
    fail_summary_html = fail_summary_view.to_html(index=False, escape=True) if not fail_summary_view.empty else ""
    fail_by_code_html = fail_by_code_view.to_html(index=False, escape=True) if not fail_by_code_view.empty else ""
    fail_by_strategy_html = fail_by_strategy_view.to_html(index=False, escape=True) if not fail_by_strategy_view.empty else ""

    # GLOBAL MACRO
    global_macro_html = ""
    global_macro_text = ""
    global_macro_result = None
    try:
        if GLOBAL_MACRO_AVAILABLE and run_global_macro_layer is not None:
            global_macro_result = run_global_macro_layer()
            global_macro_html = render_global_macro_html(global_macro_result)
            global_macro_text = render_global_macro_telegram(global_macro_result)
            print("GLOBAL MACRO LAYER OK")
        else:
            global_macro_html = "<div class='ui-note'>GLOBAL MACRO MODE: module chưa được bật</div>"
    except Exception as e:
        print("WARN: GLOBAL MACRO layer error:", repr(e))
        global_macro_html = "<div class='ui-note'>GLOBAL MACRO MODE lỗi, bỏ qua</div>"

    # V13.5 SOFT MATCH
    v135_softmatch_top_html = ""
    v135_soft_match_html = ""
    try:
        v135_soft_match_view = build_v135_soft_history_match_view(
            combined, backfill_history, limit=60, lookback_years=3, min_match_pct=70
        )
        v135_soft_match_view = add_sample_strength_column(v135_soft_match_view, mode="soft")
        v135_softmatch_top_view = build_v135_softmatch_top_view(v135_soft_match_view, limit=15)
        v135_softmatch_top_html = ui_table_html(v135_softmatch_top_view, "top-table")
        v135_soft_match_html = v135_soft_match_view.to_html(index=False, escape=True)
        print("V13.5 SOFT HISTORY MATCH OK")
    except Exception as e:
        print("WARN: V13.5 soft history match error:", repr(e))
        v135_softmatch_top_html = "<p>Lỗi V13.5 soft match</p>"
        v135_soft_match_html = "<p>Lỗi V13.5 soft match</p>"

    # V13.4 UI HIGHLIGHT
    try:
        v134_ui_view = build_v134_decision_ui_vi(v133_feature_view, limit=30)
        # Downgrade BUY NOW khi T+5 âm
        t5_col_ui = _ui_find_col(v134_ui_view, ["Lợi TB T+5 %", "Loi TB T+5 %", "Lợi T+5 %", "Loi T+5 %"])
        if t5_col_ui is not None:
            action_col_ui = _ui_find_col(v134_ui_view, ["Hành động hiện tại", "Hanh dong hien tai", "Action"])
            if action_col_ui is not None:
                action_text = v134_ui_view[action_col_ui].astype(str).str.upper()
                t5_vals = pd.to_numeric(v134_ui_view[t5_col_ui], errors="coerce")
                mask = action_text.str.contains("BUY NOW", na=False) & (t5_vals < 0)
                v134_ui_view.loc[mask, action_col_ui] = "WATCHLIST"

        # Apply global macro risk
        try:
            if global_macro_result is not None and apply_global_risk_to_decision is not None:
                v134_ui_view = apply_global_risk_to_decision(v134_ui_view, global_macro_result, action_col="Hành động hiện tại")
        except Exception as e:
            print("WARN: apply global macro to V13.4 UI failed:", repr(e))

        v134_ui_view = ui_top_sort(v134_ui_view)
        v134_buy_real_view, v134_watch_top_view, v134_red_top_view = ui_split_buy_watch_red(v134_ui_view)

        # Export for Render
        safe_export_intraday_watchlist(v134_buy_real_view, v134_watch_top_view, _ui_find_col)

        v134_buy_real_html = ui_table_html(v134_buy_real_view, "top-table")
        v134_watch_top_html = ui_table_html(v134_watch_top_view, "top-table")
        v134_red_top_html = ui_table_html(v134_red_top_view, "top-table")
        v134_ui_html = ui_full_v134_html(v134_ui_view)
    except Exception as e:
        print("WARN: V13.4 UI error:", repr(e))
        v134_buy_real_html = ""
        v134_watch_top_html = ""
        v134_red_top_html = ""
        v134_ui_html = f"<p>LOI V13.4 UI: {repr(e)}</p>"

    # ===== 7. BUILD HTML DASHBOARD =====
    html_full = f"""
<html>
<head>
<meta charset="utf-8">
<title>Trading Dashboard</title>
{html_style()}
{ui_extra_style()}
</head>
<body>

<h2>TRADING BOT ACTION CENTER</h2>
<p><b>Generated:</b> {now_vietnam()}</p>
<p><b>Data date:</b> {get_report_data_date(combined, entry, action_plan)}</p>
<p><b>Version:</b> {SYSTEM_VERSION}</p>
<p><b>Batch:</b> {start_idx} -> {end_idx} / {len(UNIVERSE)}</p>

<div class="ui-note">Bản này tích hợp GLOBAL MACRO MODE ở đầu dashboard. Macro chỉ hạ cấp rủi ro khi Risk Off/Panic, không tự nâng WATCH lên BUY.</div>

<div class="ui-note">Flow đọc dashboard: 0) Global Macro → 1) Market regime VN → 2) RS20 leaders → 3) TOP MUA THẬT → 4) TOP THEO DÕI → 5) V13.3 history → 6) V13.5 soft match → 7) kiểm tra bảng đầy đủ.</div>

<h3>0. GLOBAL MACRO MODE - LIÊN THỊ TRƯỜNG</h3>
{global_macro_html}

<h3>1. MARKET REGIME - BỐI CẢNH THỊ TRƯỜNG VN</h3>
<h3>DANH GIA THI TRUONG V11</h3>
{v11_market_summary_html}

<h3>V13 - TOM TAT THI TRUONG THAT / AO</h3>
{v13_market_summary_html}

<h3>2. RS20 LEADERS - MÃ KHỎE HƠN THỊ TRƯỜNG</h3>
<h3>V11 - TOP LEADER RS20</h3>
{v11_leader_html}

<h3>V11 - MA BI HA HANG DO BOI CANH THI TRUONG</h3>
{v11_downgrade_html}

<div class="top-card top-green">
<h3>3. TOP MUA THẬT - ƯU TIÊN CAO</h3>
{v134_buy_real_html}
</div>

<div class="top-card top-green">
<h3>4. TOP THEO DÕI - CHƯA MUA VỘI</h3>
{v134_watch_top_html}
</div>

<h3>5. V13.3 HISTORY - PATTERN CỨNG</h3>
<h3>V13.3 - TOP MA GAN MAU LICH SU NHAT</h3>
{v133_top_feature_html}
<h3>V13.3 - FEATURE PATTERN</h3>
{v133_feature_html}

<h3>6. V13.5 SOFT MATCH - MẪU MỀM 1-3 NĂM</h3>
<div class="top-card top-green">
<h3>TOP MATCH MEM DANG THEO DOI</h3>
{v135_softmatch_top_html}
</div>
<h3>V13.5 - MATCH MEM DU LIEU QUA KHU 1-3 NAM</h3>
{v135_soft_match_html}

<div class="top-card top-red">
<h3>7. TOP ĐỎ - RỦI RO / KHÔNG ƯU TIÊN</h3>
{v134_red_top_html}
</div>

<h3>BẢNG ĐẦY ĐỦ ĐỂ ĐỐI CHIẾU</h3>
<h3>V13.4 - BANG QUYET DINH TU DONG</h3>
{v134_ui_html}

<h3>AI TEST SUMMARY</h3>
{ai_summary_html}
<h3>TOP PROVEN PATTERNS</h3>
{top_patterns_html}
<h3>V13.2 - FEATURE BASED TOP MA</h3>
{v132_top_feature_html}
<h3>V13.2 - FEATURE BASED PATTERN MATCH</h3>
{v132_feature_html}
<h3>V13 - TOP QUYET DINH CUOI</h3>
{v13_top_picks_html}
<h3>V13 - DO TIN CAY LICH SU CO TRONG SO</h3>
{v13_final_html}
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

    # ===== 8. TELEGRAM ALERT =====
    send_telegram_alert(entry, action_plan, combined, tracker,
                        v134_buy_real_view, v134_watch_top_view,
                        global_macro_text, DASHBOARD_PATH)

    # ===== 9. AI COUNCIL DEBUG =====
    print_ai_council_debug(combined, repair_mojibake)

    # ===== 10. SAVE STATE =====
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
