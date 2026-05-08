from io import BytesIO
import zipfile
import pandas as pd

def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="predictions")
    return output.getvalue()


def build_prediction_zip(
    pred_df: pd.DataFrame,
    actual_plot_bytes: bytes,
    forecast_plot_bytes: bytes,
    xgb_plot_bytes: bytes,
    lgb_plot_bytes: bytes,
) -> bytes:
    """
    Buat ZIP berisi:
    - prediction.csv
    - prediction.xlsx
    - actual_plot.png
    - forecast_plot.png
    - feature_importance_xgb.png
    - feature_importance_lgb.png
    """
    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("prediction.csv", to_csv_bytes(pred_df))
        zf.writestr("prediction.xlsx", to_excel_bytes(pred_df))
        zf.writestr("actual_plot.png", actual_plot_bytes)
        zf.writestr("forecast_plot.png", forecast_plot_bytes)
        zf.writestr("feature_importance_xgb.png", xgb_plot_bytes)
        zf.writestr("feature_importance_lgb.png", lgb_plot_bytes)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()