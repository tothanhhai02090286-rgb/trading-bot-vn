# ================================
# 🚀 V10 STABLE - FIXED TELEGRAM VERSION
# ================================

SYSTEM_VERSION = "V10 STABLE"

from datetime import datetime

def build_telegram_message(source_df, run_time, data_date):
    # Case 1: no data
    if source_df is None or len(source_df) == 0:
        return (
            f"TRADING BOT {SYSTEM_VERSION}\n"
            f"Run time: {run_time}\n"
            f"Data date: {data_date}\n"
            "Status: NO REAL SIGNAL\n"
            "Reason: market closed / no new data / no setup passed filter\n"
            "Dashboard HTML attached."
        )

    # Case 2: only NO_SIGNAL rows
    if "Mã" in source_df.columns:
        if source_df["Mã"].astype(str).str.contains("NO_SIGNAL|NO_ACTION", na=False).all():
            return (
                f"TRADING BOT {SYSTEM_VERSION}\n"
                f"Run time: {run_time}\n"
                f"Data date: {data_date}\n"
                "Status: NO REAL SIGNAL\n"
                "Reason: market closed / no new data / no setup passed filter\n"
                "Dashboard HTML attached."
            )

    # Case 3: real signals
    return (
        f"TRADING BOT {SYSTEM_VERSION}\n"
        f"Run time: {run_time}\n"
        f"Data date: {data_date}\n"
        "Status: SIGNAL DETECTED\n"
        "Check dashboard for details."
    )


def send_telegram_alert(source_df):
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data_date = datetime.now().strftime("%Y-%m-%d")

    msg = build_telegram_message(source_df, run_time, data_date)

    if not msg:
        print("No message to send")
        return

    print("SEND TELEGRAM:")
    print(msg)

