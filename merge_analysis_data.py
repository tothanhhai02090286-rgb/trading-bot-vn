# -*- coding: utf-8 -*-
"""
Ghép dữ liệu chuỗi tăng (streaks) với các quyết định của hệ thống.
Đầu ra: merged_analysis.csv (có thể mở bằng Excel)
"""

import os
import pandas as pd

# ==================== FILE ĐẦU VÀO ====================
STREAKS_FILE = "streaks_report.csv"
FINAL_DECISION_FILE = "v17_final_decision_integrated.csv"   # hoặc "v17_final_decision.csv"
META_ALLOC_FILE = "v16_meta_allocation.csv"
WATCHLIST_FILE = "intraday_watchlist_v17.csv"
PRO_RESEARCH_FILE = "v153_pro_research.csv"                  # nếu có

# ==================== FILE ĐẦU RA ====================
OUTPUT_MERGED = "merged_analysis.csv"

# ==================== ĐỌC DỮ LIỆU ====================
def read_smart(path):
    if not os.path.exists(path):
        print(f"⚠️ Không tìm thấy {path}, bỏ qua")
        return pd.DataFrame()
    for enc in ["utf-8-sig", "utf-8", "cp1258"]:
        try:
            return pd.read_csv(path, encoding=enc)
        except:
            pass
    return pd.DataFrame()

streaks = read_smart(STREAKS_FILE)
final = read_smart(FINAL_DECISION_FILE)
meta = read_smart(META_ALLOC_FILE)
watch = read_smart(WATCHLIST_FILE)
pro = read_smart(PRO_RESEARCH_FILE)

# Chuẩn hóa cột mã
for df in [streaks, final, meta, watch, pro]:
    if df is not None and not df.empty:
        if "Mã" in df.columns:
            df["Mã"] = df["Mã"].astype(str).str.upper().str.strip()
        elif "Ma" in df.columns:
            df["Mã"] = df["Ma"].astype(str).str.upper().str.strip()
        elif "Symbol" in df.columns:
            df["Mã"] = df["Symbol"].astype(str).str.upper().str.strip()

# ==================== GHÉP DỮ LIỆU ====================
# Bắt đầu từ streaks (chứa tất cả mã có cache)
merged = streaks.copy()

# Thêm quyết định cuối (Final Decision, Meta Allocation, ...)
if not final.empty:
    keep_final = ["Mã", "Final Decision", "Decision Mode", "Meta Allocation %", "Meta Exposure", "Regime Strength", "Equity State", "Hành động"]
    keep_final = [c for c in keep_final if c in final.columns]
    merged = merged.merge(final[keep_final], on="Mã", how="left")

if not meta.empty:
    keep_meta = ["Mã", "Meta Allocation %", "Meta Exposure", "Decision Mode"]
    keep_meta = [c for c in keep_meta if c in meta.columns]
    merged = merged.merge(meta[keep_meta], on="Mã", how="left", suffixes=("", "_meta"))

if not watch.empty:
    keep_watch = ["Mã", "Nhóm realtime", "Ưu tiên"]
    keep_watch = [c for c in keep_watch if c in watch.columns]
    merged = merged.merge(watch[keep_watch], on="Mã", how="left")

if not pro.empty:
    keep_pro = ["Mã", "Điểm V15.3 cuối cùng", "Kết luận V15.3"]
    keep_pro = [c for c in keep_pro if c in pro.columns]
    merged = merged.merge(pro[keep_pro], on="Mã", how="left")

# ==================== SẮP XẾP ====================
# Ưu tiên mã có chuỗi tăng dài nhất và điểm cao
if "So phien tang dai nhat" in merged.columns:
    merged["So phien tang dai nhat"] = pd.to_numeric(merged["So phien tang dai nhat"], errors="coerce").fillna(0)
if "Meta Allocation %" in merged.columns:
    merged["Meta Allocation %"] = pd.to_numeric(merged["Meta Allocation %"], errors="coerce").fillna(0)
if "Điểm V15.3 cuối cùng" in merged.columns:
    merged["Điểm V15.3 cuối cùng"] = pd.to_numeric(merged["Điểm V15.3 cuối cùng"], errors="coerce").fillna(0)

merged = merged.sort_values(
    by=["So phien tang dai nhat", "Meta Allocation %", "Điểm V15.3 cuối cùng"],
    ascending=[False, False, False]
)

# ==================== XUẤT FILE ====================
merged.to_csv(OUTPUT_MERGED, index=False, encoding="utf-8-sig")
print(f"✅ Đã tạo file {OUTPUT_MERGED} với {len(merged)} dòng.")
print("Các cột chính:", list(merged.columns))
