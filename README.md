# QueueCTL - Background Job Queue

QueueCTL is a resilient, concurrent background job queue built entirely in Python. It utilizes a SQLite database to maintain robust state management, allowing multiple worker processes to safely execute commands in parallel without race conditions..

## Detailed Features

* **CLI-Driven Architecture:** The system provides a comprehensive command-line interface using Python's `argparse`, allowing full control over job routing, worker management, and queue configuration.
* **True Concurrency:** By using Python's `multiprocessing` library, the system spawns completely separate OS processes for workers, bypassing the Global Interpreter Lock (GIL) and allowing true parallel execution.
* **Atomic Job Claims:** To prevent two workers from processing the same job simultaneously, the queue relies on SQLite's `UPDATE ... RETURNING` syntax to act as an atomic lock during the claim phase.
* **Zombie Process Recovery:** The workers are self-healing. At the start of every loop, they scan for jobs that have been stuck in the `processing` state for more than 45 seconds and reset them.
* **Exponential Backoff Strategy:** Failed jobs are not immediately retried. The system calculates a delay using `backoff_base ** attempts` and pushes the job's `run_after` timestamp into the future.
* **Dead Letter Queue (DLQ):** Jobs that repeatedly fail and hit the `max_retries` threshold are removed from the active queue and placed into a `dead` state for manual inspection.
* **Graceful Degradation:** Workers listen for `SIGINT` and `SIGTERM` signals. Upon receiving a stop command, they finish their current loop and safely clean up their PID tracking files.

---

## Command Reference

### Job Enqueueing & Deletion
* **`python main.py enqueue <json_string>`**
  Parses a JSON string and inserts a new job into the queue. The job starts in the `pending` state. 
  *Example:* `python main.py enqueue '{"id": "job_1", "command": "echo Hello"}'`
* **`python main.py delete <job_id>`**
  Permanently removes a job from the database entirely, regardless of its current state.

### Worker Management
* **`python main.py worker start count <n>`**
  Starts `<n>` concurrent background worker processes and records the main process ID to `queuectl_workers.pid`.
* **`python main.py worker stop`**
  Reads the PID file and sends a `SIGTERM` signal to gracefully shut down all active workers. If the process is already dead, it cleans up the stale PID file.

### Queue Monitoring
* **`python main.py list --state <state> [--json]`**
  Retrieves all jobs currently in the specified state (e.g., `pending`, `processing`, `completed`). The `--json` flag formats the output for programmatic parsing.
* **`python main.py status`**
  Displays a summary of how many jobs are in each state by grouping the database rows, and checks if the `queuectl_workers.pid` file exists to indicate if workers are active.

### Dead Letter Queue (DLQ)
* **`python main.py dlq list`**
  A shortcut command that lists all jobs currently in the `dead` state.
* **`python main.py dlq retry <job_id>`**
  Manually rescues a job from the DLQ by resetting its attempts to 0, updating its `run_after` time to now, and pushing it back into the `pending` queue.

### System Configuration
* **`python main.py config set <key> <value>`**
  Updates the `queuectl.json` configuration file. 
  *Supported keys:* `max-retries` (integer) and `backoff-base` (integer).
