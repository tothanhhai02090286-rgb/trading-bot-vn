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
import html as _html
from v11_market_overlay import ap_dung_v11_market_overlay, tao_bang_v11_leader, tao_bang_v11_bi_ha_hang
from v13_final_decision_vi import build_v13_final_decision_vi, build_v13_top_picks_vi
from v132_feature_pattern_engine_vi import build_v132_feature_pattern_view_vi, build_v132_top_feature_picks_vi
from v133_feature_pattern_no_empty_vi import build_v133_feature_pattern_view_vi, build_v133_top_picks_vi
from v134_ui_highlight_vi import build_v134_decision_ui_vi, dataframe_to_highlight_html

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



# ============================================================
# UI SAFE TOP TABLES - display only, do not change trading logic
# ============================================================
def _ui_find_col(df, candidates):
    if df is None or getattr(df, "empty", True):
        return None
    cols = list(df.columns)
    lower_map = {str(c).lower().strip(): c for c in cols}
    for name in candidates:
        key = str(name).lower().strip()
        if key in lower_map:
            return lower_map[key]
    for c in cols:
        text = str(c).lower()
        for name in candidates:
            if str(name).lower() in text:
                return c
    return None


def _ui_action_rank(text):
    """Display-only priority. Smaller number = shown first."""
    t = str(text).upper()
    if "BUY NOW" in t or "MUA" in t:
        return 1
    if "WATCHLIST" in t or "THEO DÕI" in t or "THEO DOI" in t or "GIỮ" in t or "GIU" in t:
        return 2
    if "WAIT" in t or "CHỜ" in t or "CHO" in t or "KHÔNG ƯU TIÊN" in t or "KHONG UU TIEN" in t:
        return 3
    if "SKIP" in t or "BỎ QUA" in t or "BO QUA" in t:
        return 4
    return 9


def _ui_risk_rank(text):
    """Display-only risk priority. Smaller number = shown first."""
    t = str(text).upper()
    if "PASS" in t:
        return 1
    if "FAIL" in t:
        return 2
    return 9


def _ui_text_for_cols(out, col_names):
    text = pd.Series("", index=out.index, dtype="object")
    for col in col_names:
        if col is not None:
            text = text + " " + out[col].astype(str)
    return text


def _ui_top_sort(df):
    """Sort only the dashboard display, not the trading/output logic.
    Priority: Action -> Risk -> AI -> Score -> historical confidence.
    """
    if df is None or df.empty:
        return df
    out = df.copy()

    action_col = _ui_find_col(out, ["Hành động hiện tại", "Hanh dong hien tai", "Action"])
    decision_col = _ui_find_col(out, ["QUYẾT ĐỊNH TỰ ĐỘNG", "Quyet dinh tu dong", "Final Action"])
    risk_col = _ui_find_col(out, ["Risk", "Risk Status"])

    action_text = _ui_text_for_cols(out, [action_col, decision_col])
    risk_text = _ui_text_for_cols(out, [risk_col])

    out["__ui_action_rank"] = action_text.map(_ui_action_rank)
    out["__ui_risk_rank"] = risk_text.map(_ui_risk_rank)

    numeric_priority = [
        ["AI", "AI Confidence"],
        ["Score"],
        ["Độ tin cậy lịch sử", "Do tin cay lich su", "Điểm lịch sử", "Diem lich su"],
        ["Mức khớp mẫu %", "Muc khop mau %"],
        ["Tỷ lệ thắng", "Ty le thang", "Win Probability"],
        ["Lợi T+5 %", "Loi T+5 %"],
        ["Lợi T+2 %", "Loi T+2 %"],
    ]

    sort_cols = ["__ui_action_rank", "__ui_risk_rank"]
    ascending = [True, True]
    for names in numeric_priority:
        col = _ui_find_col(out, names)
        if col is not None and col not in sort_cols:
            out[col] = pd.to_numeric(out[col], errors="coerce")
            sort_cols.append(col)
            ascending.append(False)

    out = out.sort_values(sort_cols, ascending=ascending, na_position="last").reset_index(drop=True)
    return out.drop(columns=["__ui_action_rank", "__ui_risk_rank"], errors="ignore")


def _ui_compact_top_view(df, limit=10):
    if df is None or df.empty:
        return pd.DataFrame([{"Trạng thái": "Không có mã phù hợp"}])
    out = _ui_top_sort(df).head(limit).copy()
    keep_candidates = [
        ["Mã", "Ma"],
        ["Giá", "Close"],
        ["QUYẾT ĐỊNH TỰ ĐỘNG", "Quyet dinh tu dong", "Final Action", "Action"],
        ["Hành động hiện tại", "Hanh dong hien tai", "Action"],
        ["Strategy", "Chiến lược", "Chien luoc"],
        ["Risk"],
        ["Độ tin cậy lịch sử", "Do tin cay lich su"],
        ["Mức khớp mẫu %", "Muc khop mau %"],
        ["Tỷ lệ thắng", "Ty le thang", "Win Probability"],
        ["Lợi T+2 %", "Loi T+2 %"],
        ["Lợi T+5 %", "Loi T+5 %"],
        ["AI", "AI Confidence"],
        ["Score"],
    ]
    keep = []
    for names in keep_candidates:
        col = _ui_find_col(out, names)
        if col is not None and col not in keep:
            keep.append(col)
    if keep:
        out = out[keep]
    return out


def _ui_split_green_red(df):
    if df is None or getattr(df, "empty", True):
        return pd.DataFrame(), pd.DataFrame()
    out = df.copy()
    action_col = _ui_find_col(out, ["Hành động hiện tại", "Hanh dong hien tai", "Action"])
    decision_col = _ui_find_col(out, ["QUYẾT ĐỊNH TỰ ĐỘNG", "Quyet dinh tu dong", "Final Action"])
    text = pd.Series("", index=out.index, dtype="object")
    for col in [action_col, decision_col]:
        if col is not None:
            text = text + " " + out[col].astype(str).str.upper()
    green_mask = text.str.contains("BUY NOW|MUA|GIỮ|GIU|WATCHLIST", na=False)
    red_mask = text.str.contains("SKIP|BỎ QUA|BO QUA|KHÔNG|KHONG|WAIT", na=False) & ~green_mask
    green = _ui_compact_top_view(out[green_mask].copy(), limit=10)
    red = _ui_compact_top_view(out[red_mask].copy(), limit=10)
    return green, red


def _ui_table_html(df, css_class=""):
    try:
        return df.to_html(index=False, escape=True, classes=css_class)
    except Exception as e:
        return f"<p>Không tạo được bảng UI: {repr(e)}</p>"



def _ui_row_type(row):
    text = " ".join([str(x).upper() for x in row.values])
    if ("BUY NOW" in text) or ("MUA" in text) or ("WATCHLIST" in text) or ("GIỮ" in text) or ("GIU" in text):
        return "green"
    if ("SKIP" in text) or ("BỎ QUA" in text) or ("BO QUA" in text) or ("KHÔNG" in text) or ("KHONG" in text) or ("WAIT" in text):
        return "red"
    return "neutral"


def _ui_full_v134_html(df):
    """Render V13.4 full table with symbol badge on the original table.
    Display only: does not change data or trading logic.
    """
    try:
        if df is None or getattr(df, "empty", True):
            return "<p>Không có dữ liệu V13.4</p>"
        out = df.copy()
        cols = list(out.columns)
        ma_col = _ui_find_col(out, ["Mã", "Ma"])
        html_parts = ['<div class="v134-scroll"><table class="v134-full-table">']
        html_parts.append('<thead><tr>')
        for c in cols:
            html_parts.append(f'<th>{_html.escape(str(c))}</th>')
        html_parts.append('</tr></thead><tbody>')
        for _, row in out.iterrows():
            rtype = _ui_row_type(row)
            html_parts.append(f'<tr class="v134-row-{rtype}">')
            for c in cols:
                val = "" if pd.isna(row[c]) else str(row[c])
                safe = _html.escape(val)
                if ma_col is not None and c == ma_col:
                    html_parts.append(f'<td class="v134-symbol-cell"><span class="v134-symbol-badge v134-symbol-{rtype}">{safe}</span></td>')
                else:
                    html_parts.append(f'<td>{safe}</td>')
            html_parts.append('</tr>')
        html_parts.append('</tbody></table></div>')
        return "".join(html_parts)
    except Exception as e:
        return f"<p>LOI TAO BANG V13.4 FULL UI: {_html.escape(repr(e))}</p>"


def ui_extra_style():
    return """
<style>
body { font-size: 13px; }
.ui-note { padding: 10px 12px; border-radius: 10px; background: #111827; color: #e5e7eb; margin: 8px 0 14px 0; }
.top-card { margin: 14px 0 22px 0; padding: 12px; border-radius: 12px; overflow-x: auto; }
.top-green { background: #062f22; border: 1px solid #16a34a; }
.top-red { background: #3a0b0b; border: 1px solid #dc2626; }
.top-card h3 { margin-top: 0; color: #ffffff; }
.top-card table { width: 100%; border-collapse: collapse; font-size: 12px; }
.top-card th { position: sticky; top: 0; background: #111827; color: #ffffff; }
.top-card td, .top-card th { padding: 7px 8px; border: 1px solid rgba(255,255,255,0.14); white-space: nowrap; }
.top-card td { color: #f9fafb; font-weight: 600; }
.top-card td:first-child {
  font-size: 15px;
  font-weight: 900;
  letter-spacing: 0.7px;
  text-align: center;
  min-width: 54px;
  border-radius: 8px;
  position: sticky;
  left: 0;
  z-index: 2;
}
.top-card th:first-child {
  position: sticky;
  left: 0;
  z-index: 3;
}
.top-green td:first-child {
  color: #ffffff;
  background: linear-gradient(135deg, #16a34a, #065f46);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.35), 0 0 8px rgba(34,197,94,0.35);
}
.top-red td:first-child {
  color: #ffffff;
  background: linear-gradient(135deg, #dc2626, #7f1d1d);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.28), 0 0 8px rgba(239,68,68,0.35);
}
.full-note { color: #d1d5db; font-size: 12px; margin-top: -6px; }

.v134-scroll { overflow-x: auto; width: 100%; }
.v134-full-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.v134-full-table th { position: sticky; top: 0; background: #111827; color: #ffffff; z-index: 1; }
.v134-full-table td, .v134-full-table th { padding: 8px 8px; border: 1px solid rgba(255,255,255,0.13); vertical-align: middle; }
.v134-full-table td { color: #f3f4f6; font-weight: 600; }
.v134-row-green { background: #063b2a !important; }
.v134-row-red { background: #401010 !important; }
.v134-row-neutral { background: #151923 !important; }
.v134-symbol-cell { position: sticky; left: 0; z-index: 2; background: inherit !important; text-align: center; min-width: 68px; }
.v134-full-table th:first-child { position: sticky; left: 0; z-index: 3; }
.v134-symbol-badge { display: inline-block; min-width: 48px; padding: 7px 10px; border-radius: 9px; font-size: 15px; font-weight: 900; letter-spacing: 0.8px; color: #ffffff; }
.v134-symbol-green { background: linear-gradient(135deg, #22c55e, #047857); box-shadow: 0 0 10px rgba(34,197,94,0.55), inset 0 0 0 1px rgba(255,255,255,0.35); }
.v134-symbol-red { background: linear-gradient(135deg, #ef4444, #7f1d1d); box-shadow: 0 0 10px rgba(239,68,68,0.55), inset 0 0 0 1px rgba(255,255,255,0.28); }
.v134-symbol-neutral { background: linear-gradient(135deg, #64748b, #334155); box-shadow: 0 0 8px rgba(148,163,184,0.35), inset 0 0 0 1px rgba(255,255,255,0.22); }

</style>
"""


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

    # V13.3 FEATURE PATTERN PRO - Không trả về rỗng
    try:
        v133_feature_view = build_v133_feature_pattern_view_vi(combined, back_wf_stats_disp, limit=60)
        v133_top_feature_view = build_v133_top_picks_vi(v133_feature_view, limit=8)
        print("V13.3 FEATURE PATTERN NO EMPTY OK")
    except Exception as e:
        print("WARN: V13.3 feature pattern error:", repr(e))
        v133_feature_view = pd.DataFrame([{"Trạng thái": "Lỗi V13.3 nhưng đã bỏ qua để không crash", "Chi tiết": repr(e)}])
        v133_top_feature_view = pd.DataFrame()


    # V13.2 FEATURE-BASED PATTERN ENGINE - Cách 2
    try:
        v132_feature_view = build_v132_feature_pattern_view_vi(combined, back_wf_stats_disp, min_match_pct=60, limit=60)
        v132_top_feature_view = build_v132_top_feature_picks_vi(v132_feature_view, limit=8)
        print("V13.2 FEATURE PATTERN OK")
    except Exception as e:
        print("WARN: V13.2 feature pattern error:", repr(e))
        v132_feature_view = pd.DataFrame([{"Trạng thái": "Lỗi V13.2 nhưng đã bỏ qua để không crash", "Chi tiết": repr(e)}])
        v132_top_feature_view = pd.DataFrame()


    # V13 FINAL DECISION - Market thật/ảo + Pattern weighted riêng Momentum/Bottom
    try:
        _market_score_v13 = 0
        try:
            _market_score_v13 = float(market_ret20)
        except Exception:
            _market_score_v13 = 0

        v13_final_view, v13_market_summary_view = build_v13_final_decision_vi(
            combined,
            back_wf_stats_disp,
            market_score=_market_score_v13,
            universe=UNIVERSE,
            limit=60
        )
        v13_top_picks_view = build_v13_top_picks_vi(v13_final_view, limit=8)
        print("V13 FINAL DECISION OK")
    except Exception as e:
        print("WARN: V13 final decision error:", repr(e))
        v13_final_view = pd.DataFrame([{"Trạng thái": "Lỗi V13 nhưng đã bỏ qua để không crash", "Chi tiết": repr(e)}])
        v13_market_summary_view = pd.DataFrame()
        v13_top_picks_view = pd.DataFrame()


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
    try:
        v133_feature_html = v133_feature_view.to_html(index=False, escape=True)
    except Exception:
        v133_feature_html = ""
    try:
        v133_top_feature_html = v133_top_feature_view.to_html(index=False, escape=True)
    except Exception:
        v133_top_feature_html = ""
    try:
        v132_feature_html = v132_feature_view.to_html(index=False, escape=True)
    except Exception:
        v132_feature_html = ""
    try:
        v132_top_feature_html = v132_top_feature_view.to_html(index=False, escape=True)
    except Exception:
        v132_top_feature_html = ""
    try:
        v13_market_summary_html = v13_market_summary_view.to_html(index=False, escape=True)
    except Exception:
        v13_market_summary_html = ""
    try:
        v13_top_picks_html = v13_top_picks_view.to_html(index=False, escape=True)
    except Exception:
        v13_top_picks_html = ""
    try:
        v13_final_html = v13_final_view.to_html(index=False, escape=True)
    except Exception:
        v13_final_html = ""
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
    # ===== UI HIGHLIGHT V13.4 =====
    try:
        v134_ui_view = build_v134_decision_ui_vi(v133_feature_view, limit=30)
        v134_ui_view = _ui_top_sort(v134_ui_view)
        v134_green_top_view, v134_red_top_view = _ui_split_green_red(v134_ui_view)
        v134_green_top_html = _ui_table_html(v134_green_top_view, "top-table")
        v134_red_top_html = _ui_table_html(v134_red_top_view, "top-table")
        v134_ui_html = _ui_full_v134_html(v134_ui_view)
    except Exception as e:
        v134_green_top_html = ""
        v134_red_top_html = ""
        v134_ui_html = f"<p>LOI V13.4 UI: {repr(e)}</p>"
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

<div class="ui-note">Bản này chỉ thêm bảng TOP ở đầu dashboard và làm nổi bật tên mã theo màu xanh/đỏ. Logic lọc và file output không đổi.</div>

<div class="top-card top-green">
<h3>TOP XANH - ƯU TIÊN THEO DÕI / MUA</h3>
<p class="full-note">Lấy từ bảng V13.4, ưu tiên theo Action → Risk → AI → Score → lịch sử.</p>
{v134_green_top_html}
</div>

<div class="top-card top-red">
<h3>TOP ĐỎ - RỦI RO / KHÔNG ƯU TIÊN</h3>
<p class="full-note">Lấy từ bảng V13.4, cũng sắp xếp cùng chuẩn Action → Risk → AI → Score → lịch sử.</p>
{v134_red_top_html}
</div>

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

<h3>V13 - TOM TAT THI TRUONG THAT / AO</h3>
{v13_market_summary_html}

<h3>V13.4 - BANG QUYET DINH TU DONG</h3>
{v134_ui_html}

<h3>V13.3 - TOP MA GAN MAU LICH SU NHAT</h3>
{v133_top_feature_html}

<h3>V13.3 - FEATURE PATTERN KHONG TRA VE RONG</h3>
{v133_feature_html}

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
