# -*- coding: utf-8 -*-
import pandas as pd
import html as _html

def _txt(x):
    try:
        if x is None:
            return ""
        s = str(x).strip()
        if s.lower() in ["nan", "none"]:
            return ""
        return s
    except Exception:
        return ""

def _up(x):
    return _txt(x).upper()

def _decision(row):
    cols = [
        "HÀNH ĐỘNG V14",
        "QUYẾT ĐỊNH TỰ ĐỘNG",
        "Kết luận V13.3",
        "Kết luận V13",
        "Hành động hiện tại",
        "Hành động V11",
        "Hanh dong V11",
        "Action",
        "Rec",
        "Signal",
    ]
    risk = _up(row.get("Risk", row.get("Risk Status", "")))
    if risk == "FAIL":
        return "BO_QUA"

    for c in cols:
        if c in row.index:
            v = _up(row.get(c))
            if v:
                if "BỎ QUA" in v or "BO QUA" in v or "SKIP" in v or "KHÔNG ƯU TIÊN" in v or "KHONG UU TIEN" in v or "FAIL" in v:
                    return "BO_QUA"
                if "MUA" in v or "BUY" in v or "CÓ THỂ MUA" in v or "CO THE MUA" in v:
                    return "MUA"
                if "THEO DÕI" in v or "THEO DOI" in v or "CHỜ" in v or "CHO" in v or "WAIT" in v or "WATCH" in v:
                    return "THEO_DOI"

    text = " ".join(_up(x) for x in row.values)
    if "BỎ QUA" in text or "BO QUA" in text or "SKIP" in text or "FAIL" in text or "KHÔNG ƯU TIÊN" in text:
        return "BO_QUA"
    if "MUA" in text or "BUY" in text:
        return "MUA"
    if "THEO DÕI" in text or "THEO DOI" in text or "CHỜ" in text or "WAIT" in text or "WATCH" in text:
        return "THEO_DOI"
    return "KHAC"

def _is_code_col(c):
    return _up(c) in ["MÃ", "MA", "CODE", "TICKER", "SYMBOL"]

def _color(t):
    return {"MUA":"#00ff7f", "THEO_DOI":"#FFD700", "BO_QUA":"#ff5252"}.get(t, "#d0d7de")

def _bg(t):
    return {"MUA":"#083d2a", "THEO_DOI":"#3a3108", "BO_QUA":"#3d1010"}.get(t, "#111820")

def dataframe_to_pro_max_html(df, max_rows=None):
    if df is None or df.empty:
        return '<div class="empty-note">Không có dữ liệu</div>'

    d = df.copy()
    if max_rows:
        d = d.head(max_rows)

    out = ['<div class="table-wrap"><table class="pro-max-table">']
    out.append("<thead><tr>")
    for c in d.columns:
        out.append(f"<th>{_html.escape(str(c))}</th>")
    out.append("</tr></thead><tbody>")

    for _, row in d.iterrows():
        t = _decision(row)
        out.append(f'<tr style="background-color:{_bg(t)};box-shadow:inset 4px 0 0 {_color(t)};">')
        for c in d.columns:
            val = row.get(c, "")
            style = ""
            cu = _up(c)
            if _is_code_col(c):
                style = f"color:{_color(t)};font-weight:1000;font-size:21px;text-align:center;letter-spacing:1px;text-shadow:0 0 8px {_color(t)};white-space:nowrap;"
            elif "QUYẾT ĐỊNH" in cu or "HÀNH ĐỘNG" in cu or "KẾT LUẬN" in cu:
                style = f"color:{_color(t)};font-weight:900;text-align:center;"
            elif cu in ["RISK", "RISK STATUS"]:
                vu = _up(val)
                if vu == "PASS":
                    style = "color:#00ff7f;font-weight:900;text-align:center;"
                elif vu == "FAIL":
                    style = "color:#ff5252;font-weight:900;text-align:center;"
            elif cu in ["AI", "SCORE", "ĐIỂM LỊCH SỬ", "ĐIỂM LỆNH V14", "MỨC KHỚP MẪU %", "TỶ LỆ THẮNG %"]:
                try:
                    n = float(val)
                    if n >= 85:
                        style = "color:#00ff7f;font-weight:800;text-align:center;"
                    elif n >= 65:
                        style = "color:#FFD700;font-weight:800;text-align:center;"
                    else:
                        style = "color:#ffab91;text-align:center;"
                except Exception:
                    style = "text-align:center;"
            out.append(f'<td style="{style}">{_html.escape(str(val))}</td>')
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)

def ui_pro_max_css():
    return """
<style>
body { background:#0d1117; color:#e6edf3; font-family:Arial,Helvetica,sans-serif; font-size:14px; }
h2 { color:#ffffff; font-size:24px; margin:18px 0 10px; }
h3 { color:#ff5c5c; font-size:22px; margin:28px 0 12px; letter-spacing:0.4px; }
.table-wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; border:1px solid #30363d; border-radius:8px; margin-bottom:20px; }
.pro-max-table, table.dataframe { border-collapse:collapse; min-width:980px; width:100%; background:#111820; }
.pro-max-table th, table.dataframe th { position:sticky; top:0; z-index:2; background:#1f2633; color:#f0f6fc; font-weight:900; padding:9px 7px; border:1px solid #30363d; font-size:13px; white-space:nowrap; }
.pro-max-table td, table.dataframe td { padding:8px 7px; border:1px solid #30363d; vertical-align:middle; font-size:13px; }
.pro-max-table tr:hover, table.dataframe tr:hover { outline:2px solid #FFD700; }
table.dataframe td:nth-child(1), table.dataframe td:nth-child(2) { color:#FFD700 !important; font-weight:900 !important; font-size:17px !important; text-align:center !important; }
table.dataframe th:nth-child(1), table.dataframe th:nth-child(2) { color:#FFD700 !important; font-weight:900 !important; }
.legend-box { background:#161b22; border-left:5px solid #FFD700; padding:12px 14px; margin:10px 0 18px; color:#fff8c5; font-size:14px; line-height:1.55; }
.legend-buy { color:#00ff7f; font-weight:1000; text-shadow:0 0 6px #00ff7f; }
.legend-watch { color:#FFD700; font-weight:1000; text-shadow:0 0 6px #FFD700; }
.legend-skip { color:#ff5252; font-weight:1000; text-shadow:0 0 6px #ff5252; }
.empty-note { color:#FFD700; padding:10px; border:1px solid #30363d; background:#161b22; }
</style>
"""

def build_ui_pro_max_note():
    return """
<div class="legend-box">
<b>HƯỚNG DẪN ĐỌC NHANH:</b><br>
<span class="legend-buy">MÃ MÀU XANH LÁ</span> = có thể mua/thăm dò.<br>
<span class="legend-watch">MÃ MÀU VÀNG</span> = theo dõi/chờ xác nhận.<br>
<span class="legend-skip">MÃ MÀU ĐỎ</span> = bỏ qua/không ưu tiên/risk fail.<br>
Cột Mã là tín hiệu trực quan chính, ưu tiên đọc trước các cột khác.
</div>
"""

def build_v14_pro_max_main_html(v14_df=None, v134_df=None, v133_df=None):
    parts = [build_ui_pro_max_note()]
    if v14_df is not None and not v14_df.empty:
        parts.append("<h3>V14 PRO MAX - TOP LỆNH THỰC CHIẾN</h3>")
        parts.append(dataframe_to_pro_max_html(v14_df, max_rows=8))
    if v134_df is not None and not v134_df.empty:
        parts.append("<h3>V13.4 PRO MAX - BẢNG QUYẾT ĐỊNH TỰ ĐỘNG</h3>")
        parts.append(dataframe_to_pro_max_html(v134_df, max_rows=40))
    if v133_df is not None and not v133_df.empty:
        parts.append("<h3>V13.3 PRO MAX - MẪU LỊCH SỬ GẦN NHẤT</h3>")
        parts.append(dataframe_to_pro_max_html(v133_df, max_rows=20))
    return "\\n".join(parts)
