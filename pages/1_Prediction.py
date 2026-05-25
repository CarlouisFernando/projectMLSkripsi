# import library
import json
import pickle

import lightgbm as lgb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import os

from utils.db import init_db, upsert_dataframe, read_table, save_predictions
from utils.export_utils import build_prediction_zip, to_csv_bytes, to_excel_bytes
from utils.history import get_user_history, save_history
from utils.predictor import run_prediction
from utils.scraper import fetch_usd_idr, get_update_date_range, scrape_antam
from utils.static_data import (
    load_static_data,
    merge_into_static,
    parse_bi_rate_upload,
    parse_inflation_upload,
    parse_xau_upload,
)

def fig_to_png_bytes(fig):
    return fig.to_image(format="png", scale=2)

def clear_prediction_state():
    keep_keys = {"user_id", "username"}
    keep_state = {k: st.session_state[k] for k in keep_keys if k in st.session_state}
    st.session_state.clear()
    st.session_state.update(keep_state)
    st.session_state.pred_df = None
    st.session_state.master_df = None
    st.session_state.horizon = 1
    st.session_state.is_past_prediction = False
    st.session_state.base_date = None
    st.session_state.csv_bytes = None
    st.session_state.excel_bytes = None
    st.session_state.zip_bytes = None

# auth check
if "user_id" not in st.session_state:
    st.warning("Silahkan Login Terlebih Dahulu")
    st.stop()

st.title("Prediction Page")
st.caption("Update data terbaru, Menjalankan proses forecasting, Serta menyimpan hasil prediksi.")

init_db()

# Load data for validation
try:
    antam_df = read_table("antam_prices")
    if not antam_df.empty:
        antam_df['date'] = pd.to_datetime(antam_df['date'])
        if 'harga_emas_antam_idr' in antam_df.columns:
            antam_df['harga_emas_antam_idr'] = pd.to_numeric(antam_df['harga_emas_antam_idr'], errors='coerce')
except:
    antam_df = pd.DataFrame()

# session state
if "pred_df" not in st.session_state:
    st.session_state.pred_df = None
if "master_df" not in st.session_state:
    st.session_state.master_df = None
if "horizon" not in st.session_state:
    st.session_state.horizon = 1
if "is_past_prediction" not in st.session_state:
    st.session_state.is_past_prediction = False
if "base_date" not in st.session_state:
    st.session_state.base_date = None
if "csv_bytes" not in st.session_state:
    st.session_state.csv_bytes = None
if "excel_bytes" not in st.session_state:
    st.session_state.excel_bytes = None
if "zip_bytes" not in st.session_state:
    st.session_state.zip_bytes = None

# header actions
top1, top2 = st.columns([1, 5])
with top1:
    if st.button("Logout", use_container_width=True):
        st.session_state.clear()
        st.switch_page("pages/0_Login.py")

# horizon
horizon = st.selectbox(
    "Pilih Horizon Prediksi",
    [1, 2, 3, 4, 5, 6, 7],
    index=[1, 2, 3, 4, 5, 6, 7].index(st.session_state.horizon)
    if st.session_state.horizon in [1, 2, 3, 4, 5, 6, 7]
    else 0,
    format_func=lambda x: f"H+{x}",
)
st.session_state.horizon = horizon

# mode prediksi
is_past_prediction = st.checkbox(
    "Prediksi Masa Lalu (Untuk Evaluasi Model)",
    value=st.session_state.is_past_prediction,
)
st.session_state.is_past_prediction = is_past_prediction
base_date = None
if is_past_prediction:
    base_date = st.date_input(
        "Pilih tanggal awal untuk prediksi masa lalu",
        value=st.session_state.base_date if st.session_state.base_date else pd.Timestamp.today() - pd.DateOffset(days=30),
        max_value=pd.Timestamp.today().date(),
    )
    st.session_state.base_date = base_date
    # Validasi tanggal base
    if base_date and not antam_df.empty:
        min_date = pd.to_datetime(antam_df['date'].min())
        max_date = pd.to_datetime(antam_df['date'].max())
        
        if pd.to_datetime(base_date) < min_date:
            st.warning(f"Tanggal base minimal adalah {min_date.date()}. Data historis tidak mencakup tanggal tersebut")
        elif pd.to_datetime(base_date) > max_date:
            st.warning(f"Tanggal base maksimal adalah {max_date.date()}. Tidak bisa memprediksi masa depan")
        else:
            # Check if there's enough historical data before base_date (at least 30 days)
            data_before_base = antam_df[antam_df['date'] < pd.to_datetime(base_date)]
            if len(data_before_base) < 30:
                st.warning(f"Data historis sebelum tanggal base terlalu sedikit ({len(data_before_base)} hari). Minimal 30 hari diperlukan untuk akurasi model")

# setup data historis
with st.expander("Setup Data Historis", expanded=False):
    st.write(
        "Gunakan fitur ini untuk pertama kali untuk mengisi data historis harga emas Antam "
        "dan Kurs USD/IDR sebelum menjalankan prediksi"
    )

    hist_start = st.date_input("Tanggal Mulai Historis", value=pd.to_datetime("2019-01-01"))
    hist_end = st.date_input("Tanggal Akhir Historis", value=pd.Timestamp.today().date())

    if st.button("Inisialisasi Data Historis", use_container_width=True):
        try:
            start_str = pd.to_datetime(hist_start).strftime("%Y-%m-%d")
            end_str = pd.to_datetime(hist_end).strftime("%Y-%m-%d")

            with st.spinner("Mengambil Data Historis..."):
                antam_df = scrape_antam(start_str, end_str)
                usd_df = fetch_usd_idr(start_str, end_str)

            upsert_dataframe(antam_df, "antam_prices")
            upsert_dataframe(usd_df, "usd_idr_rates")

            st.success(
                f"Data Historis Berhasil Disimpan\n\n"
                f"- antam: {len(antam_df)} baris ({antam_df['date'].min()} s/d {antam_df['date'].max()})\n"
                f"- usd/idr: {len(usd_df)} baris ({usd_df['date'].min()} s/d {usd_df['date'].max()})"
            )

        except Exception as e:
            st.error(f"Gagal Inisialisasi Data Historis: {e}")

# update static manual
with st.expander("Update Data Static Manual per Variabel", expanded=False):
    st.write(
        "Upload data XAU/USD, Inflasi, dan BI Rate secara terpisah. "
        "Sistem akan proses otomatis dari format mentah sumber data"
    )

    st.markdown("### Contoh Data")
    st.write("Download file CSV yang sudah sesuai template untuk setiap variabel.")
    st.markdown("### Sumber")
    st.markdown(
        """
1. [Inflasi (Sumber : Bank Indonesia)](https://www.bi.go.id/id/statistik/indikator/data-inflasi.aspx)
2. [BI Rate (Sumber : Bank Indonesia)](https://www.bi.go.id/id/statistik/indikator/bi-rate.aspx)
3. [XAU/USD Data Historis (Sumber : Investing.com)](https://id.investing.com/currencies/xau-usd-historical-data)
"""
    )
    t1, t2, t3 = st.columns(3)
    # Tampilkan template contoh dan sediakan tombol download CSV
    with t1:
        st.markdown("**Template XAU/USD**")
        
        # Prefer user-provided template files under templates/ if available
        template_dir = "templates"
        xau_path = os.path.join("template", "Template_XAU.csv")
        if os.path.exists(xau_path):
            with open(xau_path, "rb") as f:
                data_bytes = f.read()
            st.download_button(
                label="Download contoh yg benar (XAU/USD)",
                data=data_bytes,
                file_name="template_xau_usd.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_xau_template",
            )
        else:
            st.download_button(
                label="Download contoh yg benar (XAU/USD)",
                data=xau_csv,
                file_name="template_xau_usd.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_xau_template",
            )

    with t2:
        st.markdown("**Template Inflasi YoY**")
        infl_path = os.path.join("template", "Template_Inflasi.csv")
        if os.path.exists(infl_path):
            with open(infl_path, "rb") as f:
                data_bytes = f.read()
            st.download_button(
                label="Download contoh yg benar (Inflasi)",
                data=data_bytes,
                file_name="Template_Inflasi.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_infl_template",
            )
        else:
            st.download_button(
                label="Download contoh yg benar (Inflasi)",
                data=infl_csv,
                file_name="template_inflasi.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_infl_template",
            )

    with t3:
        st.markdown("**Template BI Rate**")
        bi_path = os.path.join("template", "Template_BI.csv")
        if os.path.exists(bi_path):
            with open(bi_path, "rb") as f:
                data_bytes = f.read()
            st.download_button(
                label="Download contoh yg benar (BI Rate)",
                data=data_bytes,
                file_name="template_bi_rate.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_bi_template",
            )
        else:
            st.download_button(
                label="Download contoh yg benar (BI Rate)",
                data=bi_csv,
                file_name="template_bi_rate.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_bi_template",
            )

    c1, c2, c3 = st.columns(3)

    with c1:
        xau_file = st.file_uploader(
            "Upload XAU/USD",
            type=["csv", "xls", "xlsx"],
            key="xau_upload",
        )

        if st.button("update xau/usd", use_container_width=True):
            try:
                if xau_file is None:
                    st.warning("Silahkan upload file XAU/USD terlebih dahulu")
                else:
                    parsed_xau = parse_xau_upload(xau_file)
                    info = merge_into_static(parsed_xau, "xau_usd")
                    st.success(
                        f"XAU/USD Berhasil Diperbarui\n\n"
                        f"- jumlah baris: {info['rows_uploaded']}\n"
                        f"- rentang: {info['date_min']} s/d {info['date_max']}"
                    )
            except Exception as e:
                st.error(f"Gagal Update XAU/USD: {e}")

    with c2:
        inflasi_file = st.file_uploader(
            "Upload Inflasi",
            type=["csv", "xls", "xlsx"],
            key="inflasi_upload",
        )

        if st.button("update inflasi", use_container_width=True):
            try:
                if inflasi_file is None:
                    st.warning("Silahkan upload file inflasi terlebih dahulu")
                else:
                    parsed_infl = parse_inflation_upload(inflasi_file)
                    info = merge_into_static(parsed_infl, "inflasi_yoy_id")
                    st.success(
                        f"Inflasi berhasil diperbarui\n\n"
                        f"- jumlah baris: {info['rows_uploaded']}\n"
                        f"- rentang: {info['date_min']} s/d {info['date_max']}"
                    )
            except Exception as e:
                st.error(f"Gagal update inflasi: {e}")

    with c3:
        bi_file = st.file_uploader(
            "upload bi rate",
            type=["csv", "xls", "xlsx"],
            key="bi_upload",
        )

        if st.button("Update bi rate", use_container_width=True):
            try:
                if bi_file is None:
                    st.warning("Silahkan upload file bi rate terlebih dahulu")
                else:
                    parsed_bi = parse_bi_rate_upload(bi_file)
                    info = merge_into_static(parsed_bi, "bi_7drr_rate")
                    st.success(
                        f"bi rate berhasil diperbarui\n\n"
                        f"- jumlah baris: {info['rows_uploaded']}\n"
                        f"- rentang: {info['date_min']} s/d {info['date_max']}"
                    )
            except Exception as e:
                st.error(f"Gagal update bi rate: {e}")

# action buttons
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Update data", use_container_width=True):
        try:
            antam_existing = read_table("antam_prices")
            usd_existing = read_table("usd_idr_rates")

            last_antam_date = antam_existing["date"].max() if not antam_existing.empty else None
            last_usd_date = usd_existing["date"].max() if not usd_existing.empty else None

            start_antam, end_antam = get_update_date_range(last_antam_date)
            start_usd, end_usd = get_update_date_range(last_usd_date)

            antam_ok = False
            usd_ok = False

            with st.spinner("Mengambil data terbaru..."):
                try:
                    antam_df = scrape_antam(start_antam, end_antam)
                    if not antam_df.empty:
                        upsert_dataframe(antam_df, "antam_prices")
                    antam_ok = True
                except Exception as e:
                    st.warning(f"Update antam gagal: {e}")

                try:
                    usd_df = fetch_usd_idr(start_usd, end_usd)
                    if not usd_df.empty:
                        upsert_dataframe(usd_df, "usd_idr_rates")
                    usd_ok = True
                except Exception as e:
                    st.warning(f"Update usd/idr gagal: {e}")

            if antam_ok or usd_ok:
                st.success(
                    f"Update data selesai\n\n"
                    f"- antam range: {start_antam} s/d {end_antam}\n"
                    f"- usd/idr range: {start_usd} s/d {end_usd}"
                )
            else:
                st.error("Semua proses update gagal")

        except Exception as e:
            st.error(f"Gagal update data: {e}")

with col2:
    run_btn = st.button("Jalankan Prediksi", use_container_width=True)

with col3:
    if st.button("Reset Prediksi", use_container_width=True):
        clear_prediction_state()
        st.rerun()

# preview data
st.subheader("Ringkasan Data Input")

try:
    antam_preview = read_table("antam_prices")
    usd_preview = read_table("usd_idr_rates")
    static_preview = load_static_data()

    r1, r2 = st.columns(2)

    with r1:
        st.markdown("**Tabel Harga Emas Antam**")
        st.write("Jumlah data:", len(antam_preview))
        if not antam_preview.empty:
            preview_antam = antam_preview[["date", "harga_emas_antam_idr"]].copy()
            preview_antam["date"] = pd.to_datetime(preview_antam["date"], errors="coerce")
            preview_antam = preview_antam.dropna(subset=["date"]).copy()
            preview_antam.columns = ["Tanggal", "Harga Emas Antam (IDR)"]
            preview_antam_min = preview_antam["Tanggal"].min()
            preview_antam_max = preview_antam["Tanggal"].max()
            preview_antam["Tanggal"] = preview_antam["Tanggal"].dt.strftime("%d-%m-%Y")
            st.write(
                "Rentang:",
                preview_antam_min.strftime("%d-%m-%Y"),
                "s/d",
                preview_antam_max.strftime("%d-%m-%Y"),
            )
            st.dataframe(preview_antam.tail(5), use_container_width=True)

    with r2:
        st.markdown("**Tabel Kurs USD/IDR**")
        st.write("Jumlah data:", len(usd_preview))
        if not usd_preview.empty:
            preview_usd = usd_preview[["date", "kurs_usd_idr"]].copy()
            preview_usd["date"] = pd.to_datetime(preview_usd["date"], errors="coerce")
            preview_usd = preview_usd.dropna(subset=["date"]).copy()
            preview_usd.columns = ["Tanggal", "Kurs USD/IDR"]
            preview_usd_min = preview_usd["Tanggal"].min()
            preview_usd_max = preview_usd["Tanggal"].max()
            preview_usd["Tanggal"] = preview_usd["Tanggal"].dt.strftime("%d-%m-%Y")
            st.write(
                "Rentang:",
                preview_usd_min.strftime("%d-%m-%Y"),
                "s/d",
                preview_usd_max.strftime("%d-%m-%Y"),
            )
            st.dataframe(preview_usd.tail(5), use_container_width=True)

    st.markdown("### Data Referensi Model")
    st.caption("Berisi variabel input lain yang digunakan model: XAU/USD, inflasi YoY, dan BI Rate.")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("**XAU/USD**")
        xau_df = static_preview[["date", "xau_usd"]].dropna().copy()
        xau_df["date"] = pd.to_datetime(xau_df["date"], errors="coerce")
        xau_df = xau_df.dropna(subset=["date"]).copy()
        xau_df.columns = ["Tanggal", "XAU/USD"]
        st.write("Jumlah data:", len(xau_df))
        if not xau_df.empty:
            xau_df_min = xau_df["Tanggal"].min()
            xau_df_max = xau_df["Tanggal"].max()
            xau_df["Tanggal"] = xau_df["Tanggal"].dt.strftime("%d-%m-%Y")
            st.write(
                "Rentang:",
                xau_df_min.strftime("%d-%m-%Y"),
                "s/d",
                xau_df_max.strftime("%d-%m-%Y"),
            )
            st.dataframe(xau_df.tail(5), use_container_width=True)

    with c2:
        st.markdown("**Inflasi YoY**")
        infl_df = static_preview[["date", "inflasi_yoy_id"]].dropna().copy()
        infl_df["date"] = pd.to_datetime(infl_df["date"], errors="coerce")
        infl_df = infl_df.dropna(subset=["date"]).copy()
        infl_df.columns = ["Tanggal", "Inflasi YoY (%)"]
        st.write("Jumlah data:", len(infl_df))
        if not infl_df.empty:
            infl_df_min = infl_df["Tanggal"].min()
            infl_df_max = infl_df["Tanggal"].max()
            infl_df["Tanggal"] = infl_df["Tanggal"].dt.strftime("%d-%m-%Y")
            st.write(
                "Rentang:",
                infl_df_min.strftime("%d-%m-%Y"),
                "s/d",
                infl_df_max.strftime("%d-%m-%Y"),
            )
            st.dataframe(infl_df.tail(5), use_container_width=True)

    with c3:
        st.markdown("**BI Rate**")
        bi_df = static_preview[["date", "bi_7drr_rate"]].dropna().copy()
        bi_df["date"] = pd.to_datetime(bi_df["date"], errors="coerce")
        bi_df = bi_df.dropna(subset=["date"]).copy()
        bi_df.columns = ["Tanggal", "BI Rate 7D RR (%)"]
        st.write("Jumlah data:", len(bi_df))
        if not bi_df.empty:
            bi_df_min = bi_df["Tanggal"].min()
            bi_df_max = bi_df["Tanggal"].max()
            bi_df["Tanggal"] = bi_df["Tanggal"].dt.strftime("%d-%m-%Y")
            st.write(
                "Rentang:",
                bi_df_min.strftime("%d-%m-%Y"),
                "s/d",
                bi_df_max.strftime("%d-%m-%Y"),
            )
            st.dataframe(bi_df.tail(5), use_container_width=True)

except Exception as e:
    st.warning(f"Tidak bisa membaca ringkasan data input: {e}")

# run prediction
if run_btn:
    try:
        antam_df = read_table("antam_prices")
        usd_df = read_table("usd_idr_rates")
        static_df = load_static_data()

        if antam_df.empty:
            st.warning("Tabel antam_prices masih kosong. jalankan initialize historical data atau update data")
            st.stop()

        if usd_df.empty:
            st.warning("Tabel usd_idr_rates masih kosong. jalankan initialize historical data atau update data")
            st.stop()

        if static_df.empty:
            st.warning("Data static masih kosong. upload xau/usd, inflasi, dan bi rate terlebih dahulu")
            st.stop()

        with st.spinner("Menjalankan Forecasting..."):
            master_df, pred_df = run_prediction(
                horizon=horizon,
                antam_df=antam_df,
                usd_df=usd_df,
                static_df=static_df,
                base_date=pd.to_datetime(base_date) if base_date else None,
            )

        st.session_state.pred_df = pred_df
        st.session_state.master_df = master_df
        st.session_state.csv_bytes = to_csv_bytes(pred_df)
        st.session_state.excel_bytes = to_excel_bytes(pred_df)

        # Simpan history hanya untuk prediksi masa depan
        if not is_past_prediction:
            save_history(
                st.session_state.user_id,
                horizon,
                str(master_df.index.min().date()),
                str(master_df.index.max().date()),
            )

        st.success("Prediksi Berhasil Dijalankan")

    except Exception as e:
        st.error(f"Prediksi Gagal: {e}")

# output
if st.session_state.pred_df is not None and st.session_state.master_df is not None:
    pred_df = st.session_state.pred_df
    master_df = st.session_state.master_df
    horizon = st.session_state.horizon

    st.subheader("Tabel Nilai Prediksi")
    display_pred_df = pred_df.rename(
        columns={
            "pred_date": "Tanggal Prediksi",
            "SARIMAX": "Prediksi SARIMAX",
            "Hybrid_XGBoost": "Prediksi Hybrid XGBoost",
            "Hybrid_LightGBM": "Prediksi Hybrid LightGBM",
            "Aktual": "Aktual (jika tersedia)",
        }
    )
    if "Tanggal Prediksi" in display_pred_df.columns:
        display_pred_df["Tanggal Prediksi"] = pd.to_datetime(display_pred_df["Tanggal Prediksi"]).dt.strftime("%d-%m-%Y")
    st.dataframe(display_pred_df, use_container_width=True)

    # Tampilkan informasi mode prediksi
    if is_past_prediction:
        st.info(f"Mode: Prediksi Masa Lalu | Base Date: {base_date} | Horizon: H+{horizon}")
    else:
        st.info(f"Mode: Prediksi Masa Depan | Horizon: H+{horizon}")

    st.subheader("Grafik Perbandingan Aktual vs Prediksi")
    
    filtered_master = master_df.copy()
    filtered_master["harga_emas_antam_idr"] = pd.to_numeric(
        filtered_master["harga_emas_antam_idr"], errors="coerce"
    )

    pred_df = pred_df.copy()
    pred_df["pred_date"] = pd.to_datetime(pred_df["pred_date"])
    pred_df["SARIMAX"] = pd.to_numeric(pred_df["SARIMAX"], errors="coerce")
    pred_df["Hybrid_XGBoost"] = pd.to_numeric(pred_df["Hybrid_XGBoost"], errors="coerce")
    pred_df["Hybrid_LightGBM"] = pd.to_numeric(pred_df["Hybrid_LightGBM"], errors="coerce")
    pred_df["Aktual"] = pd.to_numeric(pred_df["Aktual"], errors="coerce")
    
    if is_past_prediction and base_date:
        # Untuk prediksi historis: tampilkan data historis sebelum base_date, dan prediksi + aktual setelah base_date
        base_date_dt = pd.to_datetime(base_date)
        
        # Data historis sebelum base_date
        historical_before = filtered_master[filtered_master.index < base_date_dt]
        
        fig = go.Figure()
        
        # Tambahkan data historis sebelum base_date
        if not historical_before.empty:
            fig.add_trace(go.Scatter(
                x=historical_before.index, 
                y=historical_before["harga_emas_antam_idr"], 
                mode="lines", 
                name="Data Historis",
                line=dict(color="gray", width=2)
            ))
        
        # Tambahkan prediksi
        fig.add_trace(go.Scatter(
            x=pred_df["pred_date"], 
            y=pred_df["SARIMAX"], 
            mode="lines+markers", 
            name="Prediksi SARIMAX", 
            line=dict(dash="dash", color="orange")
        ))
        fig.add_trace(go.Scatter(
            x=pred_df["pred_date"], 
            y=pred_df["Hybrid_XGBoost"], 
            mode="lines+markers", 
            name="Prediksi Hybrid XGBoost", 
            line=dict(dash="dash", color="green")
        ))
        fig.add_trace(go.Scatter(
            x=pred_df["pred_date"], 
            y=pred_df["Hybrid_LightGBM"], 
            mode="lines+markers", 
            name="Prediksi Hybrid LightGBM", 
            line=dict(dash="dash", color="red")
        ))
        
        # Tambahkan data aktual (target) jika tersedia
        actual_mask = pred_df["Aktual"].notna()
        if actual_mask.any():
            actual_dates = pd.to_datetime(pred_df.loc[actual_mask, "pred_date"])
            actual_values = pd.to_numeric(pred_df.loc[actual_mask, "Aktual"], errors="coerce")
            fig.add_trace(go.Scatter(
                x=actual_dates, 
                y=actual_values, 
                mode="lines+markers", 
                name="Aktual (Target)", 
                line=dict(color="blue", width=3)
            ))
        
        # Tambahkan vertical line untuk base_date
        fig.add_vline(
            x=base_date_dt.timestamp() * 1000, 
            line_dash="dash", 
            line_color="black",
            annotation_text=f"Base Date: {base_date}",
            annotation_position="top right"
        )
        
        title = f"Prediksi Historis: Base Date {base_date}, Horizon H+{horizon}"
        fig.update_layout(
            title=title, 
            xaxis_title="Tanggal", 
            yaxis_title="Harga (IDR)",
            hovermode="x unified",
            height=600
        )
        st.plotly_chart(fig, use_container_width=True)

        # Chart tambahan khusus rentang prediksi (Zoom-in)
        st.subheader("Detail Prediksi vs Aktual")
        fig_zoom = go.Figure()
        
        # Tambahkan prediksi
        fig_zoom.add_trace(go.Scatter(
            x=pred_df["pred_date"], 
            y=pred_df["SARIMAX"], 
            mode="lines+markers", 
            name="Prediksi SARIMAX", 
            line=dict(dash="dash", color="orange")
        ))
        fig_zoom.add_trace(go.Scatter(
            x=pred_df["pred_date"], 
            y=pred_df["Hybrid_XGBoost"], 
            mode="lines+markers", 
            name="Prediksi Hybrid XGBoost", 
            line=dict(dash="dash", color="green")
        ))
        fig_zoom.add_trace(go.Scatter(
            x=pred_df["pred_date"], 
            y=pred_df["Hybrid_LightGBM"], 
            mode="lines+markers", 
            name="Prediksi Hybrid LightGBM", 
            line=dict(dash="dash", color="red")
        ))
        
        # Tambahkan data aktual (target) jika tersedia
        if actual_mask.any():
            fig_zoom.add_trace(go.Scatter(
                x=actual_dates, 
                y=actual_values, 
                mode="lines+markers", 
                name="Aktual (Target)", 
                line=dict(color="blue", width=3)
            ))
        
        fig_zoom.update_layout(
            title=f"Fokus Prediksi: Base Date {base_date}, Horizon H+{horizon}", 
            xaxis_title="Tanggal", 
            yaxis_title="Harga (IDR)",
            hovermode="x unified",
            height=500
        )
        st.plotly_chart(fig_zoom, use_container_width=True)
    else:
        # Untuk prediksi masa depan: tampilkan semua data historis + prediksi
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=filtered_master.index, 
            y=filtered_master["harga_emas_antam_idr"], 
            mode="lines", 
            name="Aktual (Historis)",
            line=dict(color="blue", width=2)
        ))
        fig.add_trace(go.Scatter(
            x=pred_df["pred_date"], 
            y=pred_df["SARIMAX"], 
            mode="lines+markers", 
            name="Prediksi SARIMAX", 
            line=dict(dash="dash", color="orange")
        ))
        fig.add_trace(go.Scatter(
            x=pred_df["pred_date"], 
            y=pred_df["Hybrid_XGBoost"], 
            mode="lines+markers", 
            name="Prediksi Hybrid XGBoost", 
            line=dict(dash="dash", color="green")
        ))
        fig.add_trace(go.Scatter(
            x=pred_df["pred_date"], 
            y=pred_df["Hybrid_LightGBM"], 
            mode="lines+markers", 
            name="Prediksi Hybrid LightGBM", 
            line=dict(dash="dash", color="red")
        ))
        
        title = f"Prediksi Masa Depan: Horizon H+{horizon}"
        fig.update_layout(
            title=title, 
            xaxis_title="Tanggal", 
            yaxis_title="Harga (IDR)",
            hovermode="x unified",
            height=600
        )
        st.plotly_chart(fig, use_container_width=True)

    # Tabel evaluasi untuk prediksi masa lalu
    if is_past_prediction and pred_df["Aktual"].notna().any():
        st.subheader("Evaluasi Prediksi Masa Lalu")
        eval_data = []
        for _, row in pred_df.iterrows():
            if pd.notna(row["Aktual"]):
                actual = row["Aktual"]
                sarimax_pred = row["SARIMAX"]
                xgb_pred = row["Hybrid_XGBoost"]
                lgb_pred = row["Hybrid_LightGBM"]

                eval_data.append({
                    "Tanggal": row["pred_date"].date(),
                    "Aktual": actual,
                    "Pred SARIMAX": sarimax_pred,
                    "Error SARIMAX": actual - sarimax_pred,
                    "Error % SARIMAX": ((actual - sarimax_pred) / actual) * 100 if actual != 0 else 0,
                    "Pred XGBoost": xgb_pred,
                    "Error XGBoost": actual - xgb_pred,
                    "Error % XGBoost": ((actual - xgb_pred) / actual) * 100 if actual != 0 else 0,
                    "Pred LightGBM": lgb_pred,
                    "Error LightGBM": actual - lgb_pred,
                    "Error % LightGBM": ((actual - lgb_pred) / actual) * 100 if actual != 0 else 0,
                })

        if eval_data:
            eval_df = pd.DataFrame(eval_data)
            st.dataframe(eval_df, use_container_width=True)

            # Hitung metrik keseluruhan
            st.subheader("Metrik Evaluasi Keseluruhan")
            metrics = []
            for model in ["SARIMAX", "XGBoost", "LightGBM"]:
                errors = eval_df[f"Error {model}"]
                mae = errors.abs().mean()
                rmse = (errors**2).mean()**0.5
                mape = (errors.abs() / eval_df["Aktual"]).mean() * 100

                metrics.append({
                    "Model": model,
                    "MAE": mae,
                    "RMSE": rmse,
                    "MAPE (%)": mape
                })

            metrics_df = pd.DataFrame(metrics)
            st.dataframe(metrics_df, use_container_width=True)

    st.subheader("Tabel Metrik Evaluasi Model")
    try:
        metrics_df = pd.read_csv("models/metrics_all_horizons.csv")
        metrics_filtered = metrics_df[metrics_df["horizon"] == f"H+{horizon}"].copy()
        st.dataframe(metrics_filtered, use_container_width=True)

        if not metrics_filtered.empty:
            best_row = metrics_filtered.sort_values("RMSE", ascending=True).iloc[0]
            st.info(
                f"Model terbaik untuk H+{horizon}: **{best_row['model']}** "
                f"(RMSE = {best_row['RMSE']:.2f}, MAE = {best_row['MAE']:.2f}, R² = {best_row['R2']:.4f})"
            )
    except FileNotFoundError:
        st.warning("file metrics_all_horizons.csv belum tersedia di folder models")

    # simpan metadata prediksi seperti sebelumnya
    rows = []
    for _, r in pred_df.iterrows():
        rows.extend(
            [
                {
                    "horizon": horizon,
                    "model_name": "SARIMAX",
                    "pred_date": str(pd.to_datetime(r["pred_date"]).date()),
                    "predicted_value": float(r["SARIMAX"]),
                },
                {
                    "horizon": horizon,
                    "model_name": "Hybrid_XGBoost",
                    "pred_date": str(pd.to_datetime(r["pred_date"]).date()),
                    "predicted_value": float(r["Hybrid_XGBoost"]),
                },
                {
                    "horizon": horizon,
                    "model_name": "Hybrid_LightGBM",
                    "pred_date": str(pd.to_datetime(r["pred_date"]).date()),
                    "predicted_value": float(r["Hybrid_LightGBM"]),
                },
            ]
        )
    save_predictions(pd.DataFrame(rows))

    st.subheader("Feature Importance")

    xgb_plot_bytes = None
    lgb_plot_bytes = None

    try:
        with open("models/config.json", "r") as f:
            config = json.load(f)

        feature_cols = config["feature_cols"]

        with open(f"models/xgb_h{horizon}.pkl", "rb") as f:
            xgb_model = pickle.load(f)

        lgb_model = lgb.Booster(model_file=f"models/lgb_h{horizon}.txt")

        xgb_imp = pd.DataFrame(
            {
                "feature": feature_cols,
                "importance": xgb_model.feature_importances_,
            }
        ).sort_values("importance", ascending=False)

        lgb_imp = pd.DataFrame(
            {
                "feature": feature_cols,
                "importance": lgb_model.feature_importance(),
            }
        ).sort_values("importance", ascending=False)

        c1, c2 = st.columns(2)

        with c1:
            st.markdown("**XGBoost Feature Importance**")
            top_xgb = xgb_imp.head(15).sort_values("importance", ascending=True)
            fig3 = px.bar(
                top_xgb,
                x="importance",
                y="feature",
                orientation="h",
                title=f"Top 15 XGBoost Importance (H+{horizon})",
            )
            st.plotly_chart(fig3, use_container_width=True)
            xgb_plot_bytes = fig_to_png_bytes(fig3)

        with c2:
            st.markdown("**LightGBM Feature Importance**")
            top_lgb = lgb_imp.head(15).sort_values("importance", ascending=True)
            fig4 = px.bar(
                top_lgb,
                x="importance",
                y="feature",
                orientation="h",
                title=f"Top 15 LightGBM Importance (H+{horizon})",
            )
            st.plotly_chart(fig4, use_container_width=True)
            lgb_plot_bytes = fig_to_png_bytes(fig4)

    except Exception as e:
        st.warning(f"Feature importance belum dapat ditampilkan: {e}")
        xgb_plot_bytes = None
        lgb_plot_bytes = None

    # build zip sekali dan simpan di session state
    if not st.session_state.zip_bytes:
        try:
            actual_plot_bytes = fig_to_png_bytes(fig)
            forecast_plot_bytes = fig_to_png_bytes(fig)

            if xgb_plot_bytes is None:
                empty_fig = go.Figure()
                empty_fig.update_layout(title="xgboost feature importance not available")
                xgb_plot_bytes = fig_to_png_bytes(empty_fig)

            if lgb_plot_bytes is None:
                empty_fig = go.Figure()
                empty_fig.update_layout(title="lightgbm feature importance not available")
                lgb_plot_bytes = fig_to_png_bytes(empty_fig)

            zip_result = build_prediction_zip(
                pred_df=pred_df,
                actual_plot_bytes=actual_plot_bytes,
                forecast_plot_bytes=forecast_plot_bytes,
                xgb_plot_bytes=xgb_plot_bytes,
                lgb_plot_bytes=lgb_plot_bytes,
            )
            if zip_result and isinstance(zip_result, bytes) and len(zip_result) > 0:
                st.session_state.zip_bytes = zip_result
        except Exception as e:
            st.warning(f"zip belum bisa dibuat: {e}")

    st.subheader("Simpan Hasil Prediksi")
    exp1, exp2, exp3 = st.columns(3)

    with exp1:
        if st.session_state.csv_bytes and isinstance(st.session_state.csv_bytes, bytes) and len(st.session_state.csv_bytes) > 0:
            st.download_button(
                label="download csv",
                data=st.session_state.csv_bytes,
                file_name=f"prediction_h{horizon}.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"csv_{horizon}",
            )
        else:
            st.info("CSV belum tersedia")

    with exp2:
        if st.session_state.excel_bytes and isinstance(st.session_state.excel_bytes, bytes) and len(st.session_state.excel_bytes) > 0:
            st.download_button(
                label="download excel",
                data=st.session_state.excel_bytes,
                file_name=f"prediction_h{horizon}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key=f"excel_{horizon}",
            )
        else:
            st.info("Excel belum tersedia")

    with exp3:
        if st.session_state.zip_bytes and isinstance(st.session_state.zip_bytes, bytes) and len(st.session_state.zip_bytes) > 0:
            st.download_button(
                label="download zip",
                data=st.session_state.zip_bytes,
                file_name=f"prediction_bundle_h{horizon}.zip",
                mime="application/zip",
                use_container_width=True,
                key=f"zip_{horizon}",
            )
        else:
            st.info("zip belum tersedia")

# history user
st.subheader("Riwayat Prediksi Saya")

try:
    history = get_user_history(st.session_state.user_id)

    if history:
        df_hist = pd.DataFrame(
            history,
            columns=["Tanggal Run", "Horizon", "Start data", "End data"],
        )
        st.dataframe(df_hist, use_container_width=True)
    else:
        st.info("Belum ada riwayat prediksi")
except Exception as e:
    st.warning(f"Gagal memuat riwayat: {e}")
