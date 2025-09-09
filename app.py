
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import date
import os

st.set_page_config(page_title="契約別 30分データ可視化ツール", layout="wide")
st.title("契約別 30分データ 可視化ツール（無加工）")

st.markdown("""
- **契約番号** と **日付**（単日）を選ぶと、その日の30分単位グラフを表示します。  
- **開始日・終了日** を指定すると、指定期間の各日を重ねて表示します（凡例=日付）。  
- 単位は **kWh(30分値)** と **kW換算(x2)** を切替できます。  
- **Legend**（凡例）の表示/非表示を切替できます。  
- **Axis labels** は英語（X: Time / Y: Energy [kWh] or Demand [kW]）。
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
uploaded = st.sidebar.file_uploader("Excel（例：契約別_時間帯別（30分）集計_all4_fix.xlsx）", type=["xlsx"])
default_path = "/mnt/data/契約別_時間帯別（30分）集計_all4_fix.xlsx"
use_default = False
if uploaded is None and os.path.exists(default_path):
    st.sidebar.info("アップロードが無いので、既定ファイルを使用します。")
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
    st.warning("Excelファイルをアップロードしてください。")
    st.stop()

contracts = list(data_map.keys())
contract = st.sidebar.selectbox("契約番号", contracts, index=0)

df = data_map[contract].copy()
if "年月日" not in df.columns:
    st.error("このシートに「年月日」列が見つかりません。")
    st.stop()

time_cols = [c for c in df.columns if ":" in str(c)]
if not time_cols:
    st.error("時刻列が見つかりません（'00:00:00' 等）。")
    st.stop()

tab1, tab2 = st.tabs(["単日表示", "期間重ね表示"])

with tab1:
    days = sorted(df["年月日"].dropna().dt.date.unique())
    if not len(days):
        st.warning("有効な日付が見つかりません。")
    else:
        day_sel = st.selectbox("日付を選択", days, index=0, format_func=lambda d: d.strftime("%Y-%m-%d"))
        row = df[df["年月日"].dt.date == day_sel]
        if row.empty:
            st.warning("選択日のデータが見つかりません。")
        else:
            y = convert_values(row[time_cols].iloc[0]).values.flatten()
            fig, ax = plt.subplots(figsize=(12,4))
            try:
                plt.rcParams["font.family"] = "Noto Sans CJK JP"
            except Exception:
                pass
            ax.plot(time_cols, y, label=f"{contract}")
            ax.set_title(f"{contract} | {day_sel.strftime('%Y-%m-%d')} 30分単位（{unit}）")
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
        start_d = st.date_input("開始日", value=min_d, min_value=min_d, max_value=max_d)
    with col2:
        end_d = st.date_input("終了日", value=max_d, min_value=min_d, max_value=max_d)

    if start_d > end_d:
        st.error("開始日が終了日より後になっています。")
    else:
        mask = (df["年月日"].dt.date >= start_d) & (df["年月日"].dt.date <= end_d)
        sub = df.loc[mask]
        if sub.empty:
            st.warning("指定期間のデータが見つかりません。")
        else:
            fig2, ax2 = plt.subplots(figsize=(12,5))
            try:
                plt.rcParams["font.family"] = "Noto Sans CJK JP"
            except Exception:
                pass
            for _, row in sub.sort_values("年月日").iterrows():
                lab = row["年月日"].date().strftime("%Y-%m-%d")
                ax2.plot(time_cols, convert_values(row[time_cols]).values.flatten(), label=lab)
            ax2.set_title(f"{contract} | {start_d.strftime('%Y-%m-%d')}〜{end_d.strftime('%Y-%m-%d')}（各日重ね / {unit}）")
            ax2.set_xlabel("Time")
            ax2.set_ylabel(y_label)
            if legend_on:
                ax2.legend(ncol=3, fontsize=8)
            plt.xticks(rotation=45)
            st.pyplot(fig2, use_container_width=True)
