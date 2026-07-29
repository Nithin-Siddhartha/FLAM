# Architectural Decisions Record (ADR)

This document outlines the core architectural choices, data flow mechanisms, and edge-case mitigations implemented in the QueueCTL system. 

## 1. Architecture Advantages & Problem Solving
The architecture of QueueCTL was designed defensively, operating under the assumption that hardware fails, processes crash, and commands hang. 

By leveraging SQLite's native file-locking alongside Python's multiprocessing capabilities, the architecture provides several distinct advantages that directly address the core challenges of background job processing:
* **Zero-Dependency Concurrency (Addresses Q1):** By pushing the concurrency locking down to the SQLite C-engine via `UPDATE ... RETURNING`, we eliminate the need for external lock managers (like Redis) or complex Python threading locks, resulting in a lightweight but highly robust concurrent system.
* **Guaranteed State Recovery (Addresses Q2):** The system assumes sudden death (`SIGKILL` or power cuts) is a normal operating condition. The 45-second zombie sweeping mechanism ensures no job is ever permanently orphaned in a `processing` state.
* **Clean Operational Handoffs (Addresses Q3):** Differentiating between automated transient retries (Exponential Backoff) and permanent deterministic failures (Dead Letter Queue) ensures worker compute isn't wasted on broken jobs, while allowing developers a clean interface to retry jobs once bugs are fixed.
* **Lightweight Inter-Process Communication (Addresses Q4):** Using OS-level signaling (`SIGTERM` via PID files) avoids the heavy disk I/O of database polling and the memory complexity of shared IPC events, keeping the worker loop incredibly fast.
* **High Extensibility (Addresses Q5):** The strict separation between the execution engine (`workers.py`) and the data access layer (`model.py`) means future features (like priority queues) only require tweaking a single SQL query rather than rewriting the execution logic.

---

## 2. Execution Flow Overview
To understand the architectural decisions below, it is helpful to visualize the normal execution lifecycle of a single job navigating the queue:

```text
    [ User / CLI ] 
          | (main.py enqueue)
          v
+-----------------------+
|    SQLite Database    | <--- State: 'pending'
+-----------------------+
          |
          | (Claimed via Atomic UPDATE)
          v
+-----------------------+
|    Worker Process     | <--- State: 'processing'
|   (subprocess.run)    | 
+-----------------------+
          |
          +-------------------------------+
          |                               |
  [Return Code == 0]              [Return Code != 0]
          |                               |
          v                               v
+-----------------------+       +-----------------------+
|    Mark Completed     |       |    Check Attempts     |
|  State: 'completed'   |       +-----------------------+
+-----------------------+                 |
                                          |
                        +-----------------+-----------------+
                        |                                   |
                (Attempts < Max)                    (Attempts >= Max)
                        |                                   |
                        v                                   v
+-----------------------+       +-----------------------+
|  Exponential Backoff  |       |   Dead Letter Queue   |
|   State: 'pending'    |       |     State: 'dead'     |
|   run_after: future   |       +-----------------------+

```
## 1. Storage & Concurrency Model
* **Decision:** SQLite as the primary queue backend5.
* **Rationale:** A memory-based queue (like a Python dictionary) would lose all job states during a power cut. SQLite writes directly to the disk, ensuring ACID compliance and state persistence5, 8. Furthermore, SQLite handles file-level locking. We leveraged `UPDATE ... RETURNING` inside `claim_atomic_job()` so that multiple concurrent workers can query the database simultaneously without ever claiming the same job.

## 2. Process Execution Over Threading
* **Decision:** Utilizing `multiprocessing.Process` for background workers10.
* **Rationale:** Python's Global Interpreter Lock (GIL) prevents threads from executing true parallel CPU instructions. By spawning entirely separate processes, each worker gets its own memory space and can run heavy `subprocess.run` tasks without blocking the other workers.

## 3. Zombie Job Sweeping (The 45-Second Rule)
* **Decision:** Implementing `recover_zombie_jobs()` at the top of the worker loop7, 10.
* **Rationale:** If a worker's machine loses power, the job it was processing remains stuck in the `processing` state indefinitely. The system calculates a 45-second cutoff threshold7. Any processing job older than this threshold is dynamically recovered. 
* **Infinite Loop Mitigation:** When recovering a zombie, the system intentionally adds `+1` to its `attempts` counter. This ensures that jobs which inherently take longer than 45 seconds will eventually hit the retry limit and fail safely into the Dead Letter Queue, rather than looping infinitely between workers.

## 4. The Dead Letter Queue (DLQ) Strategy
* **Decision:** Capping retries and routing to a `dead` state7.
* **Rationale:** The system differentiates between transient failures (which benefit from exponential backoff) and deterministic failures (like syntax errors, which will never succeed). By capping the attempts using `max_retries`, the system prevents broken jobs from permanently consuming worker compute cycles.

## 5. Subprocess Standard Output Handling
* **Decision:** Utilizing `capture_output=True` and safely parsing streams.
* **Rationale:** System commands often fail silently or write to standard error instead of standard output. The worker logic captures both `result.stdout` and `result.stderr`10. If a job fails, the worker intelligently strips and concatenates these streams to provide a clear, readable error log, defaulting to a fallback message if no output was provided by the OS10.

## 6. Assignment Questions & Tradeoffs
**1. Which exact lines prevent two workers from claiming the same job, and why is that operation atomic across separate OS processes?**
To prevent race conditions, I avoided fetching a job and then updating it in two separate steps. Instead, I relied on SQLite's `UPDATE ... RETURNING` syntax in `claim_atomic_job()`: ```SQL

UPDATE jobs 
SET state = 'processing', updated_at = ? 
WHERE id = (
    SELECT id FROM jobs WHERE state = 'pending' AND run_after <= ? LIMIT 1
) 
RETURNING id, command, attempts, max_retries

This is atomic because SQLite uses strict file-level locking for write operations. When Worker A executes this update, the database engine locks the file. The subquery finds the job, updates its state to `processing`, and returns the data all in one indivisible C-level operation. By the time the lock is released for Worker B, that specific job is no longer `pending`, making a double-claim impossible.

**2. A worker is SIGKILL'ed halfway through a job. Walk through, step by step, what state the job is in and how it eventually runs again. What is the worst-case delay before recovery?**
If a worker receives a hard `SIGKILL`, the OS terminates it instantly, meaning my Python `finally` blocks and signal handlers never run. 
*   **The State:** The job gets abandoned in the database. Its state remains `processing`, and its `updated_at` timestamp is frozen at the exact moment it was originally claimed.
*   **The Recovery:** To fix this, I put a `recover_zombie_jobs()` function at the very top of the worker loop. The next time *any* active worker loops around, it queries the database for `processing` jobs where `updated_at` is older than 45 seconds. It increments the attempts counter and forcefully resets the job to `pending` so it can be claimed normally.
*   **Worst-case delay:** 45 seconds (the zombie threshold) *plus* the time it takes for a currently busy worker to finish its current job and trigger the next loop.

**3. Does dlq retry reset attempts? Why is that the right call?**
Yes, my `reset_dlq_job` function explicitly sets `attempts = 0` when moving a job out of the DLQ back to `pending`. 
The tradeoff here is about recognizing human intervention. A job only lands in the DLQ because it failed repeatedly and exhausted its `max_retries`. If a developer is running `dlq retry` from the CLI, it implies they manually investigated and fixed the root cause (e.g., fixing a typo, bringing a downed API back online). Because the environment is fixed, the job deserves a completely fresh lifecycle. If I didn't reset the attempts, the job would fail once and instantly route right back to the DLQ, effectively bypassing the exponential backoff safety net entirely.

**4. What designs did you consider and reject for worker stop (cross-process signaling), and why?**
Getting completely separate OS processes to talk to each other is tricky, especially since the CLI command runs in a totally different terminal instance than the background workers. 
*   **Rejected Design 1 (Database Polling):** I considered adding a `shutdown_requested` table that workers query every second. I rejected this because the disk I/O tradeoff is terrible. Hitting the database constantly just to ask "should I die?" adds massive overhead and unnecessary database lock contention.
*   **Rejected Design 2 (Python IPC / Events):** I considered using `multiprocessing.Event()`. I rejected this because my CLI architecture instantiates a brand new Python runtime on every command. The CLI process cannot easily reach into the memory of a daemon process created hours ago to toggle an event.
*   **The Final Call:** I went with OS-level signals. By writing the master process ID to `queuectl_workers.pid`, the CLI can easily run `os.kill(pid, SIGTERM)`. It's lightweight, requires zero DB polling, and works reliably across different terminal sessions.

**5. If priorities were added tomorrow (high-priority jobs jump the queue), which parts of your design survive unchanged and which break?**
If I needed to add priorities tomorrow, the vast majority of the architecture survives completely untouched. The worker execution loop, the `subprocess.run` stdout/stderr capturing, the exponential backoff math, and the zombie recovery sweeps would require zero modifications. The core concept of the atomic lock also survives.

What breaks (and requires refactoring) is the job ingestion and the claim query:
1.  **Schema & CLI:** `init_db()` needs a new `priority` column, and the `enqueue` command needs to parse it.
2.  **The Claim Query:** The inner subquery inside `claim_atomic_job()` currently just grabs the oldest job via `LIMIT 1`. It would violate the priority rule. I would need to rewrite that subquery to `ORDER BY priority DESC, created_at ASC LIMIT 1` so high-priority jobs automatically bubble to the top of the lock.
