# -*- coding: utf-8 -*-
import pandas as pd
import html as _html


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


def ui_top_sort(df):
    """Sort only the dashboard display"""
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
        ["Lợi TB T+5 %", "Loi TB T+5 %", "Lợi T+5 %", "Loi T+5 %"],
        ["Lợi TB T+2 %", "Loi TB T+2 %", "Lợi T+2 %", "Loi T+2 %"],
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


def ui_compact_top_view(df, limit=10):
    if df is None or df.empty:
        return pd.DataFrame([{"Trạng thái": "Không có mã phù hợp"}])
    out = ui_top_sort(df).head(limit).copy()
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
        ["Lợi TB T+2 %", "Loi TB T+2 %", "Lợi T+2 %", "Loi T+2 %"],
        ["Lợi TB T+5 %", "Loi TB T+5 %", "Lợi T+5 %", "Loi T+5 %"],
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


def ui_split_buy_watch_red(df):
    """Split into TOP MUA THẬT, TOP THEO DÕI, TOP ĐỎ"""
    if df is None or getattr(df, "empty", True):
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    out = df.copy()
    action_col = _ui_find_col(out, ["Hành động hiện tại", "Hanh dong hien tai", "Action"])
    decision_col = _ui_find_col(out, ["QUYẾT ĐỊNH TỰ ĐỘNG", "Quyet dinh tu dong", "Final Action"])
    risk_col = _ui_find_col(out, ["Risk", "Risk Status"])
    t2_col = _ui_find_col(out, ["Lợi TB T+2 %", "Loi TB T+2 %", "Lợi T+2 %", "Loi T+2 %"])
    t5_col = _ui_find_col(out, ["Lợi TB T+5 %", "Loi TB T+5 %", "Lợi T+5 %", "Loi T+5 %"])
    hist_col = _ui_find_col(out, ["Độ tin cậy lịch sử", "Do tin cay lich su"])
    hist_score_col = _ui_find_col(out, ["Điểm lịch sử", "Diem lich su"])
    reason_col = _ui_find_col(out, ["LÝ DO CHI TIẾT", "Ly do chi tiet", "Lý do", "Ly do"])

    action_text = out[action_col].astype(str).str.upper() if action_col is not None else pd.Series("", index=out.index)
    decision_text = out[decision_col].astype(str).str.upper() if decision_col is not None else pd.Series("", index=out.index)
    risk_text = out[risk_col].astype(str).str.upper() if risk_col is not None else pd.Series("", index=out.index)
    all_text = action_text + " " + decision_text

    t2 = pd.to_numeric(out[t2_col], errors="coerce") if t2_col is not None else pd.Series(float("nan"), index=out.index)
    t5 = pd.to_numeric(out[t5_col], errors="coerce") if t5_col is not None else pd.Series(float("nan"), index=out.index)
    hist_score = pd.to_numeric(out[hist_score_col], errors="coerce") if hist_score_col is not None else pd.Series(float("nan"), index=out.index)

    history_text = pd.Series("", index=out.index, dtype="object")
    for col in [hist_col, reason_col]:
        if col is not None:
            history_text = history_text + " " + out[col].astype(str).str.upper()

    is_green = all_text.str.contains("BUY NOW|MUA|GIỮ|GIU|WATCHLIST", na=False)
    is_red = all_text.str.contains("SKIP|BỎ QUA|BO QUA|KHÔNG|KHONG|WAIT", na=False) & ~is_green
    hist_ok = history_text.str.contains("MẠNH|MANH|DÙNG ĐƯỢC|DUNG DUOC", na=False) | (hist_score >= 80)

    real_buy_mask = (
        action_text.str.contains("BUY NOW", na=False)
        & risk_text.str.contains("PASS", na=False)
        & (t2 >= 0)
        & (t5 >= 0)
        & hist_ok
    )

    buy_real = ui_compact_top_view(out[real_buy_mask].copy(), limit=10)
    watch = ui_compact_top_view(out[is_green & ~real_buy_mask].copy(), limit=15)
    red = ui_compact_top_view(out[is_red].copy(), limit=10)
    return buy_real, watch, red


def ui_table_html(df, css_class=""):
    try:
        return df.to_html(index=False, escape=True, classes=css_class)
    except Exception as e:
        return f"<p>Không tạo được bảng UI: {repr(e)}</p>"


def ui_full_v134_html(df):
    """Render V13.4 full table"""
    try:
        if df is None or getattr(df, "empty", True):
            return "<p>Không có dữ liệu V13.4</p>"
        out = df.copy()
        cols = list(out.columns)
        ma_col = _ui_find_col(out, ["Mã", "Ma"])
        
        def _ui_row_type(row):
            text = " ".join([str(x).upper() for x in row.values])
            if ("BUY NOW" in text) or ("MUA" in text) or ("WATCHLIST" in text) or ("GIỮ" in text) or ("GIU" in text):
                return "green"
            if ("SKIP" in text) or ("BỎ QUA" in text) or ("BO QUA" in text) or ("KHÔNG" in text) or ("KHONG" in text) or ("WAIT" in text):
                return "red"
            return "neutral"
        
        html_parts = ['<div class="v134-scroll"><table class="v134-full-table">']
        html_parts.append('<thead><tr>')
        for c in cols:
            html_parts.append(f'<th>{_html.escape(str(c))}</th>')
        html_parts.append('</thead><tbody>')
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
