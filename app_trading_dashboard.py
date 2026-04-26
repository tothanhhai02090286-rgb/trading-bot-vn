import os
import subprocess
import pandas as pd
import streamlit as st
from datetime import datetime

from config import BOT_DIR
BOT_DIR = str(BOT_DIR)
os.chdir(BOT_DIR)

st.set_page_config(page_title="Trading Bot Dashboard", layout="wide")

st.title("📊 Trading Bot Control Center")
st.caption(f"Updated: {datetime.now()}")

def run_cmd(cmd):
    with st.spinner(f"Đang chạy: {cmd}"):
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        st.code(p.stdout[-3000:])
        if p.stderr:
            st.error(p.stderr[-2000:])

def load_csv(name):
    path = f"{BOT_DIR}/{name}"
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame()

# ===== BUTTON =====
st.sidebar.header("🚀 Control")

if st.sidebar.button("⚡ FAST SYSTEM"):
    run_cmd(f"python {BOT_DIR}/run_fast_system.py")

if st.sidebar.button("🚀 FULL SYSTEM"):
    run_cmd(f"python {BOT_DIR}/run_daily_system.py")

if st.sidebar.button("🤖 AI FILTER"):
    run_cmd(f"python {BOT_DIR}/ai_risk_filter.py")

if st.sidebar.button("🌐 CREATE HTML"):
    run_cmd(f"python {BOT_DIR}/create_html.py")

# ===== TABLE =====
tab1, tab2, tab3, tab4 = st.tabs([
    "🔥 AI FINAL",
    "🧲 BOTTOM",
    "🚀 MOMENTUM",
    "📋 ENTRY"
])

with tab1:
    df = load_csv("ai_risk_filtered.csv")
    st.dataframe(df if not df.empty else pd.DataFrame({"info":["No data"]}), use_container_width=True)

with tab2:
    df = load_csv("bottom_common_priority.csv")
    st.dataframe(df if not df.empty else pd.DataFrame({"info":["No data"]}), use_container_width=True)

with tab3:
    df = load_csv("momentum_common_priority.csv")
    st.dataframe(df if not df.empty else pd.DataFrame({"info":["No data"]}), use_container_width=True)

with tab4:
    df = load_csv("entry_plan_next_session.csv")
    st.dataframe(df if not df.empty else pd.DataFrame({"info":["No data"]}), use_container_width=True)

st.divider()
st.write("📁 Files:")

files = [
    "ai_risk_filtered.csv",
    "ai_risk_dashboard.html",
    "bottom_common_priority.csv",
    "momentum_common_priority.csv"
]

for f in files:
    st.write(("✅" if os.path.exists(f"{BOT_DIR}/{f}") else "❌"), f)
