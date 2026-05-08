import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path("data/forecasting.db")

def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS antam_prices (
            date TEXT PRIMARY KEY,
            harga_emas_antam_idr REAL,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS usd_idr_rates (
            date TEXT PRIMARY KEY,
            kurs_usd_idr REAL,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            horizon INTEGER,
            model_name TEXT,
            pred_date TEXT,
            predicted_value REAL
        )
    """)

    conn.commit()
    conn.close()

def init_auth_tables(conn):
    cur = conn.cursor()

    # users table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # prediction history
    cur.execute("""
    CREATE TABLE IF NOT EXISTS prediction_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        horizon INTEGER,
        data_start_date TEXT,
        data_end_date TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    conn.commit()

def upsert_dataframe(df: pd.DataFrame, table_name: str):
    if df.empty:
        return

    conn = get_connection()
    cur = conn.cursor()

    cols = df.columns.tolist()
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)

    sql = f"INSERT OR REPLACE INTO {table_name} ({col_names}) VALUES ({placeholders})"

    cur.executemany(sql, df[cols].values.tolist())
    conn.commit()
    conn.close()

def read_table(table_name: str) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(f"SELECT * FROM {table_name} ORDER BY date", conn)
    conn.close()
    return df

def save_predictions(df: pd.DataFrame):
    conn = get_connection()
    df.to_sql("predictions", conn, if_exists="append", index=False)
    conn.close()
    