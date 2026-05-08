import re
import requests
import pandas as pd
import yfinance as yf


def scrape_antam(start_date: str, end_date: str) -> pd.DataFrame:
    url = "https://pusatdata.kontan.co.id/market/chart_logam_mulia/"
    params = {
        "startdate": start_date,
        "enddate": end_date,
        "logam": "gold"
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://pusatdata.kontan.co.id/market/logam_mulia"
    }

    res = requests.get(url, params=params, headers=headers, timeout=30)
    res.raise_for_status()

    html = res.text

    tanggal_list = re.findall(r"tanggal\.push\('([^']+)'\)", html)
    harga_list = re.findall(r"harga\.push\('([^']+)'\)", html)

    if not harga_list:
        harga_list = re.findall(r"(?:price|harga_emas|gold|nilai)\.push\('([^']+)'\)", html)

    if not harga_list:
        with open("debug_chart_logam_mulia.html", "w", encoding="utf-8") as f:
            f.write(html)
        raise Exception("Data harga emas Antam tidak ditemukan dari response Kontan.")

    if len(tanggal_list) != len(harga_list):
        min_len = min(len(tanggal_list), len(harga_list))
        tanggal_list = tanggal_list[:min_len]
        harga_list = harga_list[:min_len]

    df = pd.DataFrame({
        "date": tanggal_list,
        "harga_emas_antam_idr": harga_list
    })

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["harga_emas_antam_idr"] = (
        df["harga_emas_antam_idr"]
        .astype(str)
        .str.replace(".", "", regex=False)
        .str.replace(",", "", regex=False)
    )
    df["harga_emas_antam_idr"] = pd.to_numeric(df["harga_emas_antam_idr"], errors="coerce")

    df = df.dropna(subset=["date", "harga_emas_antam_idr"]).sort_values("date").reset_index(drop=True)
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df["source"] = "Kontan"

    return df


def fetch_usd_idr(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Download kurs USD/IDR dari Yahoo Finance.
    Fallback ke period='30d' kalau request start/end kosong.
    """
    raw = yf.download(
        "IDR=X",
        start=start_date,
        end=end_date,
        auto_adjust=True,
        progress=False
    )

    if raw.empty:
        raw = yf.download(
            "IDR=X",
            period="30d",
            interval="1d",
            auto_adjust=True,
            progress=False
        )

    if raw.empty:
        raise Exception("Tidak ada data untuk ticker IDR=X dari Yahoo Finance.")

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw[["Close"]].reset_index().rename(columns={
        "Date": "date",
        "Close": "kurs_usd_idr"
    })

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["kurs_usd_idr"] = pd.to_numeric(df["kurs_usd_idr"], errors="coerce")

    # filter lagi sesuai range yang diminta kalau memungkinkan
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    df = df[(df["date"] >= start_dt) & (df["date"] <= end_dt)]

    # kalau setelah difilter kosong, pakai data fallback apa adanya
    if df.empty:
        raw2 = yf.download(
            "IDR=X",
            period="30d",
            interval="1d",
            auto_adjust=True,
            progress=False
        )

        if isinstance(raw2.columns, pd.MultiIndex):
            raw2.columns = raw2.columns.get_level_values(0)

        df = raw2[["Close"]].reset_index().rename(columns={
            "Date": "date",
            "Close": "kurs_usd_idr"
        })

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["kurs_usd_idr"] = pd.to_numeric(df["kurs_usd_idr"], errors="coerce")
    df = df.dropna(subset=["date", "kurs_usd_idr"]).sort_values("date").reset_index(drop=True)
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df["source"] = "yfinance"

    return df


def get_update_date_range(last_date: str | None = None):
    today = pd.Timestamp.today().normalize()

    if last_date:
        start = pd.to_datetime(last_date) + pd.Timedelta(days=1)
    else:
        start = today - pd.Timedelta(days=30)

    if start > today:
        start = today

    return start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")