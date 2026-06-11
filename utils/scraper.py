import re
import requests
import pandas as pd


def scrape_antam(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Scrape harga emas Antam dari Kontan
    """

    chart_url = "https://pusatdata.kontan.co.id/market/chart_logam_mulia/"
    landing_url = "https://pusatdata.kontan.co.id/market/logam_mulia"

    params = {
        "startdate": start_date,
        "enddate": end_date,
        "logam": "gold"
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/137.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": landing_url,
        "Origin": "https://pusatdata.kontan.co.id",
        "Connection": "keep-alive",
        "X-Requested-With": "XMLHttpRequest",
    }

    session = requests.Session()

    try:
        # buka halaman utama terlebih dahulu
        session.get(
            landing_url,
            headers=headers,
            timeout=30
        )
    except Exception:
        pass

    response = session.get(
        chart_url,
        params=params,
        headers=headers,
        timeout=30
    )

    if response.status_code != 200:

        with open(
            "debug_chart_logam_mulia_error.html",
            "w",
            encoding="utf-8"
        ) as f:
            f.write(response.text)

        raise Exception(
            f"Kontan mengembalikan HTTP {response.status_code}"
        )

    html = response.text

    tanggal_list = re.findall(
        r"tanggal\.push\('([^']+)'\)",
        html
    )

    harga_list = re.findall(
        r"harga\.push\('([^']+)'\)",
        html
    )

    if not harga_list:
        harga_list = re.findall(
            r"(?:price|harga_emas|gold|nilai)\.push\('([^']+)'\)",
            html
        )

    if not harga_list:

        with open(
            "debug_chart_logam_mulia.html",
            "w",
            encoding="utf-8"
        ) as f:
            f.write(html)

        raise Exception(
            "Data harga emas Antam tidak ditemukan dari response Kontan."
        )

    if len(tanggal_list) != len(harga_list):

        min_len = min(
            len(tanggal_list),
            len(harga_list)
        )

        tanggal_list = tanggal_list[:min_len]
        harga_list = harga_list[:min_len]

    df = pd.DataFrame({
        "date": tanggal_list,
        "harga_emas_antam_idr": harga_list
    })

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce"
    )

    df["harga_emas_antam_idr"] = (
        df["harga_emas_antam_idr"]
        .astype(str)
        .str.replace(".", "", regex=False)
        .str.replace(",", "", regex=False)
    )

    df["harga_emas_antam_idr"] = pd.to_numeric(
        df["harga_emas_antam_idr"],
        errors="coerce"
    )

    df = (
        df.dropna(
            subset=[
                "date",
                "harga_emas_antam_idr"
            ]
        )
        .sort_values("date")
        .reset_index(drop=True)
    )

    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    df["source"] = "Kontan"

    return df
