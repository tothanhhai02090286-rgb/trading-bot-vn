# -*- coding: utf-8 -*-
# V13.2 FEATURE-BASED PATTERN ENGINE VI
# Cách 2: convert pattern lịch sử + tín hiệu hiện tại về feature rồi match theo trọng số.

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

def _up(x):
    return _txt(x).upper()

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

def _parts(pattern):
    return [p.strip().upper() for p in str(pattern).split("|") if p.strip()]

def _norm_token(t):
    t = str(t).strip().upper()
    mp = {
        "RS_STRONG": "RS20_STRONG",
        "RS_WEAK": "RS20_SOFT",
        "RS_BAD": "RS20_BAD",
        "RS20_SLIGHT_WEAK": "RS20_SOFT",
        "RS20_SOFT": "RS20_SOFT",
        "RS20_OK": "RS20_OK",
        "RS20_STRONG": "RS20_STRONG",
        "RS20_LEADER": "RS20_LEADER",
    }
    return mp.get(t, t)

def pattern_to_features(pattern):
    tokens = [_norm_token(t) for t in _parts(pattern)]
    f = {"Regime":"", "Strategy":"", "Action":"", "RSI":"", "RS20":"", "Volume":"", "ATR":"", "MA20":""}
    for t in tokens:
        if t in ["UPTREND", "DOWNTREND", "SIDEWAY"]:
            f["Regime"] = t
        elif t in ["MOMENTUM", "MOMENTUM_WATCH", "BOTTOM", "BOTTOM_WATCH", "WATCH"]:
            f["Strategy"] = t
        elif t in ["BUY NOW", "WAIT", "WATCHLIST", "SKIP"]:
            f["Action"] = t
        elif t.startswith("RSI_"):
            f["RSI"] = t
        elif t.startswith("RS20_"):
            f["RS20"] = t
        elif t.startswith("VOL_"):
            f["Volume"] = t
        elif t.startswith("ATR_"):
            f["ATR"] = t
        elif t in ["ABOVE_MA20", "BELOW_MA20", "FAR_MA20"]:
            f["MA20"] = t
    return f

def _bucket_rsi(v):
    r = _num(v)
    if pd.isna(r): return ""
    if r < 35: return "RSI_LOW"
    if r < 50: return "RSI_WEAK"
    if r < 65: return "RSI_MID"
    if r < 78: return "RSI_MID_HIGH"
    if r < 85: return "RSI_HIGH"
    return "RSI_OVERHEAT"

def _bucket_rs20(v):
    x = _num(v)
    if pd.isna(x): return ""
    if x >= 25: return "RS20_LEADER"
    if x >= 5: return "RS20_STRONG"
    if x >= 0: return "RS20_OK"
    if x >= -5: return "RS20_SOFT"
    return "RS20_BAD"

def _bucket_volume(v):
    x = _num(v)
    if pd.isna(x): return ""
    if x >= 1.5: return "VOL_STRONG"
    if x >= 0.8: return "VOL_OK"
    return "VOL_LOW"

def _bucket_atr(v):
    x = _num(v)
    if pd.isna(x): return ""
    if x < 3: return "ATR_LOW"
    if x <= 8: return "ATR_OK"
    return "ATR_HIGH"

def _bucket_ma20(row):
    close = _num(row.get("Close"))
    ma20 = _num(row.get("MA20"))
    dist = _num(row.get("Dist MA20 %"))
    if pd.isna(close) or pd.isna(ma20): return ""
    if close >= ma20:
        if not pd.isna(dist) and dist >= 12:
            return "FAR_MA20"
        return "ABOVE_MA20"
    return "BELOW_MA20"

def current_row_to_features(row):
    # Ưu tiên parse pattern gốc nếu đã có.
    for c in ["Deep Pattern", "Pattern", "Pattern Key"]:
        if c in row.index and _txt(row.get(c)):
            f = pattern_to_features(row.get(c))
            if not f["RSI"]: f["RSI"] = _bucket_rsi(row.get("RSI"))
            if not f["RS20"]: f["RS20"] = _bucket_rs20(row.get("RS20"))
            if not f["Volume"]: f["Volume"] = _bucket_volume(row.get("Volume Ratio"))
            if not f["ATR"]: f["ATR"] = _bucket_atr(row.get("ATR %"))
            if not f["MA20"]: f["MA20"] = _bucket_ma20(row)
            return f

    f = {
        "Regime": "", "Strategy": "", "Action": "",
        "RSI": _bucket_rsi(row.get("RSI")),
        "RS20": _bucket_rs20(row.get("RS20")),
        "Volume": _bucket_volume(row.get("Volume Ratio")),
        "ATR": _bucket_atr(row.get("ATR %")),
        "MA20": _bucket_ma20(row),
    }

    regime = _up(row.get("Regime", row.get("Market Regime Now", "")))
    if "UPTREND" in regime or "TANG" in regime:
        f["Regime"] = "UPTREND"
    elif "DOWN" in regime or "GIAM" in regime:
        f["Regime"] = "DOWNTREND"
    else:
        f["Regime"] = "SIDEWAY"

    st = _up(row.get("Strategy", row.get("Chien luoc", row.get("Chiến lược", ""))))
    if "BOTTOM" in st:
        f["Strategy"] = "BOTTOM_WATCH" if "WATCH" in st else "BOTTOM"
    elif "MOMENTUM" in st:
        f["Strategy"] = "MOMENTUM_WATCH" if "WATCH" in st else "MOMENTUM"
    elif st:
        f["Strategy"] = st

    action = _up(row.get("Action", row.get("Rec", row.get("Final Action", row.get("Hanh dong", "")))))
    if "BUY" in action or "MUA" in action:
        f["Action"] = "BUY NOW"
    elif "WAIT" in action or "CHO" in action:
        f["Action"] = "WAIT"
    elif "WATCH" in action or "THEO" in action:
        f["Action"] = "WATCHLIST"
    elif "SKIP" in action or "BO" in action:
        f["Action"] = "SKIP"

    return f

def features_to_key(f):
    return "|".join([_txt(f.get(k)) for k in ["Regime","Strategy","Action","RSI","RS20","Volume","ATR","MA20"] if _txt(f.get(k))])

WEIGHTS_MOMENTUM = {"Regime":20, "Strategy":20, "RS20":20, "RSI":15, "MA20":10, "Volume":10, "ATR":5, "Action":10}
WEIGHTS_BOTTOM = {"Regime":10, "Strategy":20, "RSI":25, "Volume":15, "ATR":10, "MA20":10, "RS20":10, "Action":10}

def _strategy_group(f):
    s = _up(f.get("Strategy"))
    if "BOTTOM" in s: return "BOTTOM"
    if "MOMENTUM" in s: return "MOMENTUM"
    return "OTHER"

def _weights_for(f):
    return WEIGHTS_BOTTOM if _strategy_group(f) == "BOTTOM" else WEIGHTS_MOMENTUM

def _ord_sim(a, b, order):
    if not a or not b: return 0.0
    if a == b: return 1.0
    if a in order and b in order:
        d = abs(order.index(a) - order.index(b))
        if d == 1: return 0.7
        if d == 2: return 0.35
    return 0.0

def _sim(field, a, b):
    a, b = _up(a), _up(b)
    if not a or not b: return 0.0
    if a == b: return 1.0

    if field == "Regime":
        if set([a,b]) == set(["UPTREND","SIDEWAY"]): return 0.5
        if set([a,b]) == set(["DOWNTREND","SIDEWAY"]): return 0.4
        return 0.0

    if field == "Strategy":
        if "MOMENTUM" in a and "MOMENTUM" in b: return 0.6
        if "BOTTOM" in a and "BOTTOM" in b: return 0.6
        return 0.0

    if field == "RSI":
        return _ord_sim(a,b,["RSI_LOW","RSI_WEAK","RSI_MID","RSI_MID_HIGH","RSI_HIGH","RSI_OVERHEAT"])

    if field == "RS20":
        return _ord_sim(a,b,["RS20_BAD","RS20_SOFT","RS20_OK","RS20_STRONG","RS20_LEADER"])

    if field == "Volume":
        return _ord_sim(a,b,["VOL_LOW","VOL_OK","VOL_STRONG"])

    if field == "ATR":
        return _ord_sim(a,b,["ATR_LOW","ATR_OK","ATR_HIGH"])

    if field == "MA20":
        if set([a,b]) == set(["ABOVE_MA20","FAR_MA20"]): return 0.6
        return 0.0

    if field == "Action":
        if a in ["BUY NOW","WAIT"] and b in ["BUY NOW","WAIT"]: return 0.5
        if a in ["WATCHLIST","WAIT"] and b in ["WATCHLIST","WAIT"]: return 0.5
        return 0.0

    return 0.0

def weighted_feature_match(current_f, hist_f):
    weights = _weights_for(current_f)
    total = sum(weights.values())
    got = 0.0
    details = []
    for field, w in weights.items():
        s = _sim(field, current_f.get(field,""), hist_f.get(field,""))
        got += w*s
        if s > 0:
            details.append(f"{field}: {round(w*s,1)}/{w}")
    pct = round(got/total*100, 2) if total else 0.0
    return pct, "; ".join(details)

def _history_records(pattern_stats_df):
    if pattern_stats_df is None or pattern_stats_df.empty:
        return []
    df = pattern_stats_df.copy()
    pcol = _col(df, ["Pattern", "Pattern Key", "pattern"])
    wrcol = _col(df, ["OOS%", "OOS Win Probability", "OOS Win Rate", "Winrate"])
    ncol = _col(df, ["OOS N", "OOSN", "OOS Samples", "Count", "Samples"])
    a2col = _col(df, ["Avg+2D", "OOS Avg Ret+2D %", "Avg 2D", "Ret+2D"])
    a5col = _col(df, ["Avg+5D", "OOS Avg Ret+5D %", "Avg 5D", "Ret+5D"])
    a10col = _col(df, ["Avg+10D", "OOS Avg Ret+10D %", "Avg 10D", "Ret+10D"])
    if not pcol: return []
    records = []
    for _, r in df.iterrows():
        p = _txt(r.get(pcol))
        if not p: continue
        n = _num(r.get(ncol),0) if ncol else 0
        wr = _num(r.get(wrcol),np.nan) if wrcol else np.nan
        win = int(round(n*wr/100)) if not pd.isna(wr) else np.nan
        records.append({
            "Pattern lịch sử": p,
            "Feature lịch sử": pattern_to_features(p),
            "Số lần test": int(n) if not pd.isna(n) else 0,
            "Số lần thắng": win,
            "Số lần thua": int(max(n-win,0)) if not pd.isna(win) else np.nan,
            "Tỷ lệ thắng %": wr,
            "Lợi TB T+2 %": _num(r.get(a2col),np.nan) if a2col else np.nan,
            "Lợi TB T+5 %": _num(r.get(a5col),np.nan) if a5col else np.nan,
            "Lợi TB T+10 %": _num(r.get(a10col),np.nan) if a10col else np.nan,
        })
    return records

def _best_match(current_f, records, min_match_pct=60):
    best = None
    for rec in records:
        pct, detail = weighted_feature_match(current_f, rec["Feature lịch sử"])
        if pct < min_match_pct:
            continue
        item = dict(rec)
        item["Mức khớp mẫu %"] = pct
        item["Chi tiết khớp"] = detail
        item["_rank"] = (pct, _num(item.get("Số lần test"),0), _num(item.get("Lợi TB T+5 %"),-999), _num(item.get("Tỷ lệ thắng %"),-999))
        if best is None or item["_rank"] > best["_rank"]:
            best = item
    if best is None: return None
    best.pop("_rank", None)
    return best

def _rank_history(n, wr, a5, pct):
    n, wr, a5, pct = _num(n,0), _num(wr), _num(a5), _num(pct,0)
    if n <= 0 or pd.isna(wr) or pd.isna(a5) or pct <= 0:
        return "CHƯA CÓ MẪU GẦN GIỐNG"
    if pct >= 85 and n >= 10 and wr >= 75 and a5 >= 5:
        return "RẤT MẠNH"
    if pct >= 75 and n >= 5 and wr >= 70 and a5 >= 3:
        return "MẠNH"
    if pct >= 65 and n >= 5 and wr >= 65 and a5 >= 1:
        return "DÙNG ĐƯỢC"
    if n < 5 and wr >= 75 and a5 > 0:
        return "MẪU ÍT - THAM KHẢO"
    return "YẾU / KHÔNG ƯU TIÊN"

def _score(n, wr, a2, a5, a10, pct):
    n, wr, a2, a5, a10, pct = _num(n,0), _num(wr), _num(a2), _num(a5), _num(a10), _num(pct,0)
    if n <= 0 or pd.isna(wr) or pct <= 0: return 0
    s = min(n,20)*1.1 + max(min(wr-50,50),0)*0.8 + pct*0.35
    if not pd.isna(a5): s += max(min(a5*3,25),-20)
    if not pd.isna(a2): s += max(min(a2*1.5,10),-10)
    if not pd.isna(a10): s += max(min(a10*0.8,8),-8)
    return round(max(min(s,100),0),1)

def _feature_vi(f):
    mp = {
        "UPTREND":"Thị trường tăng","DOWNTREND":"Thị trường giảm","SIDEWAY":"Đi ngang",
        "MOMENTUM":"Đà tăng","MOMENTUM_WATCH":"Theo dõi đà tăng","BOTTOM":"Bắt đáy","BOTTOM_WATCH":"Theo dõi đáy",
        "BUY NOW":"Mua","WAIT":"Chờ","WATCHLIST":"Theo dõi","SKIP":"Bỏ qua",
        "RSI_LOW":"RSI thấp","RSI_WEAK":"RSI yếu","RSI_MID":"RSI trung bình","RSI_MID_HIGH":"RSI khá cao","RSI_HIGH":"RSI cao","RSI_OVERHEAT":"RSI quá nóng",
        "RS20_BAD":"RS20 yếu","RS20_SOFT":"RS20 hơi yếu","RS20_OK":"RS20 ổn","RS20_STRONG":"RS20 mạnh","RS20_LEADER":"RS20 dẫn dắt",
        "VOL_LOW":"Thanh khoản thấp","VOL_OK":"Thanh khoản ổn","VOL_STRONG":"Thanh khoản mạnh",
        "ATR_LOW":"Biến động thấp","ATR_OK":"Biến động ổn","ATR_HIGH":"Biến động cao",
        "ABOVE_MA20":"Giá trên MA20","BELOW_MA20":"Giá dưới MA20","FAR_MA20":"Giá xa MA20"
    }
    vals = []
    for k in ["Regime","Strategy","Action","RSI","RS20","Volume","ATR","MA20"]:
        v = _txt(f.get(k))
        if v: vals.append(mp.get(v,v))
    return " | ".join(vals)

def build_v132_feature_pattern_view_vi(current_df, pattern_stats_df, min_match_pct=60, limit=60):
    try:
        if current_df is None or current_df.empty:
            return pd.DataFrame([{"Trạng thái":"Không có dữ liệu tín hiệu"}])
        records = _history_records(pattern_stats_df)
        if not records:
            return pd.DataFrame([{"Trạng thái":"Không có dữ liệu pattern lịch sử"}])
        df = current_df.copy()
        code_col = _col(df, ["Ma","Code","Mã"])
        date_col = _col(df, ["Ngay","Date","Ngày"])
        price_col = _col(df, ["Close","Gia","Giá"])
        rec_col = _col(df, ["Rec","Action","Final Action","Hanh dong","Hành động"])
        score_col = _col(df, ["Score"])
        ai_col = _col(df, ["AI Confidence","AI"])
        risk_col = _col(df, ["Risk Status","Risk"])
        strat_col = _col(df, ["Strategy","Chien luoc","Chiến lược"])
        rsi_col = _col(df, ["RSI"])
        rs20_col = _col(df, ["RS20"])
        rows = []
        for _, r in df.iterrows():
            cur_f = current_row_to_features(r)
            best = _best_match(cur_f, records, min_match_pct=min_match_pct)
            if best is None:
                best = {"Pattern lịch sử":"", "Feature lịch sử":{}, "Số lần test":0, "Số lần thắng":np.nan, "Số lần thua":np.nan, "Tỷ lệ thắng %":np.nan, "Lợi TB T+2 %":np.nan, "Lợi TB T+5 %":np.nan, "Lợi TB T+10 %":np.nan, "Mức khớp mẫu %":0, "Chi tiết khớp":""}
            n, wr, a2, a5, a10, pct = best["Số lần test"], best["Tỷ lệ thắng %"], best["Lợi TB T+2 %"], best["Lợi TB T+5 %"], best["Lợi TB T+10 %"], best["Mức khớp mẫu %"]
            rank = _rank_history(n, wr, a5, pct)
            row = {
                "Ngày": r.get(date_col,"") if date_col else "",
                "Mã": r.get(code_col,"") if code_col else "",
                "Giá": r.get(price_col,"") if price_col else "",
                "Hành động hiện tại": r.get(rec_col,"") if rec_col else "",
                "Strategy": r.get(strat_col,"") if strat_col else "",
                "Độ tin cậy lịch sử": rank,
                "Điểm lịch sử": _score(n,wr,a2,a5,a10,pct),
                "Mức khớp mẫu %": pct,
                "Số lần test": n,
                "Số lần thắng": best["Số lần thắng"],
                "Số lần thua": best["Số lần thua"],
                "Tỷ lệ thắng %": wr,
                "Lợi TB T+2 %": a2,
                "Lợi TB T+5 %": a5,
                "Lợi TB T+10 %": a10,
                "Score": _num(r.get(score_col),np.nan) if score_col else np.nan,
                "AI": _num(r.get(ai_col),np.nan) if ai_col else np.nan,
                "Risk": r.get(risk_col,"") if risk_col else "",
                "RSI": _num(r.get(rsi_col),np.nan) if rsi_col else np.nan,
                "RS20": _num(r.get(rs20_col),np.nan) if rs20_col else np.nan,
                "Feature hiện tại": _feature_vi(cur_f),
                "Feature lịch sử gần giống": _feature_vi(best.get("Feature lịch sử",{})),
                "Chi tiết khớp": best.get("Chi tiết khớp",""),
                "Pattern hiện tại": features_to_key(cur_f),
                "Pattern lịch sử": best.get("Pattern lịch sử",""),
            }
            row["Lý do"] = f"khớp {pct}%; lịch sử {rank}; test {n}; win {'' if pd.isna(wr) else round(wr,1)}%; T+5 {'' if pd.isna(a5) else round(a5,2)}%"
            rows.append(row)
        out = pd.DataFrame(rows)
        order = {"RẤT MẠNH":1,"MẠNH":2,"DÙNG ĐƯỢC":3,"MẪU ÍT - THAM KHẢO":4,"YẾU / KHÔNG ƯU TIÊN":8,"CHƯA CÓ MẪU GẦN GIỐNG":9}
        out["_rank"] = out["Độ tin cậy lịch sử"].map(order).fillna(9)
        for c in ["Điểm lịch sử","Mức khớp mẫu %","Tỷ lệ thắng %","Lợi TB T+2 %","Lợi TB T+5 %","Lợi TB T+10 %","Score","AI","RSI","RS20"]:
            out[c] = pd.to_numeric(out[c], errors="coerce").round(2)
        for c in ["Số lần test","Số lần thắng","Số lần thua"]:
            out[c] = pd.to_numeric(out[c], errors="coerce").round(0)
        out = out.sort_values(["_rank","Điểm lịch sử","AI","Score"], ascending=[True,False,False,False]).drop(columns=["_rank"])
        return out.replace({np.nan:""}).head(limit)
    except Exception as e:
        return pd.DataFrame([{"Trạng thái":"Lỗi V13.2 feature-based pattern","Chi tiết":repr(e)}])

def build_v132_top_feature_picks_vi(feature_df, limit=8):
    try:
        if feature_df is None or feature_df.empty or "Độ tin cậy lịch sử" not in feature_df.columns:
            return pd.DataFrame()
        df = feature_df.copy()
        good = df[df["Độ tin cậy lịch sử"].astype(str).isin(["RẤT MẠNH","MẠNH","DÙNG ĐƯỢC","MẪU ÍT - THAM KHẢO"])].copy()
        if good.empty:
            return pd.DataFrame([{"Trạng thái":"Không có mã đủ điều kiện feature-based"}])
        for c in ["Điểm lịch sử","Mức khớp mẫu %","AI","Score","Lợi TB T+5 %"]:
            if c in good.columns:
                good[c] = pd.to_numeric(good[c], errors="coerce")
        good = good.sort_values(["Điểm lịch sử","Mức khớp mẫu %","AI","Score"], ascending=[False,False,False,False])
        cols = ["Mã","Giá","Hành động hiện tại","Strategy","Độ tin cậy lịch sử","Mức khớp mẫu %","Số lần test","Tỷ lệ thắng %","Lợi TB T+5 %","Điểm lịch sử","AI","Risk","Lý do"]
        return good[[c for c in cols if c in good.columns]].head(limit).replace({np.nan:""})
    except Exception as e:
        return pd.DataFrame([{"Trạng thái":"Lỗi top V13.2 feature-based","Chi tiết":repr(e)}])
