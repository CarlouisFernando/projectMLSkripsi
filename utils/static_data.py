from pathlib import Path
import pandas as pd
import numpy as np
import io
import re

STATIC_PATH = Path("data/master_static.csv")

REQUIRED_STATIC_COLS = ["date", "xau_usd", "inflasi_yoy_id", "bi_7drr_rate"]

MONTH_MAP_ID = {
    "januari": "January",
    "februari": "February",
    "maret": "March",
    "april": "April",
    "mei": "May",
    "juni": "June",
    "juli": "July",
    "agustus": "August",
    "september": "September",
    "oktober": "October",
    "november": "November",
    "desember": "December",
}


def ensure_static_file():
    STATIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STATIC_PATH.exists():
        df = pd.DataFrame(columns=REQUIRED_STATIC_COLS)
        df.to_csv(STATIC_PATH, index=False)


def load_static_data() -> pd.DataFrame:
    ensure_static_file()
    df = pd.read_csv(STATIC_PATH)

    for col in REQUIRED_STATIC_COLS:
        if col not in df.columns:
            df[col] = pd.NA

    df = df[REQUIRED_STATIC_COLS].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    for col in ["xau_usd", "inflasi_yoy_id", "bi_7drr_rate"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def save_static_data(df: pd.DataFrame):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").drop_duplicates(subset=["date"], keep="last")

    for col in REQUIRED_STATIC_COLS:
        if col not in df.columns:
            df[col] = pd.NA

    df = df[REQUIRED_STATIC_COLS].copy()
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    STATIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(STATIC_PATH, index=False)


def merge_into_static(upload_df: pd.DataFrame, target_col: str):
    base_df = load_static_data()

    up = upload_df.copy()
    up["date"] = pd.to_datetime(up["date"], errors="coerce")
    up[target_col] = pd.to_numeric(up[target_col], errors="coerce")
    up = up.dropna(subset=["date", target_col]).sort_values("date").drop_duplicates(subset=["date"], keep="last")

    merged = base_df.merge(up[["date", target_col]], on="date", how="outer", suffixes=("", "_new"))

    if f"{target_col}_new" in merged.columns:
        merged[target_col] = merged[f"{target_col}_new"].combine_first(merged[target_col])
        merged = merged.drop(columns=[f"{target_col}_new"])

    merged = merged.sort_values("date").reset_index(drop=True)
    save_static_data(merged)

    return {
        "rows_uploaded": len(up),
        "date_min": up["date"].min().date() if not up.empty else None,
        "date_max": up["date"].max().date() if not up.empty else None,
    }


def _read_uploaded_table(uploaded_file):
    name = uploaded_file.name.lower()

    if name.endswith(".csv"):
        try:
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file)
        except Exception:
            uploaded_file.seek(0)
            raw = uploaded_file.read()
            uploaded_file.seek(0)
            return pd.read_csv(io.BytesIO(raw), encoding="latin1")

    elif name.endswith(".xlsx") or name.endswith(".xls"):
        uploaded_file.seek(0)
        return pd.read_excel(uploaded_file, header=None)

    else:
        raise ValueError("Format file belum didukung. Gunakan CSV/XLS/XLSX.")


def _parse_localized_number(val):
    if pd.isna(val):
        return np.nan

    s = str(val).strip()
    if s == "":
        return np.nan

    s = s.replace("%", "").replace('"', "").strip()

    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        if "," in s:
            s = s.replace(",", ".")

    s = re.sub(r"[^0-9\.\-]", "", s)

    try:
        return float(s)
    except Exception:
        return np.nan


def _translate_month_id(text: str):
    s = str(text).strip()
    lower = s.lower()
    for indo, eng in MONTH_MAP_ID.items():
        lower = re.sub(rf"\b{indo}\b", eng, lower, flags=re.IGNORECASE)
    return lower.title()


def _find_header_row(df_raw, keywords):
    for i in range(min(len(df_raw), 20)):
        row_text = " ".join(df_raw.iloc[i].astype(str).tolist()).lower()
        if all(k.lower() in row_text for k in keywords):
            return i
    return None


def parse_xau_upload(uploaded_file) -> pd.DataFrame:
    if uploaded_file.name.lower().endswith(".csv"):
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file)
    else:
        raw = _read_uploaded_table(uploaded_file)
        header_idx = _find_header_row(raw, ["tanggal", "terakhir"])
        if header_idx is None:
            raise ValueError("Header XAU/USD tidak ditemukan.")
        df = pd.read_excel(uploaded_file, header=header_idx)

    df.columns = [str(c).strip().lower() for c in df.columns]

    date_col = None
    value_col = None

    for c in ["tanggal", "date"]:
        if c in df.columns:
            date_col = c
            break

    for c in ["terakhir", "xau_usd", "harga_emas_dunia_usd", "close"]:
        if c in df.columns:
            value_col = c
            break

    if date_col is None or value_col is None:
        raise ValueError("Kolom XAU/USD tidak sesuai. Wajib ada `Tanggal` dan `Terakhir`.")

    out = df[[date_col, value_col]].copy()
    out.columns = ["date", "xau_usd"]
    out["date"] = pd.to_datetime(out["date"], format="%d/%m/%Y", errors="coerce")
    out["xau_usd"] = out["xau_usd"].apply(_parse_localized_number)

    out = out.dropna(subset=["date", "xau_usd"]).sort_values("date").drop_duplicates(subset=["date"], keep="last")
    return out


def parse_bi_rate_upload(uploaded_file) -> pd.DataFrame:
    raw = _read_uploaded_table(uploaded_file)

    if isinstance(raw.columns, pd.Index) and "tanggal" in [str(c).strip().lower() for c in raw.columns]:
        df = raw.copy()
    else:
        header_idx = _find_header_row(raw, ["tanggal", "bi-7day-rr"])
        if header_idx is None:
            header_idx = _find_header_row(raw, ["tanggal", "bi"])
        if header_idx is None:
            raise ValueError("Header BI Rate tidak ditemukan.")
        uploaded_file.seek(0)
        df = pd.read_excel(uploaded_file, header=header_idx)

    df.columns = [str(c).strip().lower() for c in df.columns]

    date_col = None
    value_col = None

    for c in ["tanggal", "date"]:
        if c in df.columns:
            date_col = c
            break

    for c in ["bi-7day-rr", "bi_7drr_rate", "bi rate", "bi_rate"]:
        if c in df.columns:
            value_col = c
            break

    if date_col is None or value_col is None:
        raise ValueError("Kolom BI Rate tidak sesuai.")

    out = df[[date_col, value_col]].copy()
    out.columns = ["date", "bi_7drr_rate"]
    out["date"] = out["date"].astype(str).apply(_translate_month_id)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["bi_7drr_rate"] = out["bi_7drr_rate"].apply(_parse_localized_number)

    out = out.dropna(subset=["date", "bi_7drr_rate"]).sort_values("date").drop_duplicates(subset=["date"], keep="last")
    return out


def parse_inflation_upload(uploaded_file) -> pd.DataFrame:
    raw = _read_uploaded_table(uploaded_file)

    if isinstance(raw.columns, pd.Index) and "periode" in [str(c).strip().lower() for c in raw.columns]:
        df = raw.copy()
    else:
        header_idx = _find_header_row(raw, ["periode", "inflasi"])
        if header_idx is None:
            raise ValueError("Header inflasi tidak ditemukan.")
        uploaded_file.seek(0)
        df = pd.read_excel(uploaded_file, header=header_idx)

    df.columns = [str(c).strip().lower() for c in df.columns]

    period_col = None
    value_col = None

    for c in ["periode", "period", "tanggal", "date"]:
        if c in df.columns:
            period_col = c
            break

    for c in ["data inflasi", "inflasi_yoy_id", "inflasi", "data_inflasi"]:
        if c in df.columns:
            value_col = c
            break

    if period_col is None or value_col is None:
        raise ValueError("Kolom inflasi tidak sesuai.")

    out = df[[period_col, value_col]].copy()
    out.columns = ["period", "inflasi_yoy_id"]

    out["period"] = out["period"].astype(str).apply(_translate_month_id)
    out["date"] = pd.to_datetime("01 " + out["period"], errors="coerce")
    out["inflasi_yoy_id"] = out["inflasi_yoy_id"].apply(_parse_localized_number)

    out = out[["date", "inflasi_yoy_id"]].copy()
    out = out.dropna(subset=["date", "inflasi_yoy_id"]).sort_values("date").drop_duplicates(subset=["date"], keep="last")
    return out