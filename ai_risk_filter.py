import os
import pandas as pd
from datetime import datetime
from config import BOT_DIR

BOT_DIR = str(BOT_DIR)

BOTTOM_PATH = f"{BOT_DIR}/bottom_common_priority.csv"
MOMENTUM_PATH = f"{BOT_DIR}/momentum_common_priority.csv"
ENTRY_PATH = f"{BOT_DIR}/entry_plan_next_session.csv"
OUT_PATH = f"{BOT_DIR}/ai_risk_filtered.csv"

def load_safe(path):
    if os.path.exists(path):
        try:
            return pd.read_csv(path)
        except:
            return pd.DataFrame()
    return pd.DataFrame()

def simple_risk_logic(row):
    rsi = row.get("RSI", 50)
    risk = row.get("Risk %", 2)
    dd = row.get("Drawdown 5P", -2)

    try: rsi = float(rsi)
    except: rsi = 50

    try: risk = float(risk)
    except: risk = 2

    try: dd = float(dd)
    except: dd = -2

    if risk > 4:
        return "❌ AVOID", "Risk cao"
    if dd < -5:
        return "⚠️ WARNING", "Drawdown lớn"
    if rsi > 80:
        return "⚠️ WARNING", "RSI quá nóng"
    if rsi < 35:
        return "⚠️ WARNING", "RSI quá yếu"

    return "✅ OK", "Ổn"

def run_ai_risk_filter():
    bottom = load_safe(BOTTOM_PATH)
    momentum = load_safe(MOMENTUM_PATH)
    entry = load_safe(ENTRY_PATH)

    rows = []

    if not bottom.empty:
        for _, r in bottom.iterrows():
            rows.append({
                "Mã": r.get("Mã"),
                "Chiến lược": "Bắt đáy",
                "Winrate": r.get("winrate_5P_selected"),
                "Return": r.get("avg_return_5P_selected"),
                "Drawdown 5P": r.get("avg_dd_5P_selected")
            })

    if not momentum.empty:
        for _, r in momentum.iterrows():
            rows.append({
                "Mã": r.get("Mã"),
                "Chiến lược": "Momentum",
                "Winrate": r.get("winrate_5P_selected"),
                "Return": r.get("avg_return_5P_selected"),
                "Drawdown 5P": r.get("avg_dd_5P_selected")
            })

    df = pd.DataFrame(rows)

    if df.empty:
        df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
        print("❌ Không có mã để lọc")
        return df

    if not entry.empty and "Mã" in entry.columns:
        keep = ["Mã", "RSI", "Risk %", "Hành động"]
        keep = [c for c in keep if c in entry.columns]
        df = df.merge(entry[keep], on="Mã", how="left")

    labels = df.apply(simple_risk_logic, axis=1)

    df["AI đánh giá"] = [x[0] for x in labels]
    df["Lý do AI"] = [x[1] for x in labels]
    df.insert(0, "Ngày", datetime.now().strftime("%Y-%m-%d"))

    df.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
    print("💾 Saved:", OUT_PATH)
    return df

if __name__ == "__main__":
    run_ai_risk_filter()
