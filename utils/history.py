import sqlite3
from datetime import datetime

DB_PATH = "data/app.db"


def save_history(user_id, horizon, start_date, end_date):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO prediction_history (user_id, horizon, data_start_date, data_end_date)
    VALUES (?, ?, ?, ?)
    """, (user_id, horizon, start_date, end_date))

    conn.commit()
    conn.close()


def get_user_history(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    SELECT run_timestamp, horizon, data_start_date, data_end_date
    FROM prediction_history
    WHERE user_id = ?
    ORDER BY run_timestamp DESC
    """, (user_id,))

    rows = cur.fetchall()
    conn.close()

    return rows