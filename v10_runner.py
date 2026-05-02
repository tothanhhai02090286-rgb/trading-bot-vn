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


def main():

    print("ð RUN BATCH TRADING ENGINE - KBS")
    print(f"ð SYSTEM VERSION: {SYSTEM_VERSION}")
    print("â°", now_vietnam())

    start_idx = load_state()
    if start_idx >= len(UNIVERSE):
        start_idx = 0

    end_idx = min(start_idx + BATCH_SIZE, len(UNIVERSE))
    batch = UNIVERSE[start_idx:end_idx]

    print(f"ð Batch: {start_idx} -> {end_idx} / {len(UNIVERSE)}")
    print("ð MÃ£:", batch)

    market_ret20 = get_market_ret20()
    current_market_regime = get_market_regime_from_cache(market_ret20)
    v10_learning.current_market_regime = current_market_regime
    v10_backfill_regime.current_market_regime = current_market_regime

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

    wf_stats_disp, back_wf_stats_disp, regime_stats_disp, pattern_stats_disp = load_ai_evidence_tables()
    ai_summary_view = build_ai_summary_table(wf_stats_disp, back_wf_stats_disp, regime_stats_disp, pattern_stats_disp)
    top_patterns_view = build_top_proven_patterns(wf_stats_disp, back_wf_stats_disp, regime_stats_disp)

    raw_view = make_dashboard_view(raw_signals, "raw")
    ai_view = make_dashboard_view(ai_risk, "ai")
    entry_view = make_dashboard_view(entry, "entry")
    tracker_view = make_dashboard_view(tracker, "tracker")
    action_view = make_dashboard_view(action_plan, "action")

    ai_summary_html = ai_summary_view.to_html(index=False, escape=True)
    top_patterns_html = top_patterns_view.to_html(index=False, escape=True)
    raw_html = raw_view.to_html(index=False, escape=True)
    ai_html = ai_view.to_html(index=False, escape=True)
    entry_html = entry_view.to_html(index=False, escape=True)
    tracker_html = tracker_view.to_html(index=False, escape=True)
    action_html = action_view.to_html(index=False, escape=True)

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

    <h3>TOP PROVEN PATTERNS</h3>
    {top_patterns_html}

    <h3>RAW SIGNAL - ACTION VIEW</h3>
    {raw_html}

    <h3>AI FINAL - ACTION VIEW</h3>
    {ai_html}

    <h3>ENTRY PLAN</h3>
    {entry_html}

    <h3>PORTFOLIO</h3>
    {tracker_html}

    <h3>ACTION PLAN</h3>
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



if __name__ == "__main__":
    main()
