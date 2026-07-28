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

def get_jobs(state):
    conn = get_db()
    rows = conn.execute("SELECT id, command, state, attempts, max_retries, created_at, updated_at FROM jobs WHERE state = ?", (state,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]

def fetch_next_job():
    conn = get_db()
    now = now_iso()
    job = conn.execute("SELECT * FROM jobs WHERE state = 'pending' LIMIT 1").fetchone()
    if job:
        conn.execute("UPDATE jobs SET state = 'processing', updated_at = ? WHERE id = ?", (now, job['id']))
        conn.commit()
    conn.close()
    return dict(job) if job else None

def complete_job(job_id):
    conn = get_db()
    conn.execute("UPDATE jobs SET state = 'completed', updated_at = ? WHERE id = ?", (now_iso(), job_id))
    conn.commit()
    conn.close()
    
def fail_job(job_id):
    conn = get_db()
    conn.execute("UPDATE jobs SET state = 'dead', updated_at = ? WHERE id = ?", (now_iso(), job_id))
    conn.commit()
    conn.close()
