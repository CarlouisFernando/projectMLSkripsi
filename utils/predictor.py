import pandas as pd
import numpy as np
from utils.model_loader import load_config, load_sarimax, load_boosting_models
from utils.preprocessing import build_master_dataframe

def run_prediction(horizon: int, antam_df, usd_df, static_df, base_date=None):
    # Ensure antam_df dates are datetime
    antam_df = antam_df.copy()
    antam_df['date'] = pd.to_datetime(antam_df['date'])
    
    config = load_config()
    sarimax = load_sarimax()
    xgb_models, lgb_models = load_boosting_models(config["max_horizon"])

    df = build_master_dataframe(antam_df, usd_df, static_df)

    if df.empty:
        raise ValueError(
            "Data hasil preprocessing kosong"
            "Cek kecocokan kolom master_static.csv, data antam_prices, usd_idr_rates,"
            "dan pastikan jumlah baris cukup setelah feature engineering"
        )

    feature_cols = config["feature_cols"]
    exog_cols = config["exog_sarimax"]

    missing_feature_cols = [c for c in feature_cols if c not in df.columns]
    missing_exog_cols = [c for c in exog_cols if c not in df.columns]

    if missing_feature_cols:
        raise ValueError(f"Kolom feature tidak ditemukan: {missing_feature_cols}")

    if missing_exog_cols:
        raise ValueError(f"Kolom exogenous tidak ditemukan: {missing_exog_cols}")

    df_feat = df.dropna(subset=feature_cols + exog_cols).copy()

    if df_feat.empty:
        raise ValueError(
            "Data kosong setelah dropna pada feature/exogenous"
            "Kemungkinan data historis belum cukup atau ada kolom yang seluruhnya NaN"
        )

    # Jika base_date diberikan, filter data hingga base_date
    if base_date is not None:
        df_feat = df_feat[df_feat.index <= base_date].copy()
        if df_feat.empty:
            raise ValueError(f"Tidak ada data hingga tanggal {base_date}. Pastikan data historis mencakup tanggal tersebut.")

    latest_row = df_feat.iloc[-1]
    X_feat = latest_row[feature_cols].values.reshape(1, -1)

    last_exog = df_feat[exog_cols].iloc[-1].values
    exog_future = pd.DataFrame([last_exog] * horizon, columns=exog_cols)

    try:
        sarimax_fc = sarimax.forecast(steps=horizon, exog=exog_future)
    except Exception as e:
        raise RuntimeError(f"Gagal forecast SARIMAX: {e}")

    sarimax_vals = np.array(sarimax_fc)

    pred_dates = pd.date_range(
        df_feat.index[-1] + pd.Timedelta(days=1),
        periods=horizon,
        freq="D"
    )

    rows = []

    for h in range(1, horizon + 1):
        sarimax_log = sarimax_vals[h - 1]

        try:
            xgb_resid = xgb_models[h].predict(X_feat)[0]
        except Exception as e:
            raise RuntimeError(f"Gagal predict XGBoost H+{h}: {e}")

        try:
            lgb_resid = lgb_models[h].predict(X_feat)[0]
        except Exception as e:
            raise RuntimeError(f"Gagal predict LightGBM H+{h}: {e}")

        pred_sarimax = float(np.exp(sarimax_log))
        pred_xgb = float(np.exp(sarimax_log + xgb_resid))
        pred_lgb = float(np.exp(sarimax_log + lgb_resid))

        rows.append({
            "pred_date": pred_dates[h - 1],
            "SARIMAX": pred_sarimax,
            "Hybrid_XGBoost": pred_xgb,
            "Hybrid_LightGBM": pred_lgb
        })

    result_df = pd.DataFrame(rows)

    # Tambahkan data aktual jika tersedia
    result_df['Aktual'] = None
    for idx, row in result_df.iterrows():
        pred_date = row['pred_date']
        actual_row = antam_df[antam_df['date'] == pred_date]
        if not actual_row.empty:
            result_df.at[idx, 'Aktual'] = actual_row['harga_emas_antam_idr'].values[0]

    return df_feat, result_df