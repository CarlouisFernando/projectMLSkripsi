# import library
import json
import pickle

import lightgbm as lgb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

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
    st.session_state.pred_df = None
    st.session_state.master_df = None
    st.session_state.horizon = 1
    st.session_state.csv_bytes = None
    st.session_state.excel_bytes = None
    st.session_state.zip_bytes = None

# auth check
if "user_id" not in st.session_state:
    st.warning("silakan login terlebih dahulu")
    st.stop()

st.title("Prediction")
st.caption("update data terbaru, jalankan forecasting, dan simpan hasil prediksi")

init_db()

# Load data for validation
try:
    antam_df = read_table("antam_prices")
    if not antam_df.empty:
        antam_df['date'] = pd.to_datetime(antam_df['date'])
except:
    antam_df = pd.DataFrame()

# session state
if "pred_df" not in st.session_state:
    st.session_state.pred_df = None
if "master_df" not in st.session_state:
    st.session_state.master_df = None
if "horizon" not in st.session_state:
    st.session_state.horizon = 1
if "csv_bytes" not in st.session_state:
    st.session_state.csv_bytes = None
if "excel_bytes" not in st.session_state:
    st.session_state.excel_bytes = None
if "zip_bytes" not in st.session_state:
    st.session_state.zip_bytes = None

# header actions
top1, top2 = st.columns([1, 5])
with top1:
    if st.button("logout", use_container_width=True):
        st.session_state.clear()
        st.switch_page("pages/0_Login.py")

# horizon
horizon = st.selectbox(
    "pilih horizon prediksi",
    [1, 2, 3, 4, 5, 6, 7],
    index=[1, 2, 3, 4, 5, 6, 7].index(st.session_state.horizon)
    if st.session_state.horizon in [1, 2, 3, 4, 5, 6, 7]
    else 0,
    format_func=lambda x: f"H+{x}",
)

# mode prediksi
is_past_prediction = st.checkbox("Prediksi Masa Lalu (untuk evaluasi model)")
base_date = None
if is_past_prediction:
    base_date = st.date_input(
        "Pilih tanggal base untuk prediksi masa lalu",
        value=pd.Timestamp.today() - pd.DateOffset(days=30),
        max_value=pd.Timestamp.today().date()
    )
    # Validasi tanggal base
    if base_date and not antam_df.empty:
        min_date = pd.to_datetime(antam_df['date'].min())
        max_date = pd.to_datetime(antam_df['date'].max())
        
        if pd.to_datetime(base_date) < min_date:
            st.warning(f"Tanggal base minimal adalah {min_date.date()}. Data historis tidak mencakup tanggal tersebut.")
        elif pd.to_datetime(base_date) > max_date:
            st.warning(f"Tanggal base maksimal adalah {max_date.date()}. Tidak bisa memprediksi masa depan.")
        else:
            # Check if there's enough historical data before base_date (at least 30 days)
            data_before_base = antam_df[antam_df['date'] < pd.to_datetime(base_date)]
            if len(data_before_base) < 30:
                st.warning(f"Data historis sebelum tanggal base terlalu sedikit ({len(data_before_base)} hari). Minimal 30 hari diperlukan untuk akurasi model.")

# setup data historis
with st.expander("setup data historis", expanded=False):
    st.write(
        "gunakan ini pertama kali untuk mengisi data historis harga emas antam "
        "dan kurs usd/idr sebelum menjalankan prediksi"
    )

    hist_start = st.date_input("start date historis", value=pd.to_datetime("2019-01-01"))
    hist_end = st.date_input("end date historis", value=pd.Timestamp.today().date())

    if st.button("initialize historical data", use_container_width=True):
        try:
            start_str = pd.to_datetime(hist_start).strftime("%Y-%m-%d")
            end_str = pd.to_datetime(hist_end).strftime("%Y-%m-%d")

            with st.spinner("mengambil data historis penuh..."):
                antam_df = scrape_antam(start_str, end_str)
                usd_df = fetch_usd_idr(start_str, end_str)

            upsert_dataframe(antam_df, "antam_prices")
            upsert_dataframe(usd_df, "usd_idr_rates")

            st.success(
                f"data historis berhasil disimpan\n\n"
                f"- antam: {len(antam_df)} baris ({antam_df['date'].min()} s/d {antam_df['date'].max()})\n"
                f"- usd/idr: {len(usd_df)} baris ({usd_df['date'].min()} s/d {usd_df['date'].max()})"
            )

        except Exception as e:
            st.error(f"gagal inisialisasi data historis: {e}")

# update static manual
with st.expander("update data static manual per variabel", expanded=False):
    st.write(
        "upload data xau/usd, inflasi, dan bi rate secara terpisah. "
        "sistem akan parsing otomatis dari format mentah sumber data"
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        xau_file = st.file_uploader(
            "upload xau/usd",
            type=["csv", "xls", "xlsx"],
            key="xau_upload",
        )

        if st.button("update xau/usd", use_container_width=True):
            try:
                if xau_file is None:
                    st.warning("silakan upload file xau/usd terlebih dahulu")
                else:
                    parsed_xau = parse_xau_upload(xau_file)
                    info = merge_into_static(parsed_xau, "xau_usd")
                    st.success(
                        f"xau/usd berhasil diperbarui\n\n"
                        f"- jumlah baris: {info['rows_uploaded']}\n"
                        f"- rentang: {info['date_min']} s/d {info['date_max']}"
                    )
            except Exception as e:
                st.error(f"gagal update xau/usd: {e}")

    with c2:
        inflasi_file = st.file_uploader(
            "upload inflasi",
            type=["csv", "xls", "xlsx"],
            key="inflasi_upload",
        )

        if st.button("update inflasi", use_container_width=True):
            try:
                if inflasi_file is None:
                    st.warning("silakan upload file inflasi terlebih dahulu")
                else:
                    parsed_infl = parse_inflation_upload(inflasi_file)
                    info = merge_into_static(parsed_infl, "inflasi_yoy_id")
                    st.success(
                        f"inflasi berhasil diperbarui\n\n"
                        f"- jumlah baris: {info['rows_uploaded']}\n"
                        f"- rentang: {info['date_min']} s/d {info['date_max']}"
                    )
            except Exception as e:
                st.error(f"gagal update inflasi: {e}")

    with c3:
        bi_file = st.file_uploader(
            "upload bi rate",
            type=["csv", "xls", "xlsx"],
            key="bi_upload",
        )

        if st.button("update bi rate", use_container_width=True):
            try:
                if bi_file is None:
                    st.warning("silakan upload file bi rate terlebih dahulu")
                else:
                    parsed_bi = parse_bi_rate_upload(bi_file)
                    info = merge_into_static(parsed_bi, "bi_7drr_rate")
                    st.success(
                        f"bi rate berhasil diperbarui\n\n"
                        f"- jumlah baris: {info['rows_uploaded']}\n"
                        f"- rentang: {info['date_min']} s/d {info['date_max']}"
                    )
            except Exception as e:
                st.error(f"gagal update bi rate: {e}")

# action buttons
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("update data", use_container_width=True):
        try:
            antam_existing = read_table("antam_prices")
            usd_existing = read_table("usd_idr_rates")

            last_antam_date = antam_existing["date"].max() if not antam_existing.empty else None
            last_usd_date = usd_existing["date"].max() if not usd_existing.empty else None

            start_antam, end_antam = get_update_date_range(last_antam_date)
            start_usd, end_usd = get_update_date_range(last_usd_date)

            antam_ok = False
            usd_ok = False

            with st.spinner("mengambil data terbaru..."):
                try:
                    antam_df = scrape_antam(start_antam, end_antam)
                    if not antam_df.empty:
                        upsert_dataframe(antam_df, "antam_prices")
                    antam_ok = True
                except Exception as e:
                    st.warning(f"update antam gagal: {e}")

                try:
                    usd_df = fetch_usd_idr(start_usd, end_usd)
                    if not usd_df.empty:
                        upsert_dataframe(usd_df, "usd_idr_rates")
                    usd_ok = True
                except Exception as e:
                    st.warning(f"update usd/idr gagal: {e}")

            if antam_ok or usd_ok:
                st.success(
                    f"update data selesai\n\n"
                    f"- antam range: {start_antam} s/d {end_antam}\n"
                    f"- usd/idr range: {start_usd} s/d {end_usd}"
                )
            else:
                st.error("semua proses update gagal")

        except Exception as e:
            st.error(f"gagal update data: {e}")

with col2:
    run_btn = st.button("run prediction", use_container_width=True)

with col3:
    if st.button("reset", use_container_width=True):
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
        st.markdown("**tabel antam_prices**")
        st.write("jumlah data:", len(antam_preview))
        if not antam_preview.empty:
            st.write("rentang:", antam_preview["date"].min(), "s/d", antam_preview["date"].max())
            st.dataframe(antam_preview.tail(5), use_container_width=True)

    with r2:
        st.markdown("**tabel usd_idr_rates**")
        st.write("jumlah data:", len(usd_preview))
        if not usd_preview.empty:
            st.write("rentang:", usd_preview["date"].min(), "s/d", usd_preview["date"].max())
            st.dataframe(usd_preview.tail(5), use_container_width=True)

    st.markdown("### Data Referensi Model")
    st.caption("berisi variabel input lain yang digunakan model: xau/usd, inflasi yoy, dan bi rate")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("**xau/usd**")
        xau_df = static_preview[["date", "xau_usd"]].dropna().copy()
        st.write("jumlah data:", len(xau_df))
        if not xau_df.empty:
            st.write("rentang:", xau_df["date"].min().date(), "s/d", xau_df["date"].max().date())
            st.dataframe(xau_df.tail(5), use_container_width=True)

    with c2:
        st.markdown("**inflasi yoy**")
        infl_df = static_preview[["date", "inflasi_yoy_id"]].dropna().copy()
        st.write("jumlah data:", len(infl_df))
        if not infl_df.empty:
            st.write("rentang:", infl_df["date"].min().date(), "s/d", infl_df["date"].max().date())
            st.dataframe(infl_df.tail(5), use_container_width=True)

    with c3:
        st.markdown("**bi rate**")
        bi_df = static_preview[["date", "bi_7drr_rate"]].dropna().copy()
        st.write("jumlah data:", len(bi_df))
        if not bi_df.empty:
            st.write("rentang:", bi_df["date"].min().date(), "s/d", bi_df["date"].max().date())
            st.dataframe(bi_df.tail(5), use_container_width=True)

except Exception as e:
    st.warning(f"tidak bisa membaca ringkasan data input: {e}")

# run prediction
if run_btn:
    try:
        antam_df = read_table("antam_prices")
        usd_df = read_table("usd_idr_rates")
        static_df = load_static_data()

        if antam_df.empty:
            st.warning("tabel antam_prices masih kosong. jalankan initialize historical data atau update data")
            st.stop()

        if usd_df.empty:
            st.warning("tabel usd_idr_rates masih kosong. jalankan initialize historical data atau update data")
            st.stop()

        if static_df.empty:
            st.warning("data static masih kosong. upload xau/usd, inflasi, dan bi rate terlebih dahulu")
            st.stop()

        with st.spinner("menjalankan forecasting..."):
            master_df, pred_df = run_prediction(
                horizon=horizon,
                antam_df=antam_df,
                usd_df=usd_df,
                static_df=static_df,
                base_date=pd.to_datetime(base_date) if base_date else None,
            )

        st.session_state.pred_df = pred_df
        st.session_state.master_df = master_df
        st.session_state.horizon = horizon
        st.session_state.csv_bytes = to_csv_bytes(pred_df)
        st.session_state.excel_bytes = to_excel_bytes(pred_df)
        st.session_state.zip_bytes = None

        # Simpan history hanya untuk prediksi masa depan
        if not is_past_prediction:
            save_history(
                st.session_state.user_id,
                horizon,
                str(master_df.index.min().date()),
                str(master_df.index.max().date()),
            )

        st.success("prediction berhasil dijalankan")

    except Exception as e:
        st.error(f"prediction gagal: {e}")

# output
if st.session_state.pred_df is not None and st.session_state.master_df is not None:
    pred_df = st.session_state.pred_df
    master_df = st.session_state.master_df
    horizon = st.session_state.horizon

    st.subheader("Tabel Nilai Prediksi")
    st.dataframe(pred_df, use_container_width=True)

    # Tampilkan informasi mode prediksi
    if is_past_prediction:
        st.info(f"Mode: Prediksi Masa Lalu | Base Date: {base_date} | Horizon: H+{horizon}")
    else:
        st.info(f"Mode: Prediksi Masa Depan | Horizon: H+{horizon}")

    st.subheader("Grafik Perbandingan Aktual vs Prediksi")
    filtered_master = master_df  # Show all available historical data

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=filtered_master.index, y=filtered_master["harga_emas_antam_idr"], mode="lines", name="Aktual (Historis)"))
    fig.add_trace(go.Scatter(x=pred_df["pred_date"], y=pred_df["SARIMAX"], mode="lines+markers", name="Prediksi SARIMAX", line=dict(dash="dash")))
    fig.add_trace(go.Scatter(x=pred_df["pred_date"], y=pred_df["Hybrid_XGBoost"], mode="lines+markers", name="Prediksi Hybrid XGBoost", line=dict(dash="dash")))
    fig.add_trace(go.Scatter(x=pred_df["pred_date"], y=pred_df["Hybrid_LightGBM"], mode="lines+markers", name="Prediksi Hybrid LightGBM", line=dict(dash="dash")))

    # Tambahkan trace aktual untuk prediksi masa lalu jika tersedia
    if is_past_prediction and pred_df["Aktual"].notna().any():
        actual_dates = pred_df[pred_df["Aktual"].notna()]["pred_date"]
        actual_values = pred_df[pred_df["Aktual"].notna()]["Aktual"]
        fig.add_trace(go.Scatter(x=actual_dates, y=actual_values, mode="lines", name="Aktual (Target)", line=dict(color="blue", width=2, dash="solid")))

    title = f"Perbandingan Harga Emas Antam: Aktual vs Prediksi"
    if is_past_prediction:
        title += f" (Base: {base_date}, Horizon: H+{horizon})"

    fig.update_layout(title=title, xaxis_title="Tanggal", yaxis_title="Harga (IDR)")
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
                f"model terbaik untuk H+{horizon}: **{best_row['model']}** "
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
            st.markdown("**xgboost feature importance**")
            top_xgb = xgb_imp.head(15).sort_values("importance", ascending=True)
            fig3 = px.bar(
                top_xgb,
                x="importance",
                y="feature",
                orientation="h",
                title=f"top 15 xgboost importance (H+{horizon})",
            )
            st.plotly_chart(fig3, use_container_width=True)
            xgb_plot_bytes = fig_to_png_bytes(fig3)

        with c2:
            st.markdown("**lightgbm feature importance**")
            top_lgb = lgb_imp.head(15).sort_values("importance", ascending=True)
            fig4 = px.bar(
                top_lgb,
                x="importance",
                y="feature",
                orientation="h",
                title=f"top 15 lightgbm importance (H+{horizon})",
            )
            st.plotly_chart(fig4, use_container_width=True)
            lgb_plot_bytes = fig_to_png_bytes(fig4)

    except Exception as e:
        st.warning(f"feature importance belum dapat ditampilkan: {e}")

    # build zip sekali dan simpan di session state
    if st.session_state.zip_bytes is None:
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

            st.session_state.zip_bytes = build_prediction_zip(
                pred_df=pred_df,
                actual_plot_bytes=actual_plot_bytes,
                forecast_plot_bytes=forecast_plot_bytes,
                xgb_plot_bytes=xgb_plot_bytes,
                lgb_plot_bytes=lgb_plot_bytes,
            )
        except Exception as e:
            st.warning(f"zip belum bisa dibuat: {e}")

    st.subheader("Save Prediction")
    exp1, exp2, exp3 = st.columns(3)

    with exp1:
        st.download_button(
            label="download csv",
            data=st.session_state.csv_bytes,
            file_name=f"prediction_h{horizon}.csv",
            mime="text/csv",
            use_container_width=True,
            key=f"csv_{horizon}",
        )

    with exp2:
        st.download_button(
            label="download excel",
            data=st.session_state.excel_bytes,
            file_name=f"prediction_h{horizon}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"excel_{horizon}",
        )

    with exp3:
        if st.session_state.zip_bytes is not None:
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
            columns=["tanggal run", "horizon", "start data", "end data"],
        )
        st.dataframe(df_hist, use_container_width=True)
    else:
        st.info("belum ada riwayat prediksi")
except Exception as e:
    st.warning(f"gagal memuat riwayat: {e}")