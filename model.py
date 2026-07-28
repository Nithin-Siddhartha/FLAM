import sqlite3
from connection import get_db

def insert_job(job_id, command, max_retries):
    conn = get_db()
    try:
        conn.execute('''
            INSERT INTO jobs (id, command, max_retries, run_after, created_at, updated_at) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (job_id, command, max_retries, now, now, now))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_status_counts():
    conn = get_db()
    rows = conn.execute("SELECT state, COUNT(*) as count FROM jobs GROUP BY state").fetchall()
    conn.close()
    return rows
