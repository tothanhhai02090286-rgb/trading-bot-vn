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

def _market_penalty(row):
    market = _up(row.get("Market V13", row.get("Thị trường V13", "")))
    if "TĂNG THẬT" in market or "TANG THAT" in market: return 1.00
    if "GIẢM ẢO" in market or "GIAM AO" in market or "TRỤ ĐÈ" in market or "TRU DE" in market: return 0.95
    if "TĂNG ẢO" in market or "TANG AO" in market or "TRỤ KÉO" in market or "TRU KEO" in market: return 0.85
    if "GIẢM THẬT" in market or "GIAM THAT" in market: return 0.60
    return 0.90

def _trade_type(row):
    qd = _up(row.get("QUYẾT ĐỊNH TỰ ĐỘNG", ""))
    t2 = _num(row.get("Lợi TB T+2 %"), 0)
    t5 = _num(row.get("Lợi TB T+5 %"), 0)
    if "MUA GIỮ T+5" in qd or "MUA GIU T+5" in qd: return "GIỮ T+5"
    if "MUA LƯỚT T+2" in qd or "MUA LUOT T+2" in qd: return "LƯỚT T+2"
    if t5 > t2 and t5 > 0: return "ƯU TIÊN T+5"
    if t2 > 0: return "ƯU TIÊN T+2"
    return "CHỜ"

def _base_trade_score(row):
    risk = _up(row.get("Risk"))
    if risk != "PASS": return 0
    qd = _up(row.get("QUYẾT ĐỊNH TỰ ĐỘNG", ""))
    if "BỎ QUA" in qd or "BO QUA" in qd or "KHÔNG ƯU TIÊN" in qd or "KHONG UU TIEN" in qd:
        return 0
    hist = _num(row.get("Điểm lịch sử"), 0)
    match = _num(row.get("Mức khớp mẫu %"), 0)
    ai = _num(row.get("AI"), 0)
    score = _num(row.get("Score"), 0)
    win = _num(row.get("Tỷ lệ thắng %"), 0)
    t2 = _num(row.get("Lợi TB T+2 %"), 0)
    t5 = _num(row.get("Lợi TB T+5 %"), 0)
    test = _num(row.get("Số lần test"), 0)
    bonus = 18 if "MUA GIỮ T+5" in qd or "MUA GIU T+5" in qd else 15 if "MUA LƯỚT T+2" in qd or "MUA LUOT T+2" in qd else 5 if "THEO DÕI" in qd or "THEO DOI" in qd else 2
    raw = hist*0.30 + match*0.22 + ai*0.18 + score*0.15 + max(win-50,0)*0.35 + min(test,20)*0.7 + max(t5,t2,0)*4 + bonus
    return round(max(min(raw * _market_penalty(row), 100), 0), 2)

def _position_size(row):
    if _up(row.get("Risk")) != "PASS": return 0
    diem = _num(row.get("ĐIỂM LỆNH V14"), 0)
    if diem >= 85: size = 20
    elif diem >= 75: size = 15
    elif diem >= 65: size = 10
    elif diem >= 55: size = 5
    else: size = 0
    if "BOTTOM" in _up(row.get("Strategy")): size = min(size, 10)
    if "T+2" in _trade_type(row): size = min(size, 10)
    return size

def _final_action(row):
    diem = _num(row.get("ĐIỂM LỆNH V14"), 0)
    if _up(row.get("Risk")) != "PASS": return "BỎ QUA"
    if diem >= 75 and "MUA" in _up(row.get("QUYẾT ĐỊNH TỰ ĐỘNG", "")): return "CÓ THỂ MUA THĂM DÒ"
    if diem >= 65: return "THEO DÕI SÁT"
    if diem >= 55: return "CHỜ XÁC NHẬN"
    return "KHÔNG ƯU TIÊN"

def _entry_note(row):
    gia = _num(row.get("Giá"), 0)
    loai = _trade_type(row)
    if gia <= 0: return "Canh điểm vào theo giá đóng cửa gần nhất"
    if "T+5" in loai: return f"Canh mua quanh {round(gia,2)}; ưu tiên giữ 3-5 phiên nếu không vi phạm stoploss"
    if "T+2" in loai: return f"Canh mua quanh {round(gia,2)}; ưu tiên chốt nhanh T+2 nếu đạt kỳ vọng"
    return f"Theo dõi quanh {round(gia,2)}; chưa vội mua mạnh"

def _risk_note(row):
    notes = []
    if _num(row.get("Mức khớp mẫu %"),0) < 60: notes.append("match mẫu còn yếu")
    if _num(row.get("Số lần test"),0) < 5: notes.append("số mẫu lịch sử ít")
    if _num(row.get("Lợi TB T+2 %"),0) <= 0 and _num(row.get("Lợi TB T+5 %"),0) <= 0: notes.append("T+2/T+5 chưa có lợi thế")
    if not notes: notes.append("rủi ro chính: biến động thị trường sau điểm mua")
    return "; ".join(notes)

def build_v14_top_lenh_thuc_chien_vi(v134_df, limit=5):
    try:
        if v134_df is None or v134_df.empty:
            return pd.DataFrame([{"Trạng thái":"Không có dữ liệu V13.4 để chọn lệnh"}])
        df = v134_df.copy()
        if "QUYẾT ĐỊNH TỰ ĐỘNG" not in df.columns:
            df["QUYẾT ĐỊNH TỰ ĐỘNG"] = df.get("Kết luận V13.3", "THEO DÕI")
        if "NGUỒN HÌNH THÀNH" not in df.columns:
            df["NGUỒN HÌNH THÀNH"] = "V13.3 PATTERN + AI + SCORE + RISK"
        df["ĐIỂM LỆNH V14"] = df.apply(_base_trade_score, axis=1)
        df["LOẠI LỆNH"] = df.apply(_trade_type, axis=1)
        df["TỶ TRỌNG GỢI Ý %"] = df.apply(_position_size, axis=1)
        df["HÀNH ĐỘNG V14"] = df.apply(_final_action, axis=1)
        df["GHI CHÚ ĐIỂM VÀO"] = df.apply(_entry_note, axis=1)
        df["RỦI RO CẦN LƯU Ý"] = df.apply(_risk_note, axis=1)
        tradable = df[(df["Risk"].astype(str).str.upper()=="PASS") & (df["ĐIỂM LỆNH V14"]>=55) & (~df["QUYẾT ĐỊNH TỰ ĐỘNG"].astype(str).str.upper().str.contains("BỎ QUA|BO QUA|KHÔNG ƯU TIÊN|KHONG UU TIEN", na=False))].copy()
        if tradable.empty: tradable = df.copy()
        for c in ["ĐIỂM LỆNH V14","TỶ TRỌNG GỢI Ý %","Mức khớp mẫu %","Tỷ lệ thắng %","Lợi TB T+2 %","Lợi TB T+5 %","AI","Score","Điểm lịch sử"]:
            if c in tradable.columns: tradable[c] = pd.to_numeric(tradable[c], errors="coerce").round(2)
        tradable = tradable.sort_values(["ĐIỂM LỆNH V14","TỶ TRỌNG GỢI Ý %","AI","Score"], ascending=[False,False,False,False])
        cols = ["Mã","Giá","HÀNH ĐỘNG V14","LOẠI LỆNH","TỶ TRỌNG GỢI Ý %","QUYẾT ĐỊNH TỰ ĐỘNG","NGUỒN HÌNH THÀNH","Risk","Strategy","Độ tin cậy lịch sử","Mức khớp mẫu %","Số lần test","Tỷ lệ thắng %","Lợi TB T+2 %","Lợi TB T+5 %","ĐIỂM LỆNH V14","AI","Score","GHI CHÚ ĐIỂM VÀO","RỦI RO CẦN LƯU Ý"]
        return tradable[[c for c in cols if c in tradable.columns]].head(limit).replace({np.nan:""})
    except Exception as e:
        return pd.DataFrame([{"Trạng thái":"Lỗi V14 chọn lệnh","Chi tiết":repr(e)}])

def build_v14_html(df):
    if df is None or df.empty: return ""
    html = ['<table border="1" class="dataframe v14-table"><thead><tr>']
    for c in df.columns: html.append(f"<th>{c}</th>")
    html.append("</tr></thead><tbody>")
    for _, row in df.iterrows():
        act = _up(row.get("HÀNH ĐỘNG V14"))
        if "MUA" in act: style="background-color:#103d2b;color:#d8ffe8;font-weight:bold;"
        elif "THEO DÕI" in act or "CHỜ" in act: style="background-color:#3d3510;color:#fff4c2;"
        else: style="background-color:#3d1414;color:#ffd6d6;"
        html.append(f'<tr style="{style}">')
        for c in df.columns: html.append(f"<td>{row.get(c,'')}</td>")
        html.append("</tr>")
    html.append("</tbody></table>")
    return "\n".join(html)
