from v10_config import *
from v10_utils import *
from v10_indicators import *
from v10_market_data import fetch_history
import pandas as pd

def score_momentum(row):
    score = 0
    if row["MA5"] > row["MA20"]:
        score += 15
    if 55 <= row["RSI"] <= 75:
        score += 15
    if row["Ret5 %"] > 2:
        score += 10
    if row["Ret10 %"] > 3:
        score += 10
    if row["RS20"] > 0:
        score += 10
    if row["Volume Ratio"] > 1.2:
        score += 10
    if row["ADX"] > 20:
        score += 10
    if row["ATR %"] <= 8:
        score += 10
    if row["MACD Hist Up"]:
        score += 5
    if 0 <= row["Dist MA20 %"] <= 12:
        score += 5
    return score


def score_bottom(row):
    score = 0
    if 30 <= row["RSI"] <= 48:
        score += 15
    if row["Drawdown20 %"] <= -5:
        score += 15
    if row["Rebound Low20 %"] >= 1:
        score += 10
    if row["Volume Ratio"] >= 0.8:
        score += 10
    if row["Close"] >= row["Low20"]:
        score += 10
    if row["ATR %"] <= 9:
        score += 10
    if row["RS20"] > -8:
        score += 10
    if row["Dist MA20 %"] <= 3:
        score += 10
    if row["MACD Hist Up"]:
        score += 10
    return score


def classify_strategy(row):
    if row["Momentum Score"] >= 75 and row["Momentum Score"] >= row["Bottom Score"]:
        return "MOMENTUM"
    if row["Bottom Score"] >= 70 and row["Bottom Score"] > row["Momentum Score"]:
        return "BOTTOM"
    if row["Momentum Score"] >= 60:
        return "MOMENTUM_WATCH"
    if row["Bottom Score"] >= 55:
        return "BOTTOM_WATCH"
    return "WATCH"


def risk_filter(row):
    reasons = []

    if row["RSI"] >= 90:
        reasons.append("RSI HOT")
    if row["ATR %"] > 10:
        reasons.append("ATR HIGH")
    if row["Volume Ratio"] < 0.7:
        reasons.append("VOLUME WEAK")
    if row["RS20"] < -10:
        reasons.append("RS20 WEAK")

    if row.get("Chien luoc", "") == "MOMENTUM" and row["Close"] < row["MA20"]:
        reasons.append("MOMENTUM BELOW MA20")

    if len(reasons) == 0:
        return "PASS", ""
    return "FAIL", "; ".join(reasons)


def classify_action(row):
    if row["Risk Status"] == "FAIL":
        return "SKIP"
    if row["RSI"] >= 90:
        return "SKIP"
    if 85 <= row["RSI"] < 90:
        return "WATCHLIST"
    if 75 <= row["RSI"] < 85:
        return "WAIT"

    if row.get("Chien luoc", "") == "MOMENTUM" and row["Momentum Score"] >= 80:
        return "BUY NOW"
    if row.get("Chien luoc", "") == "BOTTOM" and row["Bottom Score"] >= 75:
        return "BUY NOW"

    if row.get("Chien luoc", "") in ["MOMENTUM", "BOTTOM"]:
        return "WAIT"
    if row.get("Chien luoc", "") in ["MOMENTUM_WATCH", "BOTTOM_WATCH"]:
        return "WATCHLIST"

    return "SKIP"


def make_signal(row):
    s = row.get("Chien luoc", "")

    if s == "MOMENTUM":
        return "MOMENTUM"
    if s == "BOTTOM":
        return "BOTTOM"
    if s == "MOMENTUM_WATCH":
        return "MOMENTUM WATCH"
    if s == "BOTTOM_WATCH":
        return "BOTTOM WATCH"

    return "WATCH"


def analyze_symbol(symbol, market_ret20):
    """
    Hàm phân tích kỹ thuật và trích xuất toàn bộ dữ liệu chỉ báo,
    bao gồm cả cấu trúc nến VSA phục vụ cho việc đọc vị của Hội đồng AI.
    """
    df, fetch_mode = fetch_history(symbol)

    if df.empty or len(df) < 60:
        return None

    df = add_indicators(df)
    last = df.iloc[-1]

    # Trích xuất dữ liệu OHLC để tính toán hình dáng thân nến VSA
    open_p = safe_float(last.get("open"))
    high_p = safe_float(last.get("high"))
    low_p = safe_float(last.get("low"))
    close = safe_float(last.get("close"))
    
    ma5 = safe_float(last.get("MA5"))
    ma20 = safe_float(last.get("MA20"))
    rsi = safe_float(last.get("RSI"))
    rsi_ma5 = safe_float(last.get("RSI_MA5"))

    if pd.isna(close) or pd.isna(ma5) or pd.isna(ma20) or pd.isna(rsi):
        return None
        
    # Tính toán các thông số cấu trúc giá theo mẫu hình VSA
    if open_p and high_p and low_p:
        candle_spread = high_p - low_p
        candle_body = close - open_p
        
        # Vị trí giá đóng cửa trong phiên (0% = thấp nhất phiên, 100% = cao nhất phiên)
        if candle_spread > 0:
            close_position = ((close - low_p) / candle_spread) * 100
        else:
            close_position = 50.0
    else:
        candle_spread, candle_body, close_position = 0.0, 0.0, 50.0

    ret5 = safe_float(last.get("Ret5 %"), 0)
    ret10 = safe_float(last.get("Ret10 %"), 0)
    ret20 = safe_float(last.get("Ret20 %"), 0)
    rs20 = ret20 - market_ret20

    row = {
        "Ngay": get_price_data_date(df),
        "Ma": symbol,
        "Open": round(open_p, 2) if open_p else 0.0,
        "High": round(high_p, 2) if high_p else 0.0,
        "Low": round(low_p, 2) if low_p else 0.0,
        "Close": round(close, 2),
        "Candle Spread": round(candle_spread, 2),     # Biên độ dao động của phiên liền trước
        "Candle Body": round(candle_body, 2),         # Thân nến (Dương = Xanh, Âm = Đỏ)
        "Close Position %": round(close_position, 1), # Vị trí đóng cửa (Nhận diện râu nến/rút chân)
        "MA5": round(ma5, 2),
        "MA20": round(ma20, 2),
        "RSI": round(rsi, 2),
        "RSI_MA5": round(rsi_ma5, 2) if not pd.isna(rsi_ma5) else 0.0,
        "RSI_Above_MA5": bool(rsi > rsi_ma5) if not pd.isna(rsi_ma5) else False,
        "Ret5 %": round(ret5, 2),
        "Ret10 %": round(ret10, 2),
        "Ret20 %": round(ret20, 2),
        "RS20": round(rs20, 2),
        "Volume Ratio": round(safe_float(last.get("Volume Ratio"), 0), 2),
        "ADX": round(safe_float(last.get("ADX"), 0), 2),
        "ATR %": round(safe_float(last.get("ATR %"), 999), 2),
        "MACD Hist": round(safe_float(last.get("MACD Hist"), 0), 4),
        "MACD Hist Up": bool(last.get("MACD Hist Up")),
        "Dist MA20 %": round(safe_float(last.get("Dist MA20 %"), 0), 2),
        "Drawdown20 %": round(safe_float(last.get("Drawdown20 %"), 0), 2),
        "Rebound Low20 %": round(safe_float(last.get("Rebound Low20 %"), 0), 2),
        "Low20": round(safe_float(last.get("Low20"), 0), 2),
        "High20": round(safe_float(last.get("High20"), 0), 2),
        "Fetch Mode": fetch_mode,
        "Updated": now_vietnam().strftime("%Y-%m-%d %H:%M:%S"),
        "Version": SYSTEM_VERSION
    }

    row["Momentum Score"] = score_momentum(row)
    row["Bottom Score"] = score_bottom(row)
    row["Score"] = max(row["Momentum Score"], row["Bottom Score"])
    row["Chien luoc"] = classify_strategy(row)

    risk_status, risk_reason = risk_filter(row)
    row["Risk Status"] = risk_status
    row["Risk Reason"] = risk_reason

    row["Action"] = classify_action(row)
    row["Signal"] = make_signal(row)

    return row


def generate_ai_council_prompt(row):
    """
    Hàm bổ trợ đóng gói dữ liệu kỹ thuật thành một câu lệnh hệ thống chi tiết.
    Đảm bảo Hội đồng AI nhận định chuẩn xác theo trường phái VSA + Lý thuyết Dow
    và bắt buộc phải trả về trường 'Canh_bao_VSA'.
    """
    system_instruction = (
        "Bạn là chuyên gia phân tích kỹ thuật cấp cao thuộc Hội đồng AI của hệ thống Strike Zone, "
        "vận dụng thuần thục Lý thuyết Dow và phương pháp VSA (Volume Spread Analysis).\n"
        "Nhiệm vụ của bạn là kiểm tra tính hợp lý của dòng tiền dựa trên các tham số được cung cấp, "
        "đọc vị hành vi của Smart Money và đưa ra nhận định thực chiến độc lập.\n\n"
        "CÁC NGUYÊN TẮC PHÂN TÍCH CỐT LÕI VSA & DOW THỰC CHIẾN:\n"
        "1. Xu hướng bền vững: Giá tăng + Volume Ratio tăng (>1.2) + nằm trên MA -> Xu hướng tăng khỏe.\n"
        "2. Phân kỳ suy yếu: Giá tăng nhưng Volume Ratio sụt giảm dưới 1.0 -> Cầu yếu, nguy cơ bẫy tăng giá hoặc điều chỉnh ngắn hạn.\n"
        "3. Đọc vị bất thường (Nến & Khối lượng):\n"
        "   - Candle Spread nhỏ (thân nến hẹp) nhưng Volume Ratio cực cao (>1.5): Sự tranh chấp dữ dội, dấu hiệu gom hàng ở đáy hoặc phân phối ở đỉnh.\n"
        "   - Close Position % cao (>80%) đi kèm râu dưới dài và Vol lớn: Dấu hiệu dòng tiền bắt đáy, rút chân mạnh mẽ.\n"
        "   - Close Position % thấp (<20%) khi đang ở đỉnh xu hướng tăng kèm Vol lớn: Lực xả mạnh dội ngược từ phía trên.\n"
    )
    
    user_data_input = f"""
--- DỮ LIỆU KỸ THUẬT CỦA MÃ: {row['Ma']} ---
- Ngày phân tích: {row['Ngay']}
- Giá đóng cửa: {row['Close']} (Biên độ nến: {row['Candle Spread']}, Giá trị thân nến: {row['Candle Body']})
- Vị trí đóng cửa trong phiên: {row['Close Position %']}%
- Điểm Kỹ thuật: Momentum {row['Momentum Score']} | Bottom {row['Bottom Score']} -> Chiến lược gợi ý: {row['Chien luoc']}
- Trạng thái dòng tiền & Xu hướng:
  + Xu hướng RSI: {row['RSI']} (Đường RSI đang {'NẰM TRÊN' if row['RSI_Above_MA5'] else 'NẰM DƯỚI'} đường RSI_MA5)
  + Khối lượng (Volume Ratio): {row['Volume Ratio']}
  + Khoảng cách tới MA20: {row['Dist MA20 %']}%
  + Xu hướng MACD Hist hướng lên: {row['MACD Hist Up']}
- Đánh giá Rủi ro Kỹ thuật: Trạng thái: {row['Risk Status']} (Lý do: {row['Risk Reason'] if row['Risk Reason'] else 'Không có'})
- Hành động khuyến nghị từ Code: {row['Action']}
"""

    format_requirement = (
        "\nBẠN PHẢI TRẢ VỀ ĐẦU RA THEO ĐỊNH DẠNG JSON CHÍNH XÁC (KHÔNG KÈM THEO LỜI DẪN GIẢI KÝ TỰ LẠ):\n"
        "{\n"
        f'  "Ma_CP": "{row["Ma"]}",\n'
        '  "Tin_hieu_AI": "MUA / CHỜ ĐỢI / BỎ QUA",\n'
        '  "Canh_bao_VSA": "Nhận định ngắn gọn 1-2 câu về hành vi dòng tiền lớn dựa trên nến, volume và xu hướng ở trên.",\n'
        '  "Diem_tin_cay": "Chấm điểm từ 1 đến 10 cho cơ hội này"\n'
        "}"
    )
    
    return {"system_prompt": system_instruction, "prompt_body": user_data_input + format_requirement}
