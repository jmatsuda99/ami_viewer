
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import hashlib
import sqlite3
import os
from datetime import date

st.set_page_config(page_title="Contract 30-min Data Visualizer (DB)", layout="wide")
st.title("Contract 30-min Data Visualizer (raw) — with persistent DB")

DB_PATH = "app_data/contract_data.sqlite"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with get_conn() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sha256 TEXT UNIQUE NOT NULL,
            ingested_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_no TEXT NOT NULL UNIQUE
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS readings (
            contract_id INTEGER NOT NULL,
            ymd TEXT NOT NULL,
            time TEXT NOT NULL,
            kwh REAL NOT NULL,
            UNIQUE(contract_id, ymd, time),
            FOREIGN KEY(contract_id) REFERENCES contracts(id)
        )""")

def file_sha256(file_bytes: bytes) -> str:
    import hashlib
    h = hashlib.sha256()
    h.update(file_bytes)
    return h.hexdigest()

def ensure_contract(con, contract_no: str) -> int:
    cur = con.execute("SELECT id FROM contracts WHERE contract_no=?", (contract_no,))
    row = cur.fetchone()
    if row: return row[0]
    cur = con.execute("INSERT INTO contracts(contract_no) VALUES (?)", (contract_no,))
    return cur.lastrowid

def insert_readings(con, contract_id: int, df: pd.DataFrame):
    if "年月日" not in df.columns:
        return
    df = df.copy()
    df["年月日"] = pd.to_datetime(df["年月日"].astype(str), format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["年月日"])
    time_cols = [c for c in df.columns if ":" in str(c)]
    if not time_cols:
        return
    long_df = df[["年月日"] + time_cols].copy().melt(id_vars=["年月日"], var_name="time", value_name="kwh")
    long_df["ymd"] = long_df["年月日"].dt.strftime("%Y-%m-%d")
    long_df["kwh"] = pd.to_numeric(long_df["kwh"], errors="coerce").fillna(0.0)
    con.executemany("""
        INSERT INTO readings(contract_id, ymd, time, kwh)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(contract_id, ymd, time) DO UPDATE SET kwh=excluded.kwh
    """, [(contract_id, r.ymd, r.time, float(r.kwh)) for r in long_df.itertuples(index=False)])

def ingest_excel_to_db(file_bytes: bytes, file_name: str):
    init_db()
    sha = file_sha256(file_bytes)
    with get_conn() as con:
        cur = con.execute("SELECT id FROM files WHERE sha256=?", (sha,))
        if cur.fetchone():
            return False, "This file has already been ingested (by content hash)."
        import io
        xl = pd.ExcelFile(io.BytesIO(file_bytes))
        for sheet in xl.sheet_names:
            df = pd.read_excel(xl, sheet_name=sheet)
            cid = ensure_contract(con, str(sheet))
            insert_readings(con, cid, df)
        con.execute("INSERT INTO files(name, sha256) VALUES (?, ?)", (file_name, sha))
        return True, "Ingest completed."

def list_contracts():
    init_db()
    with get_conn() as con:
        rows = con.execute("SELECT id, contract_no FROM contracts ORDER BY contract_no").fetchall()
    return [{"id": r[0], "contract_no": r[1]} for r in rows]

def list_dates(contract_id: int):
    with get_conn() as con:
        rows = con.execute("SELECT DISTINCT ymd FROM readings WHERE contract_id=? ORDER BY ymd", (contract_id,)).fetchall()
    return [r[0] for r in rows]

def get_series(contract_id: int, ymd: str):
    with get_conn() as con:
        rows = con.execute("SELECT time, kwh FROM readings WHERE contract_id=? AND ymd=? ORDER BY time", (contract_id, ymd)).fetchall()
    if not rows:
        return [], []
    times = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    return times, vals

st.sidebar.header("Data source / DB")
uploaded = st.sidebar.file_uploader("Upload Excel (ingest once → stored in DB)", type=["xlsx"])
if uploaded is not None:
    file_bytes = uploaded.getvalue()
    ok, msg = ingest_excel_to_db(file_bytes, uploaded.name)
    st.sidebar.success(msg) if ok else st.sidebar.info(msg)

default_path = "/mnt/data/契約別_時間帯別（30分）集計_all4_fix.xlsx"
if os.path.exists(default_path):
    if st.sidebar.button("Ingest built-in sample once"):
        with open(default_path, "rb") as f:
            ok, msg = ingest_excel_to_db(f.read(), os.path.basename(default_path))
        st.sidebar.success(msg if ok else msg)

legend_on = st.sidebar.checkbox("Show legend", value=True)
unit = st.sidebar.radio("Unit", ["kWh (30min)", "kW (x2)"], index=0)

def convert(vals):
    return [float(v)*2.0 for v in vals] if unit.startswith("kW") else [float(v) for v in vals]

y_label = "Energy [kWh]" if unit.startswith("kWh") else "Demand [kW]"

contracts = list_contracts()
if not contracts:
    st.warning("No data in DB yet. Upload or ingest a file from the sidebar.")
    st.stop()

contract_labels = [c["contract_no"] for c in contracts]
sel_idx = st.sidebar.selectbox("Contract", list(range(len(contract_labels))), format_func=lambda i: contract_labels[i])
sel_contract = contracts[sel_idx]

tabs = st.tabs(["Single day", "Overlay period", "DB admin"])

with tabs[0]:
    dates = list_dates(sel_contract["id"])
    if not dates:
        st.info("No dates for this contract.")
    else:
        day_sel = st.selectbox("Date", dates, index=0)
        times, vals = get_series(sel_contract["id"], day_sel)
        vals = convert(vals)
        fig, ax = plt.subplots(figsize=(12,4))
        try:
            plt.rcParams["font.family"] = "Noto Sans CJK JP"
        except Exception:
            pass
        ax.plot(times, vals, label=f"{sel_contract['contract_no']}")
        ax.set_title(f"Contract {sel_contract['contract_no']} | {day_sel} (30min, {unit})")
        ax.set_xlabel("Time")
        ax.set_ylabel(y_label)
        if legend_on: ax.legend()
        plt.xticks(rotation=45)
        st.pyplot(fig, use_container_width=True)

with tabs[1]:
    dates = list_dates(sel_contract["id"])
    if not dates:
        st.info("No dates for this contract.")
    else:
        col1, col2 = st.columns(2)
        start_d = col1.selectbox("Start date", dates, index=0)
        end_d = col2.selectbox("End date", dates, index=len(dates)-1)
        start_idx = dates.index(start_d)
        end_idx = dates.index(end_d)
        if start_idx > end_idx:
            st.error("Start date is after end date.")
        else:
            sel_range = dates[start_idx:end_idx+1]
            fig2, ax2 = plt.subplots(figsize=(12,5))
            try:
                plt.rcParams["font.family"] = "Noto Sans CJK JP"
            except Exception:
                pass
            for d in sel_range:
                t, v = get_series(sel_contract["id"], d)
                v = convert(v)
                ax2.plot(t, v, label=d)
            ax2.set_title(f"Contract {sel_contract['contract_no']} | {sel_range[0]} ~ {sel_range[-1]} (Overlay / {unit})")
            ax2.set_xlabel("Time")
            ax2.set_ylabel(y_label)
            if legend_on: ax2.legend(ncol=3, fontsize=8)
            plt.xticks(rotation=45)
            st.pyplot(fig2, use_container_width=True)

with tabs[2]:
    st.subheader("DB info")
    with get_conn() as con:
        fcnt = con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        ccnt = con.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
        rcnt = con.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    st.write(f"Files: {fcnt}, Contracts: {ccnt}, Readings: {rcnt}")
    c1, c2 = st.columns(2)
    if c1.button("Export DB"):
        with open(DB_PATH, "rb") as f:
            st.download_button("Download contract_data.sqlite", data=f, file_name="contract_data.sqlite", mime="application/octet-stream")
    if c2.button("Clear ALL data (danger)"):
        os.remove(DB_PATH)
        st.warning("DB removed. Please refresh the page.")
