
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import date
import os

st.set_page_config(page_title="Contract 30-min Data Visualizer", layout="wide")
st.title("Contract 30-min Data Visualizer (raw)")

st.markdown("""
- Select **Contract** and **Date** to show that day's 30-min series.  
- Set **Start / End** to overlay each day in the period (legend = date).  
- Toggle **kWh (30min)** vs **kW (x2)**.  
- Toggle **Legend** on/off.  
- Axis labels are in English.
""")

@st.cache_data(show_spinner=False)
def load_excel(file) -> dict:
    if file is None:
        return {}
    xl = pd.ExcelFile(file)
    data = {}
    for sheet in xl.sheet_names:
        df = pd.read_excel(xl, sheet_name=sheet)
        if "年月日" in df.columns:
            df["年月日"] = pd.to_datetime(df["年月日"].astype(str), format="%Y%m%d", errors="coerce")
        data[sheet] = df
    return data

# Sidebar controls
st.sidebar.header("Settings")
uploaded = st.sidebar.file_uploader("Excel file (e.g., 契約別_時間帯別（30分）集計_all4_fix.xlsx)", type=["xlsx"])
default_path = "/mnt/data/契約別_時間帯別（30分）集計_all4_fix.xlsx"
use_default = False
if uploaded is None and os.path.exists(default_path):
    st.sidebar.info("No upload provided. Using the default file available in the workspace.")
    use_default = True

legend_on = st.sidebar.checkbox("Show legend", value=True)
unit = st.sidebar.radio("Unit", ["kWh (30min)", "kW (x2)"], index=0)

def convert_values(series):
    if unit.startswith("kW"):
        return series.astype(float) * 2.0
    return series.astype(float)

y_label = "Energy [kWh]" if unit.startswith("kWh") else "Demand [kW]"

data_map = load_excel(uploaded if not use_default else default_path)
if not data_map:
    st.warning("Please upload an Excel file.")
    st.stop()

contracts = list(data_map.keys())
contract = st.sidebar.selectbox("Contract", contracts, index=0)

df = data_map[contract].copy()
if "年月日" not in df.columns:
    st.error("Column '年月日' not found in this sheet.")
    st.stop()

time_cols = [c for c in df.columns if ":" in str(c)]
if not time_cols:
    st.error("Time columns not found (e.g., '00:00:00').")
    st.stop()

tab1, tab2 = st.tabs(["Single day", "Overlay period"])

with tab1:
    days = sorted(df["年月日"].dropna().dt.date.unique())
    if not len(days):
        st.warning("No valid dates found.")
    else:
        day_sel = st.selectbox("Date", days, index=0, format_func=lambda d: d.strftime("%Y-%m-%d"))
        row = df[df["年月日"].dt.date == day_sel]
        if row.empty:
            st.warning("No data for the selected date.")
        else:
            y = convert_values(row[time_cols].iloc[0]).values.flatten()
            fig, ax = plt.subplots(figsize=(12,4))
            try:
                plt.rcParams["font.family"] = "Noto Sans CJK JP"
            except Exception:
                pass
            ax.plot(time_cols, y, label=f"{contract}")
            # English title
            ax.set_title(f"Contract {contract} | {day_sel.strftime('%Y-%m-%d')} (30min, {unit})")
            ax.set_xlabel("Time")
            ax.set_ylabel(y_label)
            if legend_on:
                ax.legend()
            plt.xticks(rotation=45)
            st.pyplot(fig, use_container_width=True)

with tab2:
    col1, col2 = st.columns(2)
    all_days = sorted(df["年月日"].dropna().dt.date.unique())
    if len(all_days):
        min_d, max_d = min(all_days), max(all_days)
    else:
        min_d, max_d = date(2023,1,1), date(2023,12,31)

    with col1:
        start_d = st.date_input("Start date", value=min_d, min_value=min_d, max_value=max_d)
    with col2:
        end_d = st.date_input("End date", value=max_d, min_value=min_d, max_value=max_d)

    if start_d > end_d:
        st.error("Start date is after end date.")
    else:
        mask = (df["年月日"].dt.date >= start_d) & (df["年月日"].dt.date <= end_d)
        sub = df.loc[mask]
        if sub.empty:
            st.warning("No data in the selected period.")
        else:
            fig2, ax2 = plt.subplots(figsize=(12,5))
            try:
                plt.rcParams["font.family"] = "Noto Sans CJK JP"
            except Exception:
                pass
            for _, row in sub.sort_values("年月日").iterrows():
                lab = row["年月日"].date().strftime("%Y-%m-%d")
                ax2.plot(time_cols, convert_values(row[time_cols]).values.flatten(), label=lab)
            # English title
            ax2.set_title(f"Contract {contract} | {start_d.strftime('%Y-%m-%d')} ~ {end_d.strftime('%Y-%m-%d')} (Overlay / {unit})")
            ax2.set_xlabel("Time")
            ax2.set_ylabel(y_label)
            if legend_on:
                ax2.legend(ncol=3, fontsize=8)
            plt.xticks(rotation=45)
            st.pyplot(fig2, use_container_width=True)
