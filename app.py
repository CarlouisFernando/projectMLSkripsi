import streamlit as st
import pandas as pd
import plotly.express as px

# Custom CSS
st.markdown("""
<style>
    .main {
        background-color: #f5f5f5;
    }
    .stTitle {
        color: #2E8B57;
        font-family: 'Arial', sans-serif;
    }
    .stCaption {
        color: #696969;
        font-size: 16px;
    }
    .stInfo {
        background-color: #e8f4fd;
        border-left: 5px solid #1e90ff;
        padding: 10px;
        border-radius: 5px;
    }
    .css-1d391kg {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    .stButton>button {
        background-color: #2E8B57;
        color: white;
        border-radius: 5px;
        border: none;
        padding: 10px 20px;
        font-size: 16px;
    }
    .stButton>button:hover {
        background-color: #228B22;
    }
</style>
""", unsafe_allow_html=True)

st.title("Home")
st.subheader("sistem Forecasting Harga Emas Antam")

st.write("""
aplikasi ini menggunakan tiga model:
1. SARIMAX
2. Hybrid SARIMAX-XGBoost
3. Hybrid SARIMAX-LightGBM
""")

st.markdown("**variabel eksogen yang digunakan:** XAU/USD, Kurs USD/IDR, Inflasi YoY, BI-7DRR Rate")

metrics_path = "models/metrics_all_horizons.csv"
best_path = "models/best_model_per_horizon.csv"

try:
    metrics_df = pd.read_csv(metrics_path)
    best_df = pd.read_csv(best_path)

    st.subheader("Highlight Model Terbaik")
    st.dataframe(best_df, use_container_width=True)

    st.subheader("Ringkasan Performa Model")
    st.dataframe(metrics_df, use_container_width=True)

    st.subheader("Visualisasi RMSE per Horizon")
    fig = px.bar(metrics_df, x="horizon", y="RMSE", color="model", barmode="group", title="RMSE untuk Setiap Model per Horizon")
    st.plotly_chart(fig, use_container_width=True)

except FileNotFoundError:
    st.warning("file metrik model belum tersedia di folder models")