import pandas as pd
import numpy as np

def build_master_dataframe(antam_df, usd_df, static_df):
    antam_df = antam_df.copy()
    usd_df = usd_df.copy()
    static_df = static_df.copy()

    antam_df["date"] = pd.to_datetime(antam_df["date"])
    usd_df["date"] = pd.to_datetime(usd_df["date"])
    static_df["date"] = pd.to_datetime(static_df["date"])

    antam_df = antam_df[["date", "harga_emas_antam_idr"]]
    usd_df = usd_df[["date", "kurs_usd_idr"]]

    df = static_df.merge(antam_df, on="date", how="left")
    df = df.merge(usd_df, on="date", how="left")

    if df.empty:
        raise ValueError("Merge menghasilkan dataframe kosong.")

    df = df.sort_values("date").set_index("date")
    df = df.asfreq("D")
    df = df.ffill().bfill()

    required_cols = [
        "harga_emas_antam_idr",
        "kurs_usd_idr",
        "xau_usd",
        "inflasi_yoy_id",
        "bi_7drr_rate"
    ]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Kolom wajib tidak ditemukan: {missing_cols}")

    for c in required_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["log_harga"] = np.log(df["harga_emas_antam_idr"])
    df["log_kurs"] = np.log(df["kurs_usd_idr"])
    df["log_xau"] = np.log(df["xau_usd"])
    df["log_return"] = df["log_harga"].diff()

    for lag in [1, 2, 3, 5, 7]:
        df[f"lag_{lag}"] = df["log_harga"].shift(lag)

    df["rolling_mean_7"] = df["log_harga"].shift(1).rolling(7).mean()
    df["rolling_std_7"] = df["log_harga"].shift(1).rolling(7).std()
    df["rolling_mean_14"] = df["log_harga"].shift(1).rolling(14).mean()
    df["rolling_std_14"] = df["log_harga"].shift(1).rolling(14).std()

    df["day_of_week"] = df.index.dayofweek
    df["month"] = df.index.month
    df["quarter"] = df.index.quarter
    df["spread_macro"] = df["bi_7drr_rate"] - df["inflasi_yoy_id"]
    df["log_xau_lag1"] = df["log_xau"].shift(1)
    df["log_kurs_lag1"] = df["log_kurs"].shift(1)

    df = df.dropna().copy()

    if df.empty:
        raise ValueError(
            "Data kosong setelah feature engineering"
            "Kemungkinan data historis antam/usd_idr belum cukup panjang"
        )

    return df