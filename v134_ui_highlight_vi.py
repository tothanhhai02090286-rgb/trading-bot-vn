# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np

def _num(x, default=0):
    try:
        if x is None: return default
        s = str(x).strip()
        if s == "" or s.lower() in ["nan","none"]: return default
        return float(x)
    except Exception:
        return default

def _txt(x):
    try: return str(x).strip()
    except Exception: return ""

def _up(x): return _txt(x).upper()

def quyet_dinh_tu_dong(row):
    risk = _up(row.get("Risk"))
    ket_luan = _up(row.get("Kết luận V13.3", row.get("Kết luận V13", "")))
    rank = _up(row.get("Độ tin cậy lịch sử"))
    test = _num(row.get("Số lần test"), 0)
    win = _num(row.get("Tỷ lệ thắng %"), 0)
    t2 = _num(row.get("Lợi TB T+2 %"), 0)
    t5 = _num(row.get("Lợi TB T+5 %"), 0)
    hist = _num(row.get("Điểm lịch sử"), 0)
    match = _num(row.get("Mức khớp mẫu %"), 0)
    ai = _num(row.get("AI"), 0)
    score = _num(row.get("Score"), 0)

    if risk != "PASS":
        return "BỎ QUA"
    if "BỎ QUA" in ket_luan or "KHÔNG ƯU TIÊN" in ket_luan:
        return "KHÔNG ƯU TIÊN"
    if test <= 0:
        return "CHỜ XÁC NHẬN THÊM"

    if win >= 65 and t2 > 0 and match >= 60 and score >= 70 and ai >= 70:
        return "MUA LƯỚT T+2"
    if win >= 65 and t5 > t2 and t5 > 0 and match >= 60:
        return "MUA GIỮ T+5"
    if rank in ["RẤT MẠNH","MẠNH","DÙNG ĐƯỢC"] or hist >= 60 or match >= 60:
        return "THEO DÕI"
    return "KHÔNG ƯU TIÊN"

def nguon_hinh_thanh(row):
    risk = _up(row.get("Risk"))
    hist = _num(row.get("Điểm lịch sử"), 0)
    match = _num(row.get("Mức khớp mẫu %"), 0)
    ai = _num(row.get("AI"), 0)
    score = _num(row.get("Score"), 0)
    if risk != "PASS":
        return "RISK FILTER"
    parts = []
    if hist >= 60 or match >= 60:
        parts.append("V13.3 PATTERN")
    if ai >= 70:
        parts.append("AI")
    if score >= 70:
        parts.append("SCORE")
    parts.append("RISK PASS")
    return " + ".join(parts)

def ly_do_chi_tiet(row):
    return (
        f"Risk {_txt(row.get('Risk'))}; "
        f"lịch sử {_txt(row.get('Độ tin cậy lịch sử'))}; "
        f"khớp mẫu {round(_num(row.get('Mức khớp mẫu %')),1)}%; "
        f"test {int(_num(row.get('Số lần test')))} lần; "
        f"win {round(_num(row.get('Tỷ lệ thắng %')),1)}%; "
        f"T+2 {round(_num(row.get('Lợi TB T+2 %')),2)}%; "
        f"T+5 {round(_num(row.get('Lợi TB T+5 %')),2)}%; "
        f"AI {round(_num(row.get('AI')),1)}; "
        f"Score {round(_num(row.get('Score')),1)}"
    )

def build_v134_decision_ui_vi(v133_df, limit=30):
    try:
        if v133_df is None or v133_df.empty:
            return pd.DataFrame([{"Trạng thái":"Không có dữ liệu V13.3"}])
        df = v133_df.copy()
        df["QUYẾT ĐỊNH TỰ ĐỘNG"] = df.apply(quyet_dinh_tu_dong, axis=1)
        df["NGUỒN HÌNH THÀNH"] = df.apply(nguon_hinh_thanh, axis=1)
        df["LÝ DO CHI TIẾT"] = df.apply(ly_do_chi_tiet, axis=1)

        priority = {"MUA LƯỚT T+2":1,"MUA GIỮ T+5":2,"THEO DÕI":3,"CHỜ XÁC NHẬN THÊM":4,"KHÔNG ƯU TIÊN":8,"BỎ QUA":9}
        df["_p"] = df["QUYẾT ĐỊNH TỰ ĐỘNG"].map(priority).fillna(8)

        for c in ["Điểm lịch sử","Mức khớp mẫu %","Tỷ lệ thắng %","Lợi TB T+2 %","Lợi TB T+5 %","AI","Score"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").round(2)
        if "Số lần test" in df.columns:
            df["Số lần test"] = pd.to_numeric(df["Số lần test"], errors="coerce").round(0)

        sort_cols = [c for c in ["_p","Điểm lịch sử","Mức khớp mẫu %","AI","Score"] if c in df.columns]
        df = df.sort_values(sort_cols, ascending=[True]+[False]*(len(sort_cols)-1)).drop(columns=["_p"])

        cols = ["Mã","Giá","QUYẾT ĐỊNH TỰ ĐỘNG","NGUỒN HÌNH THÀNH","Hành động hiện tại","Strategy","Risk",
                "Độ tin cậy lịch sử","Mức khớp mẫu %","Số lần test","Tỷ lệ thắng %",
                "Lợi TB T+2 %","Lợi TB T+5 %","Điểm lịch sử","AI","Score","LÝ DO CHI TIẾT"]
        return df[[c for c in cols if c in df.columns]].head(limit).replace({np.nan:""})
    except Exception as e:
        return pd.DataFrame([{"Trạng thái":"Lỗi V13.4 UI Highlight","Chi tiết":repr(e)}])

def dataframe_to_highlight_html(df):
    if df is None or df.empty:
        return ""
    html = ['<table border="1" class="dataframe v134-table">']
    html.append("<thead><tr>")
    for c in df.columns:
        html.append(f"<th>{c}</th>")
    html.append("</tr></thead><tbody>")
    for _, row in df.iterrows():
        qd = _up(row.get("QUYẾT ĐỊNH TỰ ĐỘNG"))
        if "MUA" in qd:
            style = "background-color:#103d2b;color:#d8ffe8;font-weight:bold;"
        elif "THEO DÕI" in qd or "CHỜ" in qd:
            style = "background-color:#3d3510;color:#fff4c2;"
        elif "BỎ QUA" in qd or "KHÔNG ƯU TIÊN" in qd:
            style = "background-color:#3d1414;color:#ffd6d6;"
        else:
            style = ""
        html.append(f'<tr style="{style}">')
        for c in df.columns:
            html.append(f"<td>{row.get(c,'')}</td>")
        html.append("</tr>")
    html.append("</tbody></table>")
    return "\n".join(html)
