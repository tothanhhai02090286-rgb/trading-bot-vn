import os
import pandas as pd
import streamlit as st
from datetime import datetime
from pandas.errors import EmptyDataError

st.set_page_config(page_title="Trading Bot Control Center", layout="wide")

st.title("📊 Trading Bot Control Center")
st.caption(f"Updated: {datetime.now()}")

def load_csv(path):
    if not os.path.exists(path):
        return pd.DataFrame({"info": [f"No data: {path}"]})
    try:
        df = pd.read_csv(path)
        if df.empty:
            return pd.DataFrame({"info": [f"File exists but empty: {path}"]})
        return df
    except EmptyDataError:
        return pd.DataFrame({"info": [f"File exists but has no columns: {path}"]})
    except Exception as e:
        return pd.DataFrame({"info": [f"Read error {path}: {e}"]})


tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🔎 RAW SIGNAL",
    "🔥 AI FINAL",
    "📋 ENTRY",
    "📦 PORTFOLIO",
    "🎯 ACTION PLAN",
    "🧲 BOTTOM",
    "🚀 MOMENTUM"
])

with tab1:
    st.dataframe(load_csv("raw_signal_candidates.csv"), use_container_width=True)

with tab2:
    st.dataframe(load_csv("ai_risk_filtered.csv"), use_container_width=True)

with tab3:
    st.dataframe(load_csv("entry_plan_next_session.csv"), use_container_width=True)

with tab4:
    st.dataframe(load_csv("portfolio_tracker.csv"), use_container_width=True)

with tab5:
    st.dataframe(load_csv("action_plan.csv"), use_container_width=True)

with tab6:
    st.dataframe(load_csv("bottom_common_priority.csv"), use_container_width=True)

with tab7:
    st.dataframe(load_csv("momentum_common_priority.csv"), use_container_width=True)


st.divider()
st.subheader("📁 Files:")

files = [
    "raw_signal_candidates.csv",
    "ai_risk_filtered.csv",
    "entry_plan_next_session.csv",
    "portfolio_tracker.csv",
    "action_plan.csv",
    "bottom_common_priority.csv",
    "momentum_common_priority.csv",
    "all_signal_results.csv",
    "ai_risk_dashboard.html",
]

for f in files:
    if os.path.exists(f):
        st.write(f"✅ {f}")
    else:
        st.write(f"❌ {f}")
