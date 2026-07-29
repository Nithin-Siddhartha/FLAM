import sqlite3
from datetime import datetime, timezone, timedelta
from connection import get_db


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def insert_job(job_id, command, max_retries):
    conn = get_db()
    now = now_iso()
    try:
        conn.execute(
            """
            INSERT INTO jobs (id, command, max_retries, run_after, created_at, updated_at) 
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (job_id, command, max_retries, now, now, now),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_status_counts():
    conn = get_db()
    rows = conn.execute(
        "SELECT state, COUNT(*) as count FROM jobs GROUP BY state"
    ).fetchall()
    conn.close()
    return rows


def get_jobs_by_state(state):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, command, state, attempts, max_retries, created_at, updated_at FROM jobs WHERE state = ?",
        (state,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def reset_dlq_job(job_id):
    conn = get_db()
    now = now_iso()
    cursor = conn.execute(
        "UPDATE jobs SET state = 'pending', attempts = 0, run_after = ?, updated_at = ? WHERE id = ? AND state = 'dead'",
        (now, now, job_id),
    )
    conn.commit()
    rowcount = cursor.rowcount
    conn.close()
    return rowcount > 0


def recover_zombie_jobs():
    conn = get_db()

    # 45-second cutoff
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=45)).isoformat()
    current_time = datetime.now(timezone.utc).isoformat()

    # 1. Kill zombies that have exhausted max_retries
    cursor_dead = conn.execute(
        """
        UPDATE jobs 
        SET state = 'dead', updated_at = ?
        WHERE state = 'processing' 
          AND updated_at < ? 
          AND (attempts + 1) >= max_retries
        RETURNING id
        """,
        (current_time, cutoff),
    )
    dead_jobs = [row["id"] for row in cursor_dead.fetchall()]

    # 2. Reset remaining zombies to pending and add +1 to attempts
    cursor_pending = conn.execute(
        """
        UPDATE jobs 
        SET state = 'pending', updated_at = ?, attempts = attempts + 1
        WHERE state = 'processing' 
          AND updated_at < ?
        RETURNING id, attempts, max_retries
        """,
        (current_time, cutoff),
    )
    pending_jobs = [dict(row) for row in cursor_pending.fetchall()]

    conn.commit()
    conn.close()

    return pending_jobs, dead_jobs


def claim_atomic_job():
    conn = get_db()
    now = now_iso()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE jobs 
        SET state = 'processing', updated_at = ? 
        WHERE id = (
            SELECT id FROM jobs 
            WHERE state = 'pending' AND run_after <= ? 
            LIMIT 1
        ) 
        RETURNING id, command, attempts, max_retries
    """,
        (now, now),
    )
    job = cursor.fetchone()
    conn.commit()
    conn.close()
    return dict(job) if job else None


def mark_job_completed(job_id):
    conn = get_db()
    conn.execute(
        "UPDATE jobs SET state = 'completed', updated_at = ? WHERE id = ?",
        (now_iso(), job_id),
    )
    conn.commit()
    conn.close()


def mark_job_failed(job_id, current_attempts, max_retries, backoff_base):
    conn = get_db()
    now = now_iso()
    attempts = current_attempts + 1
    if attempts >= max_retries:
        conn.execute(
            "UPDATE jobs SET state = 'dead', attempts = ?, updated_at = ? WHERE id = ?",
            (attempts, now, job_id),
        )
    else:
        delay = backoff_base**attempts
        run_after = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
        conn.execute(
            "UPDATE jobs SET state = 'pending', attempts = ?, run_after = ?, updated_at = ? WHERE id = ?",
            (attempts, run_after, now, job_id),
        )
    conn.commit()
    conn.close()


def delete_job(job_id):
    conn = get_db()
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
