# -*- coding: utf-8 -*-
# V11 PATTERN MATCH VIEW VI
# Noi tung ma hien tai voi pattern lich su va ket qua qua khu.

import pandas as pd
import numpy as np

def _num(x, default=np.nan):
    try:
        if x is None or str(x).strip()=="":
            return default
        return float(x)
    except Exception:
        return default

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

def _vi_pattern(p):
    parts = [x.strip() for x in str(p).split("|") if x.strip()]
    mp = {
        "UPTREND":"Thi truong tang", "DOWNTREND":"Thi truong giam", "SIDEWAY":"Di ngang",
        "MOMENTUM":"Da tang", "MOMENTUM_WATCH":"Theo doi da tang",
        "BOTTOM":"Bat day", "BOTTOM_WATCH":"Theo doi day",
        "BUY NOW":"Mua", "WAIT":"Cho", "WATCHLIST":"Theo doi", "SKIP":"Bo qua",
        "RSI_LOW":"RSI thap", "RSI_WEAK":"RSI yeu", "RSI_MID":"RSI trung binh",
        "RSI_MID_HIGH":"RSI kha cao", "RSI_HIGH":"RSI cao",
        "RS_STRONG":"RS20 manh", "RS_WEAK":"RS20 yeu", "RS_BAD":"RS20 xau",
        "VOL_LOW":"Volume thap", "VOL_OK":"Volume on", "VOL_STRONG":"Volume manh",
        "ATR_LOW":"ATR thap", "ATR_OK":"ATR on", "ATR_HIGH":"ATR cao",
        "ABOVE_MA20":"Gia tren MA20", "BELOW_MA20":"Gia duoi MA20", "FAR_MA20":"Gia xa MA20",
    }
    return " | ".join([mp.get(x, x) for x in parts])

def _make_pattern(row):
    for c in ["Deep Pattern", "Pattern", "Pattern Key"]:
        if c in row.index and str(row.get(c, "")).strip():
            return str(row.get(c, "")).strip()

    parts = []
    regime = str(row.get("Regime", row.get("Market Regime Now", ""))).upper()
    if "UPTREND" in regime or "TANG" in regime:
        parts.append("UPTREND")
    elif "DOWN" in regime or "GIAM" in regime:
        parts.append("DOWNTREND")
    else:
        parts.append("SIDEWAY")

    strategy = str(row.get("Chien luoc", row.get("Strategy", ""))).upper()
    if strategy:
        parts.append(strategy)

    action = str(row.get("Action", row.get("Rec", row.get("Final Action", "")))).upper()
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
        if rsi < 35: parts.append("RSI_LOW")
        elif rsi < 50: parts.append("RSI_WEAK")
        elif rsi < 65: parts.append("RSI_MID")
        elif rsi < 78: parts.append("RSI_MID_HIGH")
        else: parts.append("RSI_HIGH")

    rs20 = _num(row.get("RS20"))
    if not pd.isna(rs20):
        if rs20 >= 5: parts.append("RS_STRONG")
        elif rs20 >= 0: parts.append("RS_WEAK")
        else: parts.append("RS_BAD")

    vol = _num(row.get("Volume Ratio"))
    if not pd.isna(vol):
        if vol >= 1.5: parts.append("VOL_STRONG")
        elif vol >= 0.8: parts.append("VOL_OK")
        else: parts.append("VOL_LOW")

    atr = _num(row.get("ATR %"))
    if not pd.isna(atr):
        if atr < 3: parts.append("ATR_LOW")
        elif atr <= 8: parts.append("ATR_OK")
        else: parts.append("ATR_HIGH")

    close = _num(row.get("Close"))
    ma20 = _num(row.get("MA20"))
    dist = _num(row.get("Dist MA20 %"))
    if not pd.isna(close) and not pd.isna(ma20):
        if close >= ma20:
            parts.append("FAR_MA20" if (not pd.isna(dist) and dist >= 12) else "ABOVE_MA20")
        else:
            parts.append("BELOW_MA20")

    return "|".join(parts)

def _grade(winrate, n, avg5):
    wr, n, a5 = _num(winrate), _num(n, 0), _num(avg5)
    if pd.isna(wr) or pd.isna(a5): return "CHUA CO MAU"
    if n >= 10 and wr >= 75 and a5 >= 5: return "A+ RAT MANH"
    if n >= 5 and wr >= 70 and a5 >= 3: return "A MANH"
    if n >= 5 and wr >= 65 and a5 >= 1: return "B DUNG DUOC"
    if n < 5 and wr >= 80 and a5 > 0: return "CANH BAO: MAU IT"
    return "C YEU / BO QUA"

def _suggest(grade, rec, risk):
    g, r, rec = str(grade).upper(), str(risk).upper(), str(rec).upper()
    if r == "FAIL": return "BO QUA VI RISK FAIL"
    if "A+ RAT MANH" in g:
        return "UU TIEN MUA THAM DO" if ("BUY" in rec or "MUA" in rec) else "UU TIEN THEO DOI SAT"
    if "A MANH" in g: return "UU TIEN / CHO DIEM VAO"
    if "B DUNG DUOC" in g: return "THEO DOI"
    if "MAU IT" in g: return "CHI THAM KHAO VI MAU IT"
    if "CHUA CO MAU" in g: return "CHUA CO LICH SU - KHONG UU TIEN"
    return "BO QUA / KHONG UU TIEN"

def build_pattern_match_view_vi(current_df, pattern_stats_df, limit=40):
    if current_df is None or current_df.empty:
        return pd.DataFrame([{"Trang thai":"Khong co du lieu tin hieu hien tai"}])
    if pattern_stats_df is None or pattern_stats_df.empty:
        return pd.DataFrame([{"Trang thai":"Khong co du lieu thong ke pattern"}])

    pcol = _col(pattern_stats_df, ["Pattern","Pattern Key","pattern"])
    wrcol = _col(pattern_stats_df, ["OOS%","OOS Win Probability","OOS Win Rate","Winrate"])
    ncol = _col(pattern_stats_df, ["OOS N","OOSN","OOS Samples","Count","Samples"])
    a2col = _col(pattern_stats_df, ["Avg+2D","OOS Avg Ret+2D %","Avg 2D"])
    a5col = _col(pattern_stats_df, ["Avg+5D","OOS Avg Ret+5D %","Avg 5D"])
    a10col = _col(pattern_stats_df, ["Avg+10D","OOS Avg Ret+10D %","Avg 10D"])
    if not pcol:
        return pd.DataFrame([{"Trang thai":"Khong tim thay cot Pattern"}])

    stats = pattern_stats_df.copy()
    stats["_PatternKey"] = stats[pcol].astype(str)
    rename = {}
    if wrcol: rename[wrcol] = "Ty le thang %"
    if ncol: rename[ncol] = "So lan test"
    if a2col: rename[a2col] = "Loi TB T+2 %"
    if a5col: rename[a5col] = "Loi TB T+5 %"
    if a10col: rename[a10col] = "Loi TB T+10 %"
    keep = ["_PatternKey"] + [c for c in [wrcol,ncol,a2col,a5col,a10col] if c]
    stats = stats[keep].rename(columns=rename)

    cur = current_df.copy()
    cur["_PatternKey"] = cur.apply(_make_pattern, axis=1)
    m = cur.merge(stats, on="_PatternKey", how="left")

    code = _col(m, ["Ma","Code","Mã"])
    date = _col(m, ["Ngay","Date","Ngày"])
    price = _col(m, ["Close","Gia","Giá"])
    rec = _col(m, ["Rec","Action","Final Action","Hanh dong"])
    score = _col(m, ["Score"])
    ai = _col(m, ["AI Confidence","AI"])
    risk = _col(m, ["Risk Status","Risk"])

    out = pd.DataFrame()
    out["Ngay"] = m[date] if date else ""
    out["Ma"] = m[code] if code else ""
    out["Gia"] = m[price] if price else ""
    out["Hanh dong hien tai"] = m[rec] if rec else ""
    out["Score"] = pd.to_numeric(m[score], errors="coerce") if score else np.nan
    out["AI"] = pd.to_numeric(m[ai], errors="coerce") if ai else np.nan
    out["Risk"] = m[risk] if risk else ""
    out["Mau dang khop"] = m["_PatternKey"].apply(_vi_pattern)
    out["So lan test"] = pd.to_numeric(m.get("So lan test", np.nan), errors="coerce")
    out["Ty le thang %"] = pd.to_numeric(m.get("Ty le thang %", np.nan), errors="coerce")
    out["Loi TB T+2 %"] = pd.to_numeric(m.get("Loi TB T+2 %", np.nan), errors="coerce")
    out["Loi TB T+5 %"] = pd.to_numeric(m.get("Loi TB T+5 %", np.nan), errors="coerce")
    out["Loi TB T+10 %"] = pd.to_numeric(m.get("Loi TB T+10 %", np.nan), errors="coerce")
    out["So lan thang"] = np.round(out["So lan test"] * out["Ty le thang %"] / 100)
    out["So lan thua"] = out["So lan test"] - out["So lan thang"]
    out["Xep hang mau"] = out.apply(lambda r: _grade(r["Ty le thang %"], r["So lan test"], r["Loi TB T+5 %"]), axis=1)
    out["Goi y theo mau"] = out.apply(lambda r: _suggest(r["Xep hang mau"], r["Hanh dong hien tai"], r["Risk"]), axis=1)
    out["Pattern goc"] = m["_PatternKey"]

    rank = {"A+ RAT MANH":1,"A MANH":2,"B DUNG DUOC":3,"CANH BAO: MAU IT":4,"CHUA CO MAU":8,"C YEU / BO QUA":9}
    out["_rank"] = out["Xep hang mau"].map(rank).fillna(9)
    out = out.sort_values(["_rank","Loi TB T+5 %","AI","Score"], ascending=[True,False,False,False]).drop(columns=["_rank"])

    for c in ["Score","AI","Ty le thang %","Loi TB T+2 %","Loi TB T+5 %","Loi TB T+10 %"]:
        out[c] = pd.to_numeric(out[c], errors="coerce").round(2)
    for c in ["So lan test","So lan thang","So lan thua"]:
        out[c] = pd.to_numeric(out[c], errors="coerce").round(0)

    cols = ["Ngay","Ma","Gia","Hanh dong hien tai","Goi y theo mau","Xep hang mau","So lan test","So lan thang","So lan thua","Ty le thang %","Loi TB T+2 %","Loi TB T+5 %","Loi TB T+10 %","Score","AI","Risk","Mau dang khop","Pattern goc"]
    return out[[c for c in cols if c in out.columns]].replace({np.nan:""}).head(limit)

def build_pattern_match_top_picks_vi(match_view, limit=8):
    if match_view is None or match_view.empty or "Xep hang mau" not in match_view.columns:
        return pd.DataFrame()
    df = match_view.copy()
    good = df[df["Xep hang mau"].astype(str).isin(["A+ RAT MANH","A MANH","B DUNG DUOC"])].copy()
    if good.empty:
        return pd.DataFrame([{"Trang thai":"Khong co ma nao khop mau tot"}])
    for c in ["Loi TB T+5 %","AI","Score","Ty le thang %"]:
        if c in good.columns:
            good[c] = pd.to_numeric(good[c], errors="coerce")
    good = good.sort_values(["Xep hang mau","Loi TB T+5 %","AI","Score"], ascending=[True,False,False,False])
    keep = ["Ma","Gia","Hanh dong hien tai","Goi y theo mau","Xep hang mau","So lan test","Ty le thang %","Loi TB T+5 %","AI","Risk"]
    return good[[c for c in keep if c in good.columns]].head(limit).replace({np.nan:""})
