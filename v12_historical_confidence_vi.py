# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np

def _num(x, default=np.nan):
    try:
        if x is None:
            return default
        s = str(x).strip()
        if s == "" or s.lower() in ["nan", "none"]:
            return default
        return float(x)
    except Exception:
        return default

def _txt(x):
    try:
        return str(x).strip()
    except Exception:
        return ""

def _col(df, names):
    if df is None or df.empty:
        return None
    low = {str(c).lower().strip(): c for c in df.columns}
    for n in names:
        if n in df.columns:
            return n
        k = str(n).lower().strip()
        if k in low:
            return low[k]
    return None

def _format_pattern_vi(pattern):
    mp = {
        "UPTREND":"Thị trường tăng","DOWNTREND":"Thị trường giảm","SIDEWAY":"Đi ngang",
        "MOMENTUM":"Đà tăng","MOMENTUM_WATCH":"Theo dõi đà tăng",
        "BOTTOM":"Bắt đáy","BOTTOM_WATCH":"Theo dõi đáy",
        "BUY NOW":"Mua","WAIT":"Chờ","WATCHLIST":"Theo dõi","SKIP":"Bỏ qua",
        "RSI_LOW":"RSI thấp","RSI_WEAK":"RSI yếu","RSI_MID":"RSI trung bình",
        "RSI_MID_HIGH":"RSI khá cao","RSI_HIGH":"RSI cao",
        "RS_STRONG":"RS20 mạnh","RS_WEAK":"RS20 yếu nhẹ","RS_BAD":"RS20 yếu",
        "VOL_LOW":"Thanh khoản thấp","VOL_OK":"Thanh khoản ổn","VOL_STRONG":"Thanh khoản mạnh",
        "ATR_LOW":"Biến động thấp","ATR_OK":"Biến động ổn","ATR_HIGH":"Biến động cao",
        "ABOVE_MA20":"Giá trên MA20","BELOW_MA20":"Giá dưới MA20","FAR_MA20":"Giá xa MA20",
    }
    return " | ".join([mp.get(p.strip(), p.strip()) for p in str(pattern).split("|") if p.strip()])

def _bucket(row):
    parts = []
    regime = _txt(row.get("Regime", row.get("Market Regime Now", ""))).upper()
    if "UPTREND" in regime or "TANG" in regime:
        parts.append("UPTREND")
    elif "DOWN" in regime or "GIAM" in regime:
        parts.append("DOWNTREND")
    else:
        parts.append("SIDEWAY")

    strategy = _txt(row.get("Strategy", row.get("Chien luoc", ""))).upper()
    if strategy:
        parts.append(strategy)

    action = _txt(row.get("Action", row.get("Rec", row.get("Final Action", "")))).upper()
    if "BUY" in action or "MUA" in action:
        parts.append("BUY NOW")
    elif "WAIT" in action or "CHO" in action:
        parts.append("WAIT")
    elif "WATCH" in action or "THEO" in action:
        parts.append("WATCHLIST")
    elif "SKIP" in action or "BO" in action:
        parts.append("SKIP")

    rsi = _num(row.get("RSI"))
    if not pd.isna(rsi):
        parts.append("RSI_LOW" if rsi < 35 else "RSI_WEAK" if rsi < 50 else "RSI_MID" if rsi < 65 else "RSI_MID_HIGH" if rsi < 78 else "RSI_HIGH")

    rs20 = _num(row.get("RS20"))
    if not pd.isna(rs20):
        parts.append("RS_STRONG" if rs20 >= 5 else "RS_WEAK" if rs20 >= 0 else "RS_BAD")

    vol = _num(row.get("Volume Ratio"))
    if not pd.isna(vol):
        parts.append("VOL_STRONG" if vol >= 1.5 else "VOL_OK" if vol >= 0.8 else "VOL_LOW")

    atr = _num(row.get("ATR %"))
    if not pd.isna(atr):
        parts.append("ATR_LOW" if atr < 3 else "ATR_OK" if atr <= 8 else "ATR_HIGH")

    close, ma20, dist = _num(row.get("Close")), _num(row.get("MA20")), _num(row.get("Dist MA20 %"))
    if not pd.isna(close) and not pd.isna(ma20):
        parts.append("FAR_MA20" if close >= ma20 and not pd.isna(dist) and dist >= 12 else "ABOVE_MA20" if close >= ma20 else "BELOW_MA20")
    return "|".join(parts)

def build_current_pattern_key(row):
    for c in ["Deep Pattern", "Pattern", "Pattern Key"]:
        if c in row.index and _txt(row.get(c)):
            return _txt(row.get(c))
    return _bucket(row)

def _lookup(pattern_stats_df):
    if pattern_stats_df is None or pattern_stats_df.empty:
        return {}
    df = pattern_stats_df.copy()
    pcol = _col(df, ["Pattern","Pattern Key","pattern"])
    wrcol = _col(df, ["OOS%","OOS Win Probability","OOS Win Rate","Winrate"])
    ncol = _col(df, ["OOS N","OOSN","OOS Samples","Count","Samples"])
    a2col = _col(df, ["Avg+2D","OOS Avg Ret+2D %","Avg 2D","Ret+2D"])
    a5col = _col(df, ["Avg+5D","OOS Avg Ret+5D %","Avg 5D","Ret+5D"])
    a10col = _col(df, ["Avg+10D","OOS Avg Ret+10D %","Avg 10D","Ret+10D"])
    if not pcol:
        return {}
    out = {}
    for _, r in df.iterrows():
        key = _txt(r.get(pcol))
        if not key:
            continue
        n = _num(r.get(ncol), 0) if ncol else 0
        wr = _num(r.get(wrcol)) if wrcol else np.nan
        win = int(round(n * wr / 100)) if not pd.isna(wr) else np.nan
        out[key] = {
            "Số lần test": int(n) if not pd.isna(n) else 0,
            "Số lần thắng": win,
            "Số lần thua": int(max(n - win, 0)) if not pd.isna(win) else np.nan,
            "Tỷ lệ thắng %": wr,
            "Lợi TB T+2 %": _num(r.get(a2col)) if a2col else np.nan,
            "Lợi TB T+5 %": _num(r.get(a5col)) if a5col else np.nan,
            "Lợi TB T+10 %": _num(r.get(a10col)) if a10col else np.nan,
        }
    return out

def _rank(n, wr, a5):
    n, wr, a5 = _num(n,0), _num(wr), _num(a5)
    if n <= 0 or pd.isna(wr) or pd.isna(a5):
        return "CHƯA CÓ MẪU KHỚP"
    if n < 5:
        return "MẪU ÍT - CHỈ THAM KHẢO" if wr >= 80 and a5 > 0 else "MẪU ÍT / CHƯA ĐỦ TIN CẬY"
    if n >= 10 and wr >= 75 and a5 >= 5:
        return "RẤT MẠNH"
    if n >= 5 and wr >= 70 and a5 >= 3:
        return "MẠNH"
    if n >= 5 and wr >= 65 and a5 >= 1:
        return "DÙNG ĐƯỢC"
    return "YẾU / KHÔNG ƯU TIÊN"

def _hist_score(n, wr, a2, a5, a10):
    n, wr, a2, a5, a10 = _num(n,0), _num(wr), _num(a2), _num(a5), _num(a10)
    if n <= 0 or pd.isna(wr):
        return 0
    score = min(n,20)*1.5 + max(min(wr-50,50),0)
    if not pd.isna(a5): score += max(min(a5*4,30),-20)
    if not pd.isna(a2): score += max(min(a2*2,15),-10)
    if not pd.isna(a10): score += max(min(a10,10),-10)
    return round(max(min(score,100),0),1)

def _decision(row, rank):
    risk = _txt(row.get("Risk")).upper()
    rec = _txt(row.get("Hành động hiện tại")).upper()
    score = _num(row.get("Score"),0)
    ai = _num(row.get("AI"),0)
    if risk == "FAIL":
        return "BỎ QUA - RISK FAIL"
    if rank in ["RẤT MẠNH","MẠNH"]:
        if ("BUY" in rec or "MUA" in rec) and score >= 75 and ai >= 75:
            return "ƯU TIÊN MUA THĂM DÒ"
        return "ƯU TIÊN THEO DÕI ĐIỂM VÀO"
    if rank == "DÙNG ĐƯỢC":
        return "THEO DÕI - CHỜ XÁC NHẬN"
    if "MẪU ÍT" in rank:
        return "CHỈ THAM KHẢO - MUA RẤT NHỎ NẾU CẦN"
    if rank == "CHƯA CÓ MẪU KHỚP":
        if ("BUY" in rec or "MUA" in rec) and score >= 85 and ai >= 85:
            return "CÓ TÍN HIỆU NHƯNG CHƯA CÓ LỊCH SỬ - GIẢM TỶ TRỌNG"
        return "KHÔNG ƯU TIÊN"
    return "KHÔNG ƯU TIÊN"

def _reason(row):
    parts = []
    n = _num(row.get("Số lần test"),0)
    wr = _num(row.get("Tỷ lệ thắng %"))
    a5 = _num(row.get("Lợi TB T+5 %"))
    if n > 0: parts.append(f"mẫu đã test {int(n)} lần")
    else: parts.append("chưa có mẫu lịch sử khớp")
    if not pd.isna(wr): parts.append(f"thắng {round(wr,1)}%")
    if not pd.isna(a5): parts.append(f"T+5 trung bình {round(a5,2)}%")
    parts.append(f"lịch sử: {row.get('Độ tin cậy lịch sử','')}")
    return "; ".join(parts)

def build_do_tin_cay_lich_su_vi(current_df, pattern_stats_df, limit=50):
    try:
        if current_df is None or current_df.empty:
            return pd.DataFrame([{"Trạng thái":"Không có dữ liệu tín hiệu hiện tại"}])
        lk = _lookup(pattern_stats_df)
        df = current_df.copy()
        code = _col(df, ["Ma","Code","Mã"]); date = _col(df, ["Ngay","Date","Ngày"])
        price = _col(df, ["Close","Gia","Giá"]); rec = _col(df, ["Rec","Action","Final Action","Hanh dong","Hành động"])
        score = _col(df, ["Score"]); ai = _col(df, ["AI Confidence","AI"]); risk = _col(df, ["Risk Status","Risk"])
        rsi = _col(df, ["RSI"]); rs20 = _col(df, ["RS20"])
        rows=[]
        for _, r in df.iterrows():
            key = build_current_pattern_key(r)
            h = lk.get(key,{})
            n, wr, a2, a5, a10 = h.get("Số lần test",0), h.get("Tỷ lệ thắng %",np.nan), h.get("Lợi TB T+2 %",np.nan), h.get("Lợi TB T+5 %",np.nan), h.get("Lợi TB T+10 %",np.nan)
            rank = _rank(n,wr,a5)
            row = {
                "Ngày": r.get(date,"") if date else "",
                "Mã": r.get(code,"") if code else "",
                "Giá": r.get(price,"") if price else "",
                "Hành động hiện tại": r.get(rec,"") if rec else "",
                "Score": _num(r.get(score),np.nan) if score else np.nan,
                "AI": _num(r.get(ai),np.nan) if ai else np.nan,
                "Risk": r.get(risk,"") if risk else "",
                "RSI": _num(r.get(rsi),np.nan) if rsi else np.nan,
                "RS20": _num(r.get(rs20),np.nan) if rs20 else np.nan,
                "Độ tin cậy lịch sử": rank,
                "Điểm lịch sử": _hist_score(n,wr,a2,a5,a10),
                "Số lần test": n,
                "Số lần thắng": h.get("Số lần thắng",np.nan),
                "Số lần thua": h.get("Số lần thua",np.nan),
                "Tỷ lệ thắng %": wr,
                "Lợi TB T+2 %": a2,
                "Lợi TB T+5 %": a5,
                "Lợi TB T+10 %": a10,
                "Mẫu hiện tại dễ hiểu": _format_pattern_vi(key),
                "Pattern Key": key,
            }
            row["Kết luận"] = _decision(row, rank)
            row["Lý do"] = _reason(row)
            rows.append(row)
        out = pd.DataFrame(rows)
        order = {"RẤT MẠNH":1,"MẠNH":2,"DÙNG ĐƯỢC":3,"MẪU ÍT - CHỈ THAM KHẢO":4,"MẪU ÍT / CHƯA ĐỦ TIN CẬY":5,"CHƯA CÓ MẪU KHỚP":8,"YẾU / KHÔNG ƯU TIÊN":9}
        out["_rank"] = out["Độ tin cậy lịch sử"].map(order).fillna(9)
        for c in ["Score","AI","RSI","RS20","Điểm lịch sử","Tỷ lệ thắng %","Lợi TB T+2 %","Lợi TB T+5 %","Lợi TB T+10 %"]:
            out[c] = pd.to_numeric(out[c], errors="coerce").round(2)
        for c in ["Số lần test","Số lần thắng","Số lần thua"]:
            out[c] = pd.to_numeric(out[c], errors="coerce").round(0)
        out = out.sort_values(["_rank","Điểm lịch sử","AI","Score"], ascending=[True,False,False,False]).drop(columns=["_rank"])
        cols = ["Ngày","Mã","Giá","Hành động hiện tại","Kết luận","Độ tin cậy lịch sử","Điểm lịch sử","Số lần test","Số lần thắng","Số lần thua","Tỷ lệ thắng %","Lợi TB T+2 %","Lợi TB T+5 %","Lợi TB T+10 %","Score","AI","Risk","RSI","RS20","Lý do","Mẫu hiện tại dễ hiểu","Pattern Key"]
        return out[[c for c in cols if c in out.columns]].replace({np.nan:""}).head(limit)
    except Exception as e:
        return pd.DataFrame([{"Trạng thái":"Lỗi độ tin cậy lịch sử","Chi tiết":repr(e)}])

def build_top_quyet_dinh_lich_su_vi(conf_df, limit=10):
    try:
        if conf_df is None or conf_df.empty or "Kết luận" not in conf_df.columns:
            return pd.DataFrame()
        df = conf_df.copy()
        mask = ~df["Kết luận"].astype(str).str.contains("KHÔNG ƯU TIÊN|BỎ QUA", case=False, na=False)
        top = df[mask].copy()
        if top.empty:
            return pd.DataFrame([{"Trạng thái":"Không có mã đủ điều kiện ưu tiên theo lịch sử"}])
        for c in ["Điểm lịch sử","AI","Score","Lợi TB T+5 %"]:
            if c in top.columns: top[c] = pd.to_numeric(top[c], errors="coerce")
        top = top.sort_values(["Điểm lịch sử","AI","Score"], ascending=[False,False,False])
        cols = ["Mã","Giá","Hành động hiện tại","Kết luận","Độ tin cậy lịch sử","Số lần test","Tỷ lệ thắng %","Lợi TB T+5 %","Điểm lịch sử","AI","Risk"]
        return top[[c for c in cols if c in top.columns]].head(limit).replace({np.nan:""})
    except Exception as e:
        return pd.DataFrame([{"Trạng thái":"Lỗi top quyết định lịch sử","Chi tiết":repr(e)}])
