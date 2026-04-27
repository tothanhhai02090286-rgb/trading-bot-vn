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
        return pd.DataFrame({"info": ["No data"]})
    try:
        df = pd.read_csv(path)
        if df.empty:
            return pd.DataFrame({"info": ["File exists but empty"]})
        return df
    except EmptyDataError:
        return pd.DataFrame({"info": ["File exists but has no columns"]})
    except Exception as e:
        return pd.DataFrame({"info": [f"Read error: {e}"]})

tab1, tab2, tab3, tab4 = st.tabs([
    "🔥 AI FINAL",
    "🧲 BOTTOM",
    "🚀 MOMENTUM",
    "📋 ENTRY"
])

with tab1:
    st.dataframe(load_csv("ai_risk_filtered.csv"), use_container_width=True)

with tab2:
    st.dataframe(load_csv("bottom_common_priority.csv"), use_container_width=True)

with tab3:
    st.dataframe(load_csv("momentum_common_priority.csv"), use_container_width=True)

with tab4:
    st.dataframe(load_csv("entry_plan_next_session.csv"), use_container_width=True)

st.divider()
st.subheader("📁 Files:")

files = [
    "ai_risk_filtered.csv",
    "ai_risk_dashboard.html",
    "bottom_common_priority.csv",
    "momentum_common_priority.csv",
    "entry_plan_next_session.csv"
]

for f in files:
    if os.path.exists(f):
        st.write(f"✅ {f}")
    else:
        st.write(f"❌ {f}")
